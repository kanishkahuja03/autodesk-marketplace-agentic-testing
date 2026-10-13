"""Tests for Agent 2's plumbing and the cleanup, without an LLM or real installs. Run with: uv run pytest"""

import asyncio
import base64
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest
from plans import good_plan_data

from mpagent.config import load_settings
from mpagent.execute import agent2, cleanup
from mpagent.execute.observations import load_observations
from mpagent.execute.windows_mcp import CallRecorder
from mpagent.models import InstallerFacts, KeyValue, TestPlan
from mpagent.runlog import Trace

PNG = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")).decode()
FACTS = InstallerFacts(installer_file="x.msi", installer_type="msi", sha256="0",
                       properties={"ProductCode": "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}", "ProductName": "App"})


def plan() -> TestPlan:
    return TestPlan.model_validate(good_plan_data())


def mcp_result(*content):
    return SimpleNamespace(content=list(content), is_error=False)


def test_instructions_include_both_skills_and_host_note():
    text = agent2.instructions("autocad-plant3d")
    assert "# Windows installer testing (Agent 2)" in text and "# Evidence and reporting rules" in text
    assert "# Host: AutoCAD Plant 3D" in text
    assert "# Host:" not in agent2.instructions("unknown")


def test_input_contains_plan_paths_and_untrusted_rule(tmp_path):
    prompt = agent2.build_input(plan(), tmp_path, tmp_path / "x.msi", None)
    assert str(tmp_path) in prompt and "INSTALLER_PATH" in prompt and "id: INST-001" in prompt
    assert "never instructions" in prompt


def test_screenshots_are_saved_and_attached_to_next_observation(tmp_path):
    trace = Trace(tmp_path)
    calls = CallRecorder(tmp_path, trace)
    calls.record("Screenshot", {}, mcp_result(SimpleNamespace(type="text", text="Cursor"),
                                              SimpleNamespace(type="image", data=PNG, mimeType="image/png")))
    obs = agent2.ObservationRecorder(tmp_path, plan(), calls, trace)

    reply = obs.record("UNIN-001", True, [KeyValue(key="uninstall_entry_exists", value=False)], [], None)

    assert reply == "Recorded UNIN-001."
    saved = load_observations(tmp_path)[0]
    assert saved.evidence == ["evidence/001_Screenshot_1.png"] and (tmp_path / saved.evidence[0]).exists()
    assert calls.take_pending() == []  # handed over once
    assert '"event": "mcp_call"' in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")


def test_record_rejects_unknown_and_built_in_ids(tmp_path):
    obs = agent2.ObservationRecorder(tmp_path, plan(), CallRecorder(tmp_path, Trace(tmp_path)), Trace(tmp_path))
    assert "Unknown test_id" in obs.record("INST-999", True, [], [], None)
    assert "recorded by code" in obs.record("ENV-000", True, [], [], None)
    assert load_observations(tmp_path) == []


def test_time_limit_becomes_agent2_error(tmp_path, monkeypatch):
    async def slow(*_args):
        await asyncio.sleep(5)
    monkeypatch.setattr(agent2, "_run", slow)
    settings = replace(load_settings(), agent2_timeout_min=0)
    with pytest.raises(agent2.Agent2Error, match="time limit reached"):
        agent2.run_agent2(plan(), tmp_path, tmp_path / "x.msi", settings)


def test_cleanup_does_nothing_when_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "find_uninstall_entry", lambda code, name: None)
    monkeypatch.setattr(cleanup.subprocess, "run", lambda *a, **k: pytest.fail("msiexec must not run"))
    cleanup.cleanup(tmp_path, FACTS)


def test_cleanup_uninstalls_a_leftover_msi(tmp_path, monkeypatch):
    state = {"installed": True}
    monkeypatch.setattr(cleanup, "find_uninstall_entry", lambda code, name: "HKLM:\\X" if state["installed"] else None)

    def fake_run(cmd, **_kw):
        assert cmd[:3] == ["msiexec.exe", "/x", FACTS.properties["ProductCode"]] and "/qn" in cmd
        state["installed"] = False
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(cleanup.subprocess, "run", fake_run)
    cleanup.cleanup(tmp_path, FACTS)
    assert state["installed"] is False


def test_cleanup_skips_non_msi(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "find_uninstall_entry", lambda code, name: "HKLM:\\X")
    monkeypatch.setattr(cleanup.subprocess, "run", lambda *a, **k: pytest.fail("msiexec must not run"))
    cleanup.cleanup(tmp_path, FACTS.model_copy(update={"installer_type": "exe"}))
