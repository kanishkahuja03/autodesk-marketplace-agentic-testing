"""Tests for Agent 1's self-check rules (ARCHITECTURE.md §4, D24). Run with: uv run pytest"""

import copy

from plans import good_plan_data

from mpagent.design.evidence import Source
from mpagent.design.selfcheck import check_plan, normalise
from mpagent.models import TestPlan

SOURCES = [
    Source("D1", "Description.txt", "Note: This Autodesk® AutoCAD® Plant 3D™ plugin is part of the P&ID\nConnector workflow."),
    Source("F1", "installer facts", "properties.ProductName = P&ID Connector Exporter Plant3D\n"
                                    "properties.Manufacturer = Kleen Software GmbH"),
]
HOSTS = ["autocad-plant3d", "none"]


def errors_for(data: dict) -> list[str]:
    return check_plan(TestPlan.model_validate(data), SOURCES, HOSTS)


def changed(edit) -> dict:
    data = copy.deepcopy(good_plan_data())
    edit(data)
    return data


def test_good_plan_passes():
    assert errors_for(good_plan_data()) == []


def test_normalise_ignores_case_whitespace_and_quote_marks():
    assert normalise('  "Kleen   SOFTWARE\nGmbH." ') == "kleen software gmbh"


def test_quote_spanning_lines_is_found():
    data = changed(lambda d: d["app"]["host_evidence"][0].update(quote="part of the P&ID Connector workflow"))
    assert errors_for(data) == []


def test_invented_quote_is_rejected():
    data = changed(lambda d: d["testcases"][0]["source"].update(quote="supports Windows 7"))
    assert any("INST-001.source: quote not found in F1" in e for e in errors_for(data))


def test_unknown_source_id_is_rejected():
    data = changed(lambda d: d["testcases"][0]["source"].update(doc="D9"))
    assert any("cites 'D9'" in e for e in errors_for(data))


def test_undeclared_placeholder_is_rejected():
    data = changed(lambda d: d.update(required_env=[]))
    assert any("${INSTALLER_PATH}" in e for e in errors_for(data))


def test_missing_basic_coverage_is_rejected():
    data = changed(lambda d: d.update(testcases=[t for t in d["testcases"] if t["id"] != "UNIN-001"]))
    assert any("missing required UNIN test" in e for e in errors_for(data))


def test_agent_may_not_write_env000_or_built_in():
    def edit(d):
        d["testcases"][1]["id"] = "ENV-000"
        d["testcases"][0]["origin"] = "built-in"
    errs = errors_for(changed(edit))
    assert any("ENV-000 is reserved" in e for e in errs)
    assert any("INST-001: origin must be 'agent'" in e for e in errs)


def test_unknown_precondition_and_cycle_are_rejected():
    def edit(d):
        d["testcases"][0]["preconditions"] = ["INST-002"]  # INST-002 already depends on INST-001
        d["testcases"][2]["preconditions"] = ["INST-009"]
    errs = errors_for(changed(edit))
    assert any("precondition INST-009" in e for e in errs)
    assert any("cycle" in e for e in errs)


def test_expectation_rules():
    def edit(d):
        d["testcases"][0]["expected"][0]["values"] = None          # 'in' without values
        d["testcases"][1]["expected"].append({"key": "display_version", "check": "equals", "value": None, "values": None})
    errs = errors_for(changed(edit))
    assert any("needs a non-empty 'values'" in e for e in errs)
    assert any("'display_version' is not in observe" in e for e in errs)
    assert any("check 'equals' on 'display_version' needs a 'value'" in e for e in errs)


def test_host_rules():
    assert any("not in the catalogue" in e for e in errors_for(changed(lambda d: d["app"].update(host_id="revit"))))
    assert any("host_evidence is empty" in e for e in errors_for(changed(lambda d: d["app"].update(host_evidence=[]))))
    unknown = changed(lambda d: d["app"].update(host_id="unknown", host_evidence=[]))
    assert any("'unknown' but summary.open_questions" in e for e in errors_for(unknown))


def test_user_profile_path_is_rejected():
    data = changed(lambda d: d["testcases"][1]["steps"].append(r"Look in C:\Users\kanishk\AppData\Roaming"))
    assert any("hard-coded user profile path" in e for e in errors_for(data))
