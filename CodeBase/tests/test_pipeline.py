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
    """Skip everything that touches the machine; records whether cleanup ran."""
    calls = {"agent2": 0, "cleanup": 0}
    monkeypatch.setattr(pipeline, "run_preflight", lambda run_dir, facts, settings: None)
    monkeypatch.setattr(pipeline, "run_agent2", lambda *a: calls.__setitem__("agent2", calls["agent2"] + 1))
    monkeypatch.setattr(pipeline, "cleanup", lambda run_dir, facts: calls.__setitem__("cleanup", calls["cleanup"] + 1))
    return calls


@needs_real_inputs
def test_real_plugin_full_run_completes(tmp_path, no_machine):
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()))
    assert code == pipeline.EXIT_COMPLETED
    run_dir = _only_run_dir(tmp_path / "runs")
    for name in ("installer_facts.json", "testcases.yaml", "testcases.json", "understanding.md", "trace.jsonl"):
        assert (run_dir / name).exists(), name
    assert no_machine == {"agent2": 1, "cleanup": 1}
    assert " COMPLETED: " in _last_line(run_dir)


@needs_real_inputs
def test_agent2_failure_stops_after_cleanup(tmp_path, no_machine, monkeypatch):
    def broken(*_a):
        raise pipeline.Agent2Error("time limit reached (20 min)")
    monkeypatch.setattr(pipeline, "run_agent2", broken)
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs", agent1_ask=fake_ask(good_plan_data()))
    assert code == pipeline.EXIT_STOPPED
    assert no_machine["cleanup"] == 1
    log_lines = (_only_run_dir(tmp_path / "runs") / RUN_LOG).read_text(encoding="utf-8").splitlines()
    assert "observations: 0 of 4 tests recorded; missing: ENV-000, INST-001, INST-002, UNIN-001" in log_lines[-2]
    assert "STOPPED: Agent 2 didn't finish: time limit reached (20 min)" in log_lines[-1]


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
