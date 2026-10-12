"""Tests for the single entry point and run logging. Run with: uv run pytest"""

import json
from pathlib import Path

import pytest

from mpagent import pipeline
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


@pytest.mark.skipif(not REAL_PLUGIN.exists(), reason="real plug-in inputs not present")
def test_real_plugin_design_side_completes(tmp_path):
    code = pipeline.run(REAL_PLUGIN, tmp_path / "runs")
    assert code == pipeline.EXIT_COMPLETED
    run_dir = _only_run_dir(tmp_path / "runs")
    assert (run_dir / "installer_facts.json").exists()
    assert " COMPLETED: " in _last_line(run_dir)


def test_trace_appends_json_lines(tmp_path):
    trace = Trace(tmp_path)
    trace.write("llm_request", agent="test-designer", attempt=1)
    trace.write("mcp_call", tool="Snapshot")
    records = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["event"] for r in records] == ["llm_request", "mcp_call"]
    assert records[0]["agent"] == "test-designer"
