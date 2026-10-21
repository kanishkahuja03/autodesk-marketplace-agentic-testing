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


def test_screenshots_agent2_names_are_kept_as_picks_without_duplicates(tmp_path):
    trace = Trace(tmp_path)
    calls = CallRecorder(tmp_path, trace)
    first = calls.record("Screenshot", {}, mcp_result(SimpleNamespace(type="image", data=PNG, mimeType="image/png")))
    calls.record("Screenshot", {}, mcp_result(SimpleNamespace(type="image", data=PNG, mimeType="image/png")))
    obs = agent2.ObservationRecorder(tmp_path, plan(), calls, trace)

    obs.record("UNIN-001", True, [KeyValue(key="uninstall_entry_exists", value=False)], ["evidence\\001_Screenshot_1.png"], None)

    saved = load_observations(tmp_path)[0]
    assert first == ["evidence/001_Screenshot_1.png"]
    assert saved.picked == ["evidence/001_Screenshot_1.png"]
    assert saved.evidence == ["evidence/001_Screenshot_1.png", "evidence/002_Screenshot_1.png"]


def test_screenshot_results_tell_the_model_the_saved_file_names():
    from mcp.types import CallToolResult, ImageContent, TextContent

    from mpagent.execute.windows_mcp import with_saved_names

    result = CallToolResult(content=[ImageContent(type="image", data=PNG, mimeType="image/png")])
    named = with_saved_names(result, ["evidence/007_Screenshot_1.png", "evidence/007_Snapshot_ui.txt"])
    assert named.content[-1] == TextContent(type="text", text="Saved as evidence: evidence/007_Screenshot_1.png")
    assert len(result.content) == 1  # a copy; the original is unchanged
    assert with_saved_names(result, ["evidence/008_Snapshot_ui.txt"]) is result  # no image, no note


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


# ---------------------------------------------------------------- LOAD (LOAD_TESTS_PLAN.md L5, L9, L17)
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


def test_load_tests_need_their_evidence_before_recording(tmp_path):
    # LOAD-000 is decided from the UI tree (needs a Snapshot); LOAD-001 is judged from screenshots (L25)
    trace = Trace(tmp_path)
    calls = CallRecorder(tmp_path, trace)
    obs = agent2.ObservationRecorder(tmp_path, load_plan(), calls, trace)
    seen = [KeyValue(key="entry_point_seen", value="a tab 'P&ID Connector'")]

    assert "Take a Screenshot of each state" in obs.record("LOAD-001", True, seen, [], None)
    calls.record("Snapshot", {}, mcp_result(SimpleNamespace(type="text", text="UI Tree:\n")))
    assert "Take a Screenshot of each state" in obs.record("LOAD-001", True, seen, [], None)  # a tree isn't enough
    calls.record("Screenshot", {}, mcp_result(SimpleNamespace(type="image", data=PNG, mimeType="image/png")))
    assert obs.record("LOAD-001", True, seen, [], None) == "Recorded LOAD-001."
    assert load_observations(tmp_path)[0].evidence == ["evidence/001_Snapshot_ui.txt", "evidence/002_Screenshot_1.png"]

    host = [KeyValue(key=k, value=v) for k, v in (("host_started", True), ("document_opened", True),
                                                   ("error_dialog_seen", False), ("load_prompt_seen", False))]
    assert "Take a Snapshot of the host window first" in obs.record("LOAD-000", True, host, [], None)
    assert obs.record("LOAD-000", False, host, [], "install failed") == "Recorded LOAD-000."  # not executed: fine


def test_host_interaction_skill_and_host_block_only_with_load(tmp_path):
    assert "# Host interaction: LOAD and FUNC tests" in agent2.instructions("autocad-plant3d", with_host_interaction=True)
    assert "# Host interaction" not in agent2.instructions("autocad-plant3d")
    assert agent2.host_launch(plan()) is None  # no LOAD tests in the plan
    host = agent2.HostLaunch(executable=r"C:\Host\host.exe", args=["/a", "b"], processes=["host.exe"],
                             main_window="^Host", new_document="Doc1")
    prompt = agent2.build_input(load_plan(), tmp_path, tmp_path / "x.msi", None, FACTS, host)
    assert r"- executable: C:\Host\host.exe" in prompt and '- args: ["/a", "b"]' in prompt
    assert "(ENV, INST, LOAD, FUNC, UNIN)" in prompt
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


def func_plan() -> TestPlan:
    from test_selfcheck import func_plan_data

    from mpagent.design.agent1 import add_built_in_tests
    from mpagent.hostnotes import host_process
    return add_built_in_tests(TestPlan.model_validate(func_plan_data()), FACTS, host_process("autocad-plant3d"))


def test_func_tests_get_an_output_folder_and_a_copy_of_their_sample(tmp_path):
    from mpagent.execute.context import func_block, prepare_func_tests

    samples = tmp_path / "SampleProject"  # SAMPLES_DIR is the sample itself (Q14)
    (samples / "Docs").mkdir(parents=True)
    (samples / "Docs" / "a.dat").write_bytes(b"data")
    run_dir = tmp_path / "run"
    [setup] = prepare_func_tests(func_plan(), run_dir, samples)
    assert setup.output == run_dir / "evidence" / "FUNC-001" and setup.output.is_dir() and not any(setup.output.iterdir())
    assert setup.context == run_dir / "context" / "SampleProject"
    assert (setup.context / "Docs" / "a.dat").read_bytes() == b"data"
    block = func_block([setup])
    assert f"open this copy of the sample 'SampleProject' through the host's UI: {setup.context}" in block
    assert f"output folder (save everything the app produces in this test here): {setup.output}" in block

    [missing] = prepare_func_tests(func_plan(), tmp_path / "run2", None)
    assert missing.context is None and "SAMPLES_DIR is not set" in missing.problem
    assert "record this test with executed: false" in func_block([missing])
    assert func_block(prepare_func_tests(plan(), tmp_path / "run3", samples)) == ""  # no FUNC tests


def test_func_tests_start_the_host_and_raise_the_limits(tmp_path, monkeypatch):
    settings = replace(load_settings(), agent2_timeout_min=40, agent2_max_turns=150, agent2_func_min_per_test=10,
                       agent2_func_turns_per_test=40)
    assert agent2.limits(func_plan(), settings) == (50, 190)
    assert agent2.limits(plan(), settings) == (40, 150)
    p = func_plan()
    p.testcases = [t for t in p.testcases if t.category.value != "LOAD"]
    monkeypatch.setattr(agent2.host_mod, "resolve", lambda hp: "resolved")
    assert agent2.host_launch(p) == "resolved"  # FUNC tests alone also need the host


def test_load000_gets_the_sample_copy_and_func_tests_reuse_it(tmp_path):
    from mpagent.execute.context import func_block, prepare_func_tests

    sample = tmp_path / "SampleProject"
    sample.mkdir()
    (sample / "a.dat").write_bytes(b"x")
    setups = prepare_func_tests(func_plan(), tmp_path / "run", sample)
    block = func_block(setups, "SampleProject")
    assert block.startswith("LOAD-000 context: open this copy of the sample 'SampleProject'")
    assert "the copy of the sample 'SampleProject' that LOAD-000 opened" in block
    missing = func_block(prepare_func_tests(func_plan(), tmp_path / "run2", None), "SampleProject")
    assert "record LOAD-000 with executed: false" in missing


def test_ui_find_tools_add_their_skill_only_when_switched_on():
    # UI_FIND_TOOLS_PLAN.md: with the switch off, Agent 2's instructions are exactly as before
    before = agent2.instructions("autocad-plant3d", with_host_interaction=True)
    assert agent2.instructions("autocad-plant3d", with_host_interaction=True, with_ui_find=False) == before
    assert "# Finding UI elements by name" not in before and "steps with the name tools" not in before
    on = agent2.instructions("autocad-plant3d", with_host_interaction=True, with_ui_find=True)
    assert on.startswith(before.split("\n\n")[0]) and "# Finding UI elements by name" in on
    assert "# AutoCAD Plant 3D: steps with the name tools" in on
    assert "# Finding UI elements by name" not in agent2.instructions("autocad-plant3d", with_ui_find=True)  # no host


def test_ui_find_switch_is_on_by_default_and_can_be_turned_off(monkeypatch):
    monkeypatch.delenv("AGENT2_UI_FIND_TOOLS", raising=False)
    assert load_settings().agent2_ui_find_tools in (True, False)  # .env may set it
    monkeypatch.setenv("AGENT2_UI_FIND_TOOLS", "false")
    assert load_settings().agent2_ui_find_tools is False
    monkeypatch.setenv("AGENT2_UI_FIND_TOOLS", "true")
    assert load_settings().agent2_ui_find_tools is True


def test_reasoning_effort_is_only_sent_when_set(monkeypatch):
    base = load_settings()
    assert agent2.agent2_model_settings(replace(base, agent2_reasoning_effort=None)).reasoning is None  # as before
    low = agent2.agent2_model_settings(replace(base, agent2_reasoning_effort="low"))
    assert low.reasoning.effort == "low" and low.parallel_tool_calls is False
    monkeypatch.setenv("AGENT2_REASONING_EFFORT", "fast")
    with pytest.raises(Exception, match="AGENT2_REASONING_EFFORT must be one of"):
        load_settings()


def test_load000_can_be_recorded_with_window_titles_read_by_code(tmp_path):
    from mpagent.design.agent1 import add_built_in_tests
    from mpagent.hostnotes import host_process

    trace = Trace(tmp_path)
    calls = CallRecorder(tmp_path, trace)
    (tmp_path / "evidence").mkdir()
    lplan = add_built_in_tests(TestPlan.model_validate(good_plan_data()), FACTS, host_process("autocad-plant3d"))
    values = [KeyValue(key=k, value=v) for k, v in (("host_started", True), ("document_opened", True),
                                                    ("error_dialog_seen", False), ("load_prompt_seen", False))]
    without = agent2.ObservationRecorder(tmp_path, lplan, calls, trace)
    assert "took no Snapshot" in without.record("LOAD-000", True, values, [], None)  # as before
    no_window = agent2.ObservationRecorder(tmp_path, lplan, calls, trace, window_titles=list)
    assert "took no Snapshot" in no_window.record("LOAD-000", True, values, [], None)  # nothing read: Snapshot
    rec = agent2.ObservationRecorder(tmp_path, lplan, calls, trace, window_titles=lambda: ["Host - [Drawing1.dwg]"])
    assert rec.record("LOAD-000", True, values, [], None) == "Recorded LOAD-000."
    saved = load_observations(tmp_path)[0]
    assert saved.evidence == ["evidence/LOAD-000_windows_ui.txt"]
    assert 'window "Host - [Drawing1.dwg]"' in (tmp_path / saved.evidence[0]).read_text(encoding="utf-8")
