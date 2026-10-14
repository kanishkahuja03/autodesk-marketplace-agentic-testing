"""Tests for the verdict engine and the report (ARCHITECTURE.md §5). Run with: uv run pytest"""

import json

import pytest
from plans import good_plan_data, load_plan_data
from test_ui_tree import HOST

from mpagent.design.agent1 import add_built_in_tests
from mpagent.execute.agent2 import RESULT_FILE
from mpagent.execute.observations import save_observation
from mpagent.execute.report import write_report
from mpagent.execute.verdict import UiContext, check_one, evaluate, norm
from mpagent.hostnotes import host_process
from mpagent.models import (
    Check,
    Expectation,
    InstallerFacts,
    Judgement,
    KeyValue,
    Observation,
    Status,
    TestPlan,
)

FACTS = InstallerFacts(installer_file="x.msi", installer_type="msi", sha256="0",
                       properties={"ProductCode": "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}", "ProductName": "App"})


def plan() -> TestPlan:  # ENV-000, INST-001 (exit code), INST-002 (entry exists), UNIN-001 (entry gone)
    return add_built_in_tests(TestPlan.model_validate(good_plan_data()), FACTS)


def obs(tid, executed=True, **values):
    return Observation(test_id=tid, executed=executed, observed=[KeyValue(key=k, value=v) for k, v in values.items()],
                       evidence=[], notes=None)


def happy() -> list[Observation]:
    return [obs("ENV-000", preinstalled_entry_exists=False), obs("INST-001", install_exit_code=0),
            obs("INST-002", uninstall_entry_exists=True), obs("UNIN-001", uninstall_entry_exists=False)]


def statuses(results):
    return {r.test_id: r.status for r in results}


def test_norm_makes_numbers_bools_and_text_comparable():
    assert norm(0) == norm("0") == norm(0.0) == "0"
    assert norm(True) == "true" and norm(" Valid ") == "valid"


@pytest.mark.parametrize("check, value, values, observed, ok", [
    (Check.EQUALS, "1.0.5", None, "1.0.5", True),
    (Check.EQUALS, "1.0.5", None, "1.0.6", False),
    (Check.NOT_EQUALS, "NotSigned", None, "Valid", True),
    (Check.IN, None, ["0", "3010"], 3010, True),
    (Check.IN, None, ["0", "3010"], 1603, False),
    (Check.EXISTS, None, None, True, True),
    (Check.EXISTS, None, None, False, False),
    (Check.NOT_EXISTS, None, None, False, True),
    (Check.CONTAINS, "Kleen Software", None, "CN=Kleen Software GmbH, O=Kleen", True),
    (Check.MATCHES, r"^1\.0\.\d+$", None, "1.0.5", True),
    (Check.MATCHES, r"^2\.", None, "1.0.5", False),
])
def test_each_check_type(check, value, values, observed, ok):
    assert check_one(Expectation(key="k", check=check, value=value, values=values), observed) is ok


def test_happy_path_all_pass():
    assert set(statuses(evaluate(plan(), happy(), {"INSTALLER_PATH"})).values()) == {Status.PASS}


def test_failed_check_is_fail_and_dependents_are_blocked():
    observations = happy()
    observations[1] = obs("INST-001", install_exit_code=1603)
    s = statuses(evaluate(plan(), observations, set()))
    assert s["INST-001"] is Status.FAIL
    assert s["INST-002"] is Status.BLOCKED and s["UNIN-001"] is Status.BLOCKED  # both depend on INST-001


def test_already_installed_blocks_install_tests():
    observations = happy()
    observations[0] = obs("ENV-000", preinstalled_entry_exists=True)
    s = statuses(evaluate(plan(), observations, set()))
    assert s["ENV-000"] is Status.FAIL and s["INST-001"] is Status.BLOCKED


def test_missing_observation_null_value_and_not_executed_are_error():
    observations = [o for o in happy() if o.test_id != "UNIN-001"]
    observations[1] = obs("INST-001", install_exit_code=None)
    observations[2] = obs("INST-002", executed=False, uninstall_entry_exists=True)
    results = {r.test_id: r for r in evaluate(plan(), observations, None)}
    assert results["INST-001"].status is Status.ERROR and "no value observed" in results["INST-001"].notes
    assert results["INST-002"].status is Status.BLOCKED  # depends on INST-001, which isn't PASS
    assert results["UNIN-001"].status is Status.BLOCKED


def test_not_executed_is_error():
    observations = happy()
    observations[3] = obs("UNIN-001", executed=False, uninstall_entry_exists=None)
    assert statuses(evaluate(plan(), observations, set()))["UNIN-001"] is Status.ERROR


def test_unresolved_placeholder_blocks_only_when_agent2_reported_env():
    data = good_plan_data()
    data["required_env"].append("PLUGIN_DIR")
    data["testcases"][1]["steps"].append(r"Look in ${PLUGIN_DIR}")
    p = add_built_in_tests(TestPlan.model_validate(data), FACTS)
    assert statuses(evaluate(p, happy(), set()))["INST-002"] is Status.BLOCKED
    assert statuses(evaluate(p, happy(), {"PLUGIN_DIR"}))["INST-002"] is Status.PASS
    assert statuses(evaluate(p, happy(), None))["INST-002"] is Status.PASS


def test_report_files_are_written(tmp_path):
    for o in happy():
        save_observation(tmp_path, o)
    (tmp_path / RESULT_FILE).write_text(json.dumps({"done": True, "env": []}), encoding="utf-8")
    run = write_report(plan(), tmp_path)

    assert run.counts == {"PASS": 4, "FAIL": 0, "NEEDS_REVIEW": 0, "BLOCKED": 0, "ERROR": 0} and run.agent2_finished
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["counts"]["PASS"] == 4
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<title>Validation Report</title>" in html and 'id="UNIN-001"' in html
    assert "Agent 2 did not finish" not in html


def test_report_after_cut_off_run_marks_missing_tests_error(tmp_path):
    save_observation(tmp_path, happy()[0])
    run = write_report(plan(), tmp_path)  # no agent2_result.json: Agent 2 didn't finish
    assert not run.agent2_finished
    assert run.counts["ERROR"] == 1 and run.counts["BLOCKED"] == 2  # INST-001 ERROR, the rest blocked by it
    assert "Agent 2 did not finish" in (tmp_path / "report.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- LOAD: code checks and judged claims (L11, L20-L25)
NO_DOCUMENT = HOST.replace("[Drawing1.dwg]", "Start").replace('tab item "Drawing1"', 'tab item "Start"')
SHOT = "evidence/LOAD-001_Screenshot_1.png"


def load_plan() -> TestPlan:  # ENV-000, INST-001, INST-002, LOAD-000, LOAD-001 (judged), UNIN-001
    return add_built_in_tests(TestPlan.model_validate(load_plan_data()), FACTS, host_process("autocad-plant3d"))


def ui_obs(run_dir, tid, snapshot: str | None, screenshot=True, **values):
    evidence = []
    (run_dir / "evidence").mkdir(exist_ok=True)
    if snapshot is not None:
        (run_dir / "evidence" / f"{tid}_Snapshot_ui.txt").write_text(snapshot, encoding="utf-8")
        evidence.append(f"evidence/{tid}_Snapshot_ui.txt")
    if screenshot:
        evidence.append(f"evidence/{tid}_Screenshot_1.png")
    o = obs(tid, **values)
    return o.model_copy(update={"evidence": evidence})


def judgement(verdict="PASS", evidence=(SHOT,), findings=()) -> Judgement:
    return Judgement(verdict=verdict, shown="a new tab 'P&ID Connector'", differences=[], findings=list(findings),
                     evidence=list(evidence), reason="the tab is in the screenshot")


def stand_in_judge(answer: Judgement | Exception, calls: list | None = None):
    def judge(t, e, o):
        if calls is not None:
            calls.append((t.id, e.value, list(o.evidence)))
        if isinstance(answer, Exception):
            raise answer
        return answer
    return judge


def load_results(tmp_path, judge=None, load000_snapshot=HOST, screenshot=True, **load001_values):
    o000 = ui_obs(tmp_path, "LOAD-000", load000_snapshot, host_started=True, document_opened=True,
                  error_dialog_seen=False, load_prompt_seen=False)
    o001 = ui_obs(tmp_path, "LOAD-001", HOST, screenshot=screenshot,
                  **(load001_values or {"entry_point_seen": "a tab 'P&ID Connector'"}))
    ui = UiContext(tmp_path, host_process("autocad-plant3d").main_window, judge)
    return {r.test_id: r for r in evaluate(load_plan(), happy() + [o000, o001], set(), ui)}


def test_the_judge_decides_the_claim_from_the_screenshots(tmp_path):
    calls = []
    r = load_results(tmp_path, stand_in_judge(judgement(), calls))
    assert r["LOAD-000"].status is Status.PASS and r["LOAD-001"].status is Status.PASS
    assert r["UNIN-001"].status is Status.PASS  # UNIN never depends on LOAD
    assert calls == [("LOAD-001", "After installation the host shows a new tab called “P&ID Exporter”",
                      ["evidence/LOAD-001_Snapshot_ui.txt", SHOT])]
    assert r["LOAD-001"].judgement.evidence == [SHOT] and r["LOAD-001"].notes.startswith("judge: ")


def test_judge_verdicts_and_findings(tmp_path):
    # L23: only the app's own text matches -> PASS with a documentation-mismatch finding
    mismatch = "Documentation mismatch: the documents say 'P&ID Exporter', the app shows 'P&ID Connector'"
    r = load_results(tmp_path, stand_in_judge(judgement(findings=[mismatch])))["LOAD-001"]
    assert r.status is Status.PASS and r.findings == [mismatch]
    assert load_results(tmp_path, stand_in_judge(judgement("FAIL")))["LOAD-001"].status is Status.FAIL
    assert load_results(tmp_path, stand_in_judge(judgement("NEEDS_REVIEW")))["LOAD-001"].status is Status.NEEDS_REVIEW


def test_judge_guards(tmp_path):
    # L25: never without screenshots, never on a screenshot not attached to the test, a failed call is ERROR
    r = load_results(tmp_path, stand_in_judge(judgement()), screenshot=False)["LOAD-001"]
    assert r.status is Status.ERROR and "never judged from notes alone" in r.notes
    r = load_results(tmp_path, stand_in_judge(judgement(evidence=["evidence/999_Screenshot_1.png"])))["LOAD-001"]
    assert r.status is Status.ERROR and "named no screenshot attached" in r.notes
    assert load_results(tmp_path, stand_in_judge(judgement(evidence=["LOAD-001_Screenshot_1.png"])))[
        "LOAD-001"].status is Status.PASS  # the bare file name is fine
    r = load_results(tmp_path, stand_in_judge(TimeoutError("slow")))["LOAD-001"]
    assert r.status is Status.ERROR and "judge call failed (TimeoutError: slow)" in r.notes
    r = load_results(tmp_path, None)["LOAD-001"]
    assert r.status is Status.ERROR and "no judge available" in r.notes


def test_agent2_value_is_not_needed_for_a_judged_claim(tmp_path):
    r = load_results(tmp_path, stand_in_judge(judgement()), entry_point_seen=None)["LOAD-001"]
    assert r.status is Status.PASS and r.checks[0].reported is None


def test_window_in_ui_not_seen_is_fail_and_blocks_load001(tmp_path):
    r = load_results(tmp_path, stand_in_judge(judgement()), load000_snapshot=NO_DOCUMENT)
    assert r["LOAD-000"].status is Status.FAIL
    assert [c.key for c in r["LOAD-000"].checks if not c.ok] == ["document_opened"]
    assert r["LOAD-001"].status is Status.BLOCKED


def test_report_shows_the_judgement_and_findings(tmp_path):
    for o in happy():
        save_observation(tmp_path, o)
    save_observation(tmp_path, ui_obs(tmp_path, "LOAD-000", HOST, host_started=True, document_opened=True,
                                      error_dialog_seen=False, load_prompt_seen=False))
    save_observation(tmp_path, ui_obs(tmp_path, "LOAD-001", HOST, entry_point_seen="a tab 'P&ID Connector'"))
    mismatch = "Documentation mismatch: the documents say 'P&ID Exporter', the app shows 'P&ID Connector'"
    run = write_report(load_plan(), tmp_path, judge=stand_in_judge(judgement("NEEDS_REVIEW", findings=[mismatch])))
    assert run.counts["NEEDS_REVIEW"] == 1 and run.counts["PASS"] == 5
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert 'class="status NEEDS_REVIEW"' in html and "Decided by the LLM judge" in html
    assert "<h2>Findings</h2>" in html and "Documentation mismatch" in html


def test_report_shows_host_crash_records(tmp_path):
    from mpagent.execute.host import CRASH_EVENTS_FILE

    (tmp_path / "evidence").mkdir()
    (tmp_path / CRASH_EVENTS_FILE).write_text("[2026-10-13T17:50:46] Application Error\nFaulting module name: X.dll",
                                              encoding="utf-8")
    write_report(plan(), tmp_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "The host crashed during this run" in html and "Faulting module name: X.dll" in html
