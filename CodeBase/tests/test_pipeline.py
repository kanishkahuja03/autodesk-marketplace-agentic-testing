"""Tests for the single entry point and run logging. Run with: uv run pytest"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from plans import fake_ask, good_plan_data

from mpagent import pipeline
from mpagent.config import load_settings
from mpagent.runlog import RUN_LOG, Trace

REAL_PLUGIN = Path(__file__).parent.parent / "inputs" / "pid-connector-exporter"


def _only_run_dir(runs: Path) -> Path:
    run_dirs = [p for p in runs.glob("*/*") if p.is_dir()]
    assert len(run_dirs) == 1
    return run_dirs[0]


def _last_line(run_dir: Path) -> str:
    return (run_dir / RUN_LOG).read_text(encoding="utf-8").strip().splitlines()[-1]


def test_missing_input_folder_stops_without_run_folder(tmp_path):
    code = pipeline.run(tmp_path / "does-not-exist", tmp_path / "runs")
    assert code == pipeline.EXIT_STOPPED
    assert not (tmp_path / "runs").exists()


def test_failure_after_intake_is_logged_in_run_log(tmp_path):
    app = tmp_path / "inputs" / "fake-app"
    app.mkdir(parents=True)
    (app / "description.txt").write_text("A fake app.\n", encoding="utf-8")
    (app / "setup.msi").write_bytes(b"not a real msi")

    code = pipeline.run(app, tmp_path / "runs")

    assert code == pipeline.EXIT_STOPPED
    run_dir = _only_run_dir(tmp_path / "runs")
    log_text = (run_dir / RUN_LOG).read_text(encoding="utf-8")
    assert "S0 intake: start" in log_text  # lines from before the run folder existed are kept
    assert "STOPPED: S1 installer static read failed" in _last_line(run_dir)


needs_real_inputs = pytest.mark.skipif(not REAL_PLUGIN.exists(), reason="real plug-in inputs not present")


@pytest.fixture
def no_machine(monkeypatch):
    """Skip everything that touches the machine; records whether the host kill and cleanup ran, and in which order."""
    calls = {"agent2": 0, "cleanup": 0, "order": []}

    def step(name):
        def run(*_a):
            calls[name] = calls.get(name, 0) + 1
            calls["order"].append(name)
            return []
        return run
    monkeypatch.setattr(pipeline, "run_preflight", lambda *a: None)
    monkeypatch.setattr(pipeline, "run_agent2", step("agent2"))
    monkeypatch.setattr(pipeline, "kill_host", step("kill_host"))
    monkeypatch.setattr(pipeline, "save_crash_events", lambda *a: [])
    monkeypatch.setattr(pipeline, "cleanup", step("cleanup"))
    return calls


@needs_real_inputs
def test_real_plugin_full_run_completes(tmp_path, no_machine):
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()))
    assert code == pipeline.EXIT_COMPLETED
    run_dir = _only_run_dir(tmp_path / "runs")
    for name in ("installer_facts.json", "testcases.yaml", "testcases.json", "understanding.md", "trace.jsonl"):
        assert (run_dir / name).exists(), name
    # the host is killed before cleanup, so the uninstall never runs under it (LOAD_TESTS_PLAN.md L12)
    assert no_machine["order"] == ["agent2", "kill_host", "cleanup"]
    assert (run_dir / "results.json").exists() and (run_dir / "report.html").exists()
    last = _last_line(run_dir)
    assert " COMPLETED: " in last and "report:" in last  # stand-in Agent 2 recorded nothing: all ERROR/BLOCKED


@needs_real_inputs
def test_agent2_failure_stops_after_cleanup(tmp_path, no_machine, monkeypatch):
    def broken(*_a):
        raise pipeline.Agent2Error("time limit reached (20 min)")
    monkeypatch.setattr(pipeline, "run_agent2", broken)
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()))
    assert code == pipeline.EXIT_STOPPED
    assert no_machine["cleanup"] == 1
    run_dir = _only_run_dir(tmp_path / "runs")
    log_text = (run_dir / RUN_LOG).read_text(encoding="utf-8")
    assert ("observations: 0 of 6 tests recorded; missing: ENV-000, INST-001, INST-002, LOAD-000, UNIN-000, UNIN-001"
            in log_text)  # LOAD-000 is built in for a host with host_process; UNIN-000 for every app
    assert (run_dir / "report.html").exists()  # the report is still written for a cut-off run
    assert "STOPPED: Agent 2 didn't finish: time limit reached (20 min)" in _last_line(run_dir)


@needs_real_inputs
def test_agent1_self_check_failure_stops_before_agent2(tmp_path):
    bad = good_plan_data()
    bad["testcases"][0]["source"]["quote"] = "an invented sentence"
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(bad))
    assert code == pipeline.EXIT_STOPPED
    run_dir = _only_run_dir(tmp_path / "runs")
    last = _last_line(run_dir)
    assert "STOPPED: Agent 1 failed: self-check failed after 2 retries" in last and "Agent 2 not started" in last
    assert not (run_dir / "testcases.yaml").exists()


@needs_real_inputs
def test_not_admin_stops_after_design_side(tmp_path, monkeypatch):
    monkeypatch.setattr("mpagent.execute.preflight.is_elevated", lambda: False)
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()))
    assert code == pipeline.EXIT_STOPPED
    run_dir = _only_run_dir(tmp_path / "runs")
    assert "STOPPED: preflight: not running as administrator" in _last_line(run_dir)
    assert (run_dir / "testcases.yaml").exists()  # design outputs are kept


@needs_real_inputs
def test_missing_openai_settings_stop_the_run(tmp_path, monkeypatch):
    no_key = replace(load_settings(), openai_api_key=None, gemini_api_key=None)
    monkeypatch.setattr(pipeline, "load_settings", lambda: no_key)
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs")  # real LLM path, but it must stop before any call
    assert code == pipeline.EXIT_STOPPED
    last = _last_line(_only_run_dir(tmp_path / "runs"))
    assert "STOPPED: Agent 1 can't start: missing in" in last
    assert "no run folder was created" not in last


def test_trace_appends_json_lines(tmp_path):
    trace = Trace(tmp_path)
    trace.write("llm_request", agent="test-designer", attempt=1)
    trace.write("mcp_call", tool="Snapshot")
    records = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["event"] for r in records] == ["llm_request", "mcp_call"]
    assert records[0]["agent"] == "test-designer"


@needs_real_inputs
def test_review_answer_no_stops_before_anything_is_installed(tmp_path, no_machine):
    # seniors' request (LOAD_TESTS_PLAN.md L19): review testcases.yaml, then y/n in the console
    asked = []
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()),
                        confirm=lambda q: asked.append(q) or False)
    assert code == pipeline.EXIT_STOPPED and asked == [pipeline.REVIEW_QUESTION]
    assert no_machine["order"] == []  # no preflight result used, Agent 2 never started
    run_dir = _only_run_dir(tmp_path / "runs")
    log_text = (run_dir / RUN_LOG).read_text(encoding="utf-8")
    assert "INST-001" in log_text and "testcases.yaml" in log_text  # the plan is listed for the reviewer
    assert "STOPPED: test plan not approved at the review" in _last_line(run_dir)


@needs_real_inputs
def test_review_answer_yes_continues(tmp_path, no_machine):
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()), confirm=lambda q: True)
    assert code == pipeline.EXIT_COMPLETED and no_machine["order"][0] == "agent2"
    assert "Test case review: approved" in (_only_run_dir(tmp_path / "runs") / RUN_LOG).read_text(encoding="utf-8")


def test_console_confirm_asks_until_y_or_n(monkeypatch):
    answers = iter(["", "maybe", "Y"])
    monkeypatch.setattr("builtins.input", lambda q: next(answers))
    assert pipeline.console_confirm("go? ") is True
    monkeypatch.setattr("builtins.input", lambda q: "n")
    assert pipeline.console_confirm("go? ") is False

    def interrupted(q):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", interrupted)
    assert pipeline.console_confirm("go? ") is False
