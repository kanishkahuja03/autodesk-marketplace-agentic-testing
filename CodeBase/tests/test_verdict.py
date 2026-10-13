"""Tests for the verdict engine and the report (ARCHITECTURE.md §5). Run with: uv run pytest"""

import json

import pytest
from plans import good_plan_data

from mpagent.design.agent1 import add_built_in_tests
from mpagent.execute.agent2 import RESULT_FILE
from mpagent.execute.observations import save_observation
from mpagent.execute.report import write_report
from mpagent.execute.verdict import check_one, evaluate, norm
from mpagent.models import (
    Check,
    Expectation,
    InstallerFacts,
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

    assert run.counts == {"PASS": 4, "FAIL": 0, "BLOCKED": 0, "ERROR": 0} and run.agent2_finished
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
