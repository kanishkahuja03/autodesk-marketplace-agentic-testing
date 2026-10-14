"""Tests for Agent 2's plumbing and the cleanup, without an LLM or real installs. Run with: uv run pytest"""

import asyncio
import base64
import os
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


def test_record_rejects_evidence_files_that_dont_exist(tmp_path):
    # run 20261012-191028: Agent 2 listed evidence/install.log although msiexec never wrote it
    obs = agent2.ObservationRecorder(tmp_path, plan(), CallRecorder(tmp_path, Trace(tmp_path)), Trace(tmp_path))
    exit_code = [KeyValue(key="install_exit_code", value=0)]

    reply = obs.record("INST-001", True, exit_code, ["evidence/install.log"], None)
    assert reply.startswith("Not recorded") and load_observations(tmp_path) == []
    assert "Not recorded" in obs.record("INST-001", True, exit_code, ["../../outside.txt"], None)

    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "install.log").write_text("Installation success or error status: 0.", encoding="utf-8")
    assert obs.record("INST-001", True, exit_code, ["evidence/install.log"], None) == "Recorded INST-001."


def test_evidence_folder_exists_before_agent2_starts(tmp_path, monkeypatch):
    seen = {}

    async def fake_run(_plan, run_dir, *_a):
        seen["evidence"] = (run_dir / "evidence").is_dir()
        return agent2.Agent2Result(done=True, env=[])
    monkeypatch.setattr(agent2, "_run", fake_run)
    agent2.run_agent2(plan(), tmp_path, tmp_path / "x.msi", load_settings())
    assert seen["evidence"] is True


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


def test_executed_observation_is_not_replaced_and_repeats_are_ignored(tmp_path):
    # run 20261013-125224: ENV-001's good result was overwritten by later "not executed" records
    obs = agent2.ObservationRecorder(tmp_path, plan(), CallRecorder(tmp_path, Trace(tmp_path)), Trace(tmp_path))
    good = [KeyValue(key="install_exit_code", value=0)]

    assert obs.record("INST-001", False, [KeyValue(key="install_exit_code", value=None)], [], "failed") == \
        "Recorded INST-001."
    assert obs.record("INST-001", True, good, [], None) == "Recorded INST-001."  # not executed -> executed is fine
    assert "already recorded as executed" in obs.record("INST-001", False, [], [], "gave up")
    assert obs.record("INST-001", True, good, [], "again").startswith("Already recorded")
    saved = load_observations(tmp_path)
    assert len(saved) == 1 and saved[0].executed and saved[0].observed == good


def test_input_names_the_app_and_real_folders(tmp_path):
    # run 20261013-132121: Agent 2 guessed C:\Users\Admin and selected the wrong program
    plugins = r"%AppData%\Autodesk\ApplicationPlugins"
    facts = FACTS.model_copy(update={"install_roots": [plugins]})
    prompt = agent2.build_input(plan(), tmp_path, tmp_path / "x.msi", None, facts)
    assert "DisplayName (name in Programs and Features): App" in prompt
    wow = r"HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall" + "\\"
    assert wow + FACTS.properties["ProductCode"] in prompt
    assert f"%APPDATA% = {os.environ['APPDATA']}" in prompt
    assert os.path.expandvars(plugins) in prompt


# ---------------------------------------------------------------- LOAD (FUNCTIONAL_TESTS_PLAN.md L5, L9, L17)
def load_plan() -> TestPlan:
    from plans import load_plan_data

    from mpagent.design.agent1 import add_built_in_tests
    from mpagent.hostnotes import host_process
    return add_built_in_tests(TestPlan.model_validate(load_plan_data()), FACTS, host_process("autocad-plant3d"))


def test_snapshot_text_is_saved_in_full_and_attached(tmp_path):
    trace = Trace(tmp_path)
    calls = CallRecorder(tmp_path, trace)
    big = "UI Tree:\n" + "x" * 50_000  # longer than what the model and the trace get
    calls.record("Snapshot", {}, mcp_result(SimpleNamespace(type="text", text=big)))
    assert calls.has_pending_snapshot()
    saved = tmp_path / "evidence" / "001_Snapshot_ui.txt"
    assert saved.read_text(encoding="utf-8") == big
    calls.record("Click", {}, mcp_result(SimpleNamespace(type="text", text="clicked")))
    assert calls.take_pending() == ["evidence/001_Snapshot_ui.txt"]  # only Snapshots are saved as text


def test_ui_tests_need_a_snapshot_before_recording(tmp_path):
    trace = Trace(tmp_path)
    calls = CallRecorder(tmp_path, trace)
    obs = agent2.ObservationRecorder(tmp_path, load_plan(), calls, trace)
    label = [KeyValue(key="entry_point_label", value="P&ID Exporter")]

    assert "Take a Snapshot of the host window first" in obs.record("LOAD-001", True, label, [], None)
    assert obs.record("LOAD-001", False, [KeyValue(key="entry_point_label", value=None)], [], "install failed") == \
        "Recorded LOAD-001."  # not executed: no Snapshot needed
    calls.record("Snapshot", {}, mcp_result(SimpleNamespace(type="text", text="UI Tree:\n")))
    assert obs.record("LOAD-001", True, label, [], None) == "Recorded LOAD-001."
    assert load_observations(tmp_path)[0].evidence == ["evidence/001_Snapshot_ui.txt"]


def test_host_interaction_skill_and_host_block_only_with_load(tmp_path):
    assert "# Host interaction: LOAD tests" in agent2.instructions("autocad-plant3d", with_host_interaction=True)
    assert "# Host interaction" not in agent2.instructions("autocad-plant3d")
    assert agent2.host_launch(plan()) is None  # no LOAD tests in the plan
    host = agent2.HostLaunch(executable=r"C:\Host\host.exe", args=["/a", "b"], processes=["host.exe"],
                             main_window="^Host", new_document="Doc1")
    prompt = agent2.build_input(load_plan(), tmp_path, tmp_path / "x.msi", None, FACTS, host)
    assert r"- executable: C:\Host\host.exe" in prompt and '- args: ["/a", "b"]' in prompt
    assert "(ENV, INST, LOAD, UNIN)" in prompt
    missing = agent2.build_input(load_plan(), tmp_path, tmp_path / "x.msi", None, FACTS,
                                 agent2.HostLaunch(None, [], ["host.exe"], "^Host", "Doc1"))
    assert "NOT FOUND" in missing and "executed: false" in missing


def test_install_test_cannot_be_recorded_as_executed_without_running_the_installer(tmp_path):
    # run 20261013-175002: INST-001 was recorded as executed (exit code null) although msiexec never ran
    from mpagent.execute.guardrails import CallPolicy

    trace = Trace(tmp_path)
    policy = CallPolicy(tmp_path)
    obs = agent2.ObservationRecorder(tmp_path, plan(), CallRecorder(tmp_path, trace), trace, policy)
    exit_code = [KeyValue(key="install_exit_code", value=None)]
    assert "the installer hasn't run in this run" in obs.record("INST-001", True, exit_code, [], None)
    assert obs.record("INST-001", False, exit_code, [], "not reached") == "Recorded INST-001."
    policy.installed = True
    assert obs.record("INST-001", True, [KeyValue(key="install_exit_code", value=0)], [], None) == "Recorded INST-001."
