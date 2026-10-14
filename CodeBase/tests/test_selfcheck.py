"""Tests for Agent 1's self-check rules (ARCHITECTURE.md §4, D24). Run with: uv run pytest"""

import copy

from plans import TAB_QUOTE, good_plan_data, load_plan_data

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


def test_env_tests_may_not_observe_app_install_keys():
    # run 20261013-145150: a "host is installed" ENV test observed uninstall_entry_exists and failed falsely
    env = {"id": "ENV-001", "origin": "agent", "category": "ENV", "title": "Host installed",
           "source": {"doc": "D1", "line": 1, "quote": "AutoCAD® Plant 3D™ plugin"}, "preconditions": [],
           "steps": ["Check the host"], "observe": ["uninstall_entry_exists"],
           "expected": [{"key": "uninstall_entry_exists", "check": "exists", "value": None, "values": None}],
           "priority": "P1"}
    errs = errors_for(changed(lambda d: d["testcases"].append(env)))
    assert any("ENV-001: ENV tests check the machine/host" in e for e in errs)
    env["observe"] = ["host_installed"]
    env["expected"][0]["key"] = "host_installed"
    assert errors_for(changed(lambda d: d["testcases"].append(env))) == []


# ---------------------------------------------------------------- LOAD rules (FUNCTIONAL_TESTS_PLAN.md §4.1)
LOAD_SOURCES = SOURCES + [Source("D2", "UserGuide.txt", "After installation, " + TAB_QUOTE + ", which contains two "
                                                        "new buttons.\nThe “Export” button is used to export.")]


def load_errors(edit=lambda d: None, load_hosts=("autocad-plant3d",)) -> list[str]:
    data = copy.deepcopy(load_plan_data())
    edit(data)
    return check_plan(TestPlan.model_validate(data), LOAD_SOURCES, HOSTS, load_hosts)


def _load001(d: dict) -> dict:
    return next(t for t in d["testcases"] if t["id"] == "LOAD-001")


LOAD002_QUOTE = "The “Export” button is used to export"


def with_load002(d: dict) -> None:
    """The entry point's documented items, and LOAD-002 claiming they are reachable."""
    d["summary"]["entry_point"]["items"] = ["Export"]
    d["summary"]["entry_point"]["sources"].append({"doc": "D2", "line": 10, "quote": LOAD002_QUOTE})
    load002 = {**copy.deepcopy(_load001(d)), "id": "LOAD-002", "preconditions": ["LOAD-000", "LOAD-001"],
               "source": {"doc": "D2", "line": 10, "quote": LOAD002_QUOTE}}
    load002["expected"][0]["value"] = "The entry point contains a button called “Export”"
    d["testcases"].insert(3, load002)


def test_good_load_plan_passes():
    assert load_errors() == []
    assert load_errors(with_load002) == []  # the items are documented, so LOAD-002 is there too


def test_load002_is_required_when_items_are_documented():
    errors = load_errors(lambda d: d["summary"]["entry_point"].update(items=["Export"]))
    assert any("also write LOAD-002" in e for e in errors)


def test_claim_names_must_come_from_the_quotes():
    # names in a claim are checked against its quotes; the guide doesn't name 'Info'
    assert any("the claim names 'Info'" in e for e in load_errors(
        lambda d: _load001(d)["expected"][0].update(value="The tab has a button 'Info'")))
    assert load_errors(lambda d: _load001(d)["expected"][0].update(
        value="The host shows the app's new tab, called 'P&ID Exporter'")) == []  # apostrophe in "app's" is no quote


def test_load_needs_a_host_with_host_process():
    assert any("no LOAD support" in e for e in load_errors(load_hosts=()))


def test_entry_point_names_must_be_quoted():
    # the user guide names only "Export"; "Info" is not in the documents
    errors = load_errors(lambda d: d["summary"]["entry_point"].update(items=["Export", "Info"]))
    assert any("'Info' is not in any quote" in e for e in errors)


def test_load_test_shape_rules():
    # a command or own window isn't visible right after start; no entry point at all can't be checked either
    for edit in (lambda d: d["summary"]["entry_point"].update(kind="command"),
                 lambda d: d["summary"].update(entry_point=None)):
        assert any("needs summary.entry_point with kind" in e for e in load_errors(edit))
    assert any("preconditions must be ['LOAD-000']" in e
               for e in load_errors(lambda d: _load001(d).update(preconditions=["INST-001"])))
    assert any("exactly one expected check, 'judged'" in e
               for e in load_errors(lambda d: _load001(d)["expected"][0].update(check="equals")))

    def three(d):
        with_load002(d)
        d["testcases"].insert(4, {**_load001(d), "id": "LOAD-003"})
    assert any("at most two LOAD tests" in e for e in load_errors(three))


def test_load000_is_reserved_and_ui_checks_only_in_load():
    def write_load000(d):
        _load001(d)["id"] = "LOAD-000"
    assert any("LOAD-000 is reserved" in e for e in load_errors(write_load000))

    def ui_check_in_inst(d):
        d["testcases"][1]["expected"][0].update(check="window_in_ui", value="x")
    assert any("only for LOAD tests" in e for e in load_errors(ui_check_in_inst))

    def window_in_ui(d):
        _load001(d)["expected"][0].update(check="window_in_ui")
    assert any("reserved for the built-in LOAD-000" in e for e in load_errors(window_in_ui))


def test_unin_may_not_depend_on_load():
    def depend(d):
        d["testcases"][-1]["preconditions"].append("LOAD-000")
    assert any("never on LOAD" in e for e in load_errors(depend))


# ---------------------------------------------------------------- citation fixes from run 20261013-172934
def test_misplaced_quote_says_which_source_has_it():
    data = changed(lambda d: d["app"]["host_evidence"][0].update(doc="F1"))  # the quote is really in D1
    errors = errors_for(data)
    assert any("this text is in D1, not F1: set doc to D1" in e for e in errors)
    assert any("(copy the text exactly)" in e
               for e in errors_for(changed(lambda d: d["app"]["host_evidence"][0].update(quote="invented text"))))


def test_quote_mark_kinds_inside_a_quote_do_not_matter():
    # the user guide has “P&ID Exporter”; the model wrote 'P&ID Exporter' and ‘P&ID Exporter’
    for variant in ("'P&ID Exporter'", "‘P&ID Exporter’", '"P&ID Exporter"'):
        quote = TAB_QUOTE.replace("“P&ID Exporter”", variant)
        assert load_errors(lambda d, q=quote: d["summary"]["entry_point"]["sources"][0].update(quote=q)) == []
    assert any("quote not found" in e for e in load_errors(
        lambda d: d["summary"]["entry_point"]["sources"][0].update(quote=TAB_QUOTE.replace("new tab", "new ribbon"))))


def test_load001_is_required_for_a_visible_entry_point():
    def drop(d):
        d["testcases"] = [t for t in d["testcases"] if t["id"] != "LOAD-001"]
    assert any("write the LOAD test LOAD-001" in e for e in load_errors(drop))

    def drop_command(d):
        drop(d)
        d["summary"]["entry_point"]["kind"] = "command"
    assert load_errors(drop_command) == []  # not visible after start: no LOAD test needed
    assert load_errors(drop, load_hosts=()) == []  # host without host_process
