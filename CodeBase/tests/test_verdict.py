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


def plan() -> TestPlan:  # ENV-000, INST-001 (exit code), INST-002 (entry exists), UNIN-000 (leftovers), UNIN-001
    return add_built_in_tests(TestPlan.model_validate(good_plan_data()), FACTS)


def obs(tid, executed=True, **values):
    return Observation(test_id=tid, executed=executed, observed=[KeyValue(key=k, value=v) for k, v in values.items()],
                       evidence=[], notes=None)


def happy() -> list[Observation]:
    return [obs("ENV-000", preinstalled_entry_exists=False), obs("INST-001", install_exit_code=0),
            obs("INST-002", uninstall_entry_exists=True), obs("UNIN-001", uninstall_entry_exists=False),
            obs("UNIN-000", program_leftovers=0, settings_leftovers=0)]


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

    assert run.counts == {"PASS": 5, "FAIL": 0, "NEEDS_REVIEW": 0, "BLOCKED": 0, "ERROR": 0} and run.agent2_finished
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["counts"]["PASS"] == 5
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<title>Validation Report</title>" in html and 'id="UNIN-001"' in html
    assert "Agent 2 did not finish" not in html


def test_report_after_cut_off_run_marks_missing_tests_error(tmp_path):
    save_observation(tmp_path, happy()[0])
    run = write_report(plan(), tmp_path)  # no agent2_result.json: Agent 2 didn't finish
    assert not run.agent2_finished
    assert run.counts["ERROR"] == 1 and run.counts["BLOCKED"] == 3  # INST-001 ERROR, the rest blocked by it
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
    assert run.counts["NEEDS_REVIEW"] == 1 and run.counts["PASS"] == 6
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


def test_unin000_fails_on_program_leftovers_and_reports_settings_as_findings():
    leftover = r"Left behind after the uninstall (user settings): HKCU\Software\SomeApp"
    observations = happy()
    observations[-1] = obs("UNIN-000", program_leftovers=0, settings_leftovers=1).model_copy(
        update={"findings": [leftover]})
    r = {x.test_id: x for x in evaluate(plan(), observations, set())}
    assert r["UNIN-000"].status is Status.PASS and r["UNIN-000"].findings == [leftover]
    observations[-1] = obs("UNIN-000", program_leftovers=2, settings_leftovers=0)
    assert statuses(evaluate(plan(), observations, set()))["UNIN-000"] is Status.FAIL
    observations[3] = obs("UNIN-001", uninstall_entry_exists=True)  # the uninstall didn't work
    assert statuses(evaluate(plan(), observations, set()))["UNIN-000"] is Status.BLOCKED


def func_results(tmp_path, files: dict[str, bytes]):
    from mpagent.execute.verdict import output_dir
    from mpagent.models import Category, Citation, TestCase

    p = plan()
    p.testcases.append(TestCase(
        id="FUNC-001", origin="agent", category=Category.FUNC, title="Export writes a file",
        source=Citation(doc="D2", line=None, quote="export"), preconditions=["INST-001"], steps=["Run the feature"],
        observe=["output_files"], priority="P1",
        expected=[Expectation(key="output_files", check=Check.OUTPUT_CREATED, value=None, values=None)]))
    for name, data in files.items():
        path = output_dir(tmp_path, "FUNC-001") / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    observations = happy() + [obs("FUNC-001", output_files="Agent 2 says it saved out.json")]
    return {r.test_id: r for r in evaluate(p, observations, set(), UiContext(tmp_path, None))}["FUNC-001"]


def test_output_created_is_decided_from_the_test_folder_not_from_agent2(tmp_path):
    passed = func_results(tmp_path, {"out.json": b"{}", "sub/empty.txt": b""})
    assert passed.status is Status.PASS
    assert passed.checks[0].observed == "evidence/FUNC-001/out.json"
    assert passed.checks[0].reported == "Agent 2 says it saved out.json"


def test_output_created_fails_without_a_non_empty_file(tmp_path):
    assert func_results(tmp_path, {}).checks[0].observed == "no file"
    assert func_results(tmp_path, {}).status is Status.FAIL
    empty = func_results(tmp_path / "e", {"out.json": b""})
    assert empty.status is Status.FAIL and empty.checks[0].observed == "empty files only"


def func_plan() -> TestPlan:
    from test_selfcheck import func_plan_data
    return add_built_in_tests(TestPlan.model_validate(func_plan_data()), FACTS, host_process("autocad-plant3d"))


def func_judged_results(tmp_path, answers: list[Judgement]):
    """FUNC-001 with two judged claims and output_created; the judge answers per claim, in the claims' order
    (the claims are judged in parallel, so the answer is picked by the claim, not by call order)."""
    from mpagent.execute.verdict import output_dir

    out = output_dir(tmp_path, "FUNC-001")
    out.mkdir(parents=True)
    (out / "result.json").write_text('{"assets": []}', encoding="utf-8")
    o000 = ui_obs(tmp_path, "LOAD-000", HOST, host_started=True, document_opened=True, error_dialog_seen=False,
                  load_prompt_seen=False)
    o001 = ui_obs(tmp_path, "LOAD-001", HOST, entry_point_seen="a tab")
    ofunc = ui_obs(tmp_path, "FUNC-001", None, feature_result_seen="a file was saved", output_files="result.json")
    def judge(t, e, o):  # LOAD tests: PASS on their own screenshot; FUNC claims: the answer for that claim
        if t.category.value == "LOAD":
            return judgement(evidence=[next(x for x in o.evidence if x.endswith(".png"))])
        claims = [x for x in t.expected if x.check is Check.JUDGED]
        return answers[claims.index(e)]
    ui = UiContext(tmp_path, host_process("autocad-plant3d").main_window, judge)
    return {r.test_id: r for r in evaluate(func_plan(), happy() + [o000, o001, ofunc], set(), ui)}["FUNC-001"]


def test_every_judged_claim_of_a_func_test_is_kept_with_its_findings(tmp_path):
    first = judgement(evidence=["evidence/FUNC-001_Screenshot_1.png"], findings=["finding one"])
    second = judgement("NEEDS_REVIEW", evidence=["evidence/FUNC-001/result.json"], findings=["finding two"])
    r = func_judged_results(tmp_path, [first, second])  # the two FUNC claims
    assert r.status is Status.NEEDS_REVIEW
    assert [jc.claim for jc in r.judgements] == ["The “Export” button exports the entire drawing to a JSON file",
                                                 "The file holds assets and lines"]
    assert r.findings == ["finding one", "finding two"]
    assert r.judgements[1].judgement.evidence == ["evidence/FUNC-001/result.json"]  # an output file may be cited
    assert "evidence/FUNC-001/result.json" in r.evidence  # the produced file is attached to the result
    assert [c.ok for c in r.checks] == [True, False, True]  # the last check is output_created


def test_func_report_shows_each_claim(tmp_path):
    from mpagent.execute.observations import save_observation as save
    from mpagent.execute.verdict import output_dir

    for o in happy() + [ui_obs(tmp_path, "LOAD-000", HOST, host_started=True, document_opened=True,
                               error_dialog_seen=False, load_prompt_seen=False),
                        ui_obs(tmp_path, "LOAD-001", HOST, entry_point_seen="a tab"),
                        ui_obs(tmp_path, "FUNC-001", None, feature_result_seen="saved", output_files="r.json")]:
        save(tmp_path, o)
    output_dir(tmp_path, "FUNC-001").mkdir(parents=True)
    (output_dir(tmp_path, "FUNC-001") / "r.json").write_text("{}", encoding="utf-8")
    run = write_report(func_plan(), tmp_path,
                       judge=lambda t, e, o: judgement(evidence=[next(x for x in o.evidence if x.endswith(".png"))]))
    assert run.counts["PASS"] == 8
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "The file holds assets and lines" in html and 'href="evidence/FUNC-001/r.json"' in html


def test_a_tests_judged_claims_are_asked_at_the_same_time(tmp_path):
    import threading
    import time

    running, peak, lock = [0], [0], threading.Lock()

    def judge(t, e, o):
        if t.category.value == "LOAD":
            return judgement(evidence=[next(x for x in o.evidence if x.endswith(".png"))])
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.3)
        with lock:
            running[0] -= 1
        return judgement(evidence=["evidence/FUNC-001_Screenshot_1.png"])

    from mpagent.execute.verdict import output_dir

    output_dir(tmp_path, "FUNC-001").mkdir(parents=True)
    (output_dir(tmp_path, "FUNC-001") / "r.json").write_text("{}", encoding="utf-8")
    observations = happy() + [
        ui_obs(tmp_path, "LOAD-000", HOST, host_started=True, document_opened=True, error_dialog_seen=False,
               load_prompt_seen=False),
        ui_obs(tmp_path, "LOAD-001", HOST, entry_point_seen="a tab"),
        ui_obs(tmp_path, "FUNC-001", None, feature_result_seen="saved", output_files="r.json")]
    started = time.monotonic()
    r = {x.test_id: x for x in evaluate(func_plan(), observations, set(),
                                        UiContext(tmp_path, host_process("autocad-plant3d").main_window, judge))}
    assert peak[0] == 2 and time.monotonic() - started < 0.55  # two claims at once, not one after the other
    assert r["FUNC-001"].status is Status.PASS and len(r["FUNC-001"].judgements) == 2


def test_window_titles_read_by_code_decide_load000_like_a_snapshot(tmp_path):
    # UI_FIND_TOOLS_PLAN.md: the host's window titles, written in the Snapshot's UI-tree form
    path = tmp_path / "evidence"
    path.mkdir(exist_ok=True)
    (path / "LOAD-000_windows_ui.txt").write_text(
        'Host windows read by code\n\nUI Tree:\ndesktop\n├── window "Autodesk AutoCAD Plant 3D 2027 - [Drawing1.dwg]"\n',
        encoding="utf-8")
    o000 = obs("LOAD-000", host_started=True, document_opened=True, error_dialog_seen=False, load_prompt_seen=False)
    o000 = o000.model_copy(update={"evidence": ["evidence/LOAD-000_windows_ui.txt"]})
    ui = UiContext(tmp_path, host_process("autocad-plant3d").main_window, None)
    r = {x.test_id: x for x in evaluate(add_built_in_tests(TestPlan.model_validate(good_plan_data()), FACTS,
                                                         host_process("autocad-plant3d")), happy() + [o000], set(), ui)}
    assert r["LOAD-000"].status is Status.PASS
