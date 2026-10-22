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
    assert any("not in the catalogue" in e for e in errors_for(changed(lambda d: d["app"].update(host_id="no-such-host"))))
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


# ---------------------------------------------------------------- LOAD rules (LOAD_TESTS_PLAN.md §4.1)
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


# ---------------------------------------------------------------- FUNC rules (FUNC_TESTS_PLAN.md §4.1, F1, F13, F16)
FUNC_DOC = ("For the export to take place, the user must be in a P&ID project and have a drawing open.\n"
            "The “Export” button is used to export the entire drawing to a JSON file.\n"
            "The exported data are assets and lines, as well as all associated P&ID properties.")
FUNC_SOURCES = LOAD_SOURCES + [Source("D3", "Guide.txt", FUNC_DOC)]
RESULT_1 = "export the entire drawing to a JSON file"
RESULT_2 = "The exported data are assets and lines"


def _cite(quote: str) -> dict:
    return {"doc": "D3", "line": None, "quote": quote}


def func_plan_data() -> dict:
    """load_plan_data() plus one testable feature card (with a sample) and its FUNC-001."""
    from plans import _test

    data = load_plan_data()
    data["summary"]["features"] = [{
        "name": "Export", "how_started": "The “Export” button", "context": "in a P&ID project and have a drawing open",
        "sample": "SampleProject", "results": [_cite(RESULT_1), _cite(RESULT_2)],
        "sources": [_cite("The “Export” button is used to export"), _cite("must be in a P&ID project")],
        "action_class": 1, "testable": True, "reason": None, "test_id": "FUNC-001"}]
    func = _test("FUNC-001", "FUNC", "", ["LOAD-000"], ["Open the given context, start “Export”, save the result"],
                 ["feature_result_seen", "output_files"],
                 [{"key": "feature_result_seen", "check": "judged", "value": "The “Export” button exports the entire "
                   "drawing to a JSON file", "values": None},
                  {"key": "feature_result_seen", "check": "judged", "value": "The file holds assets and lines",
                   "values": None},
                  {"key": "output_files", "check": "output_created", "value": None, "values": None}])
    func["source"] = _cite("The “Export” button is used to export")
    data["testcases"].insert(3, func)
    return data


def func_errors(edit=lambda d: None, samples=("SampleProject",), load_hosts=("autocad-plant3d",)) -> list[str]:
    data = copy.deepcopy(func_plan_data())
    edit(data)
    return check_plan(TestPlan.model_validate(data), FUNC_SOURCES, HOSTS, load_hosts, samples)


def _card(d: dict) -> dict:
    return d["summary"]["features"][0]


def _func(d: dict) -> dict:
    return next(t for t in d["testcases"] if t["id"] == "FUNC-001")


def test_good_func_plan_passes():
    assert func_errors() == []


def test_feature_card_quotes_and_sample_are_checked():
    errors = func_errors(lambda d: _card(d)["results"].append(_cite("exports to Excel")))
    assert any("results[2]: quote not found in D3" in e for e in errors)
    assert any("SampleProject" in e and "not in the samples listing (none are available)" in e
               for e in func_errors(samples=()))


def test_feature_card_input_file_is_checked_against_the_listing():
    def with_input(d):
        _card(d)["input_file"] = "export.json"
    assert any("input_file 'export.json' is not in the input files listing (none are available)" in e
               for e in func_errors(with_input))
    data = copy.deepcopy(func_plan_data())
    with_input(data)
    assert check_plan(TestPlan.model_validate(data), FUNC_SOURCES, HOSTS, ("autocad-plant3d",), ("SampleProject",),
                      ("export.json",)) == []


def test_input_files_are_listed_in_their_own_block(tmp_path):
    from mpagent.design.samples import list_samples, render_input_files

    (tmp_path / "export.json").write_bytes(b"{}")
    text = render_input_files(list_samples(tmp_path / "export.json"))
    assert text.startswith("<input_files>\n") and '<input_file name="export.json" kind="file" files="1"' in text
    assert "No input files are available" in render_input_files([])


def test_testable_card_needs_its_test_and_untestable_card_a_reason():
    assert any("test_id must name the FUNC test" in e for e in func_errors(lambda d: _card(d).update(test_id=None)))

    def untestable(d):
        _card(d).update(testable=False, reason=None)
    errors = func_errors(untestable)
    assert any("'reason' must say which point fails" in e for e in errors)
    assert any("test_id must be null" in e for e in errors)
    assert any("FUNC-001: no testable feature card" in e for e in errors)
    assert any("class 3 (lasting)" in e for e in func_errors(lambda d: _card(d).update(action_class=3)))


def test_one_judged_claim_per_documented_result():
    errors = func_errors(lambda d: _func(d)["expected"].pop(1))
    assert any("one 'judged' claim per documented result" in e and "(2 results, 1 claims)" in e for e in errors)


def test_func_preconditions_checks_and_quoted_names():
    errors = func_errors(lambda d: _func(d).update(preconditions=["LOAD-000", "LOAD-001"]))
    assert any("FUNC-001: preconditions must be ['LOAD-000']" in e for e in errors)
    errors = func_errors(lambda d: _func(d)["expected"].append(
        {"key": "feature_result_seen", "check": "equals", "value": "x", "values": None}))
    assert any("uses only 'judged' claims and 'output_created'" in e for e in errors)
    errors = func_errors(lambda d: _func(d)["expected"][0].update(value="The “Export all” button works"))
    assert any("the claim names 'Export all'" in e for e in errors)


def test_output_created_only_in_func_and_unin_never_depends_on_func():
    def misuse(d):
        unin = next(t for t in d["testcases"] if t["id"] == "UNIN-001")
        unin["preconditions"].append("FUNC-001")
        unin["expected"].append({"key": "uninstall_entry_exists", "check": "output_created", "value": None,
                                 "values": None})
    errors = func_errors(misuse)
    assert any("UNIN-001: check 'output_created' is only for FUNC tests" in e for e in errors)
    assert any("never on LOAD or FUNC" in e for e in errors)


def test_func_tests_run_in_class_order_and_need_a_host_with_host_process():
    def class2_first(d):
        second = copy.deepcopy(_func(d))
        second["id"] = "FUNC-002"
        d["testcases"].insert(4, second)
        d["summary"]["features"].append({**copy.deepcopy(_card(d)), "test_id": "FUNC-002"})
        _card(d)["action_class"] = 2
    assert any("FUNC-002: FUNC tests run in class order" in e for e in func_errors(class2_first))
    assert any("no FUNC support" in e for e in func_errors(load_hosts=()))


def test_samples_folder_is_listed_not_opened(tmp_path):
    from mpagent.design.samples import list_samples, render_samples

    # SAMPLES_DIR is one sample (Q14): a folder (e.g. a project) or a single file
    (tmp_path / "Project" / "Docs").mkdir(parents=True)
    (tmp_path / "Project" / "Docs" / "a.dat").write_bytes(b"12345")
    (tmp_path / "Project" / "main.cfg").write_bytes(b"1")
    (tmp_path / "single.dat").write_bytes(b"123")
    [project] = list_samples(tmp_path / "Project")
    assert (project.name, project.path, project.total_files, project.total_bytes) == ("Project", tmp_path / "Project",
                                                                                       2, 6)
    assert project.files == [("Docs/a.dat", 5), ("main.cfg", 1)]
    text = render_samples([project])
    assert '<sample name="Project" kind="folder" files="2" bytes="6">' in text and "Docs/a.dat (5 bytes)" in text
    [single] = list_samples(tmp_path / "single.dat")
    assert single.files == [("single.dat", 3)] and 'kind="file"' in render_samples([single])
    assert list_samples(None) == [] and list_samples(tmp_path / "missing") == []
    assert "No samples are available" in render_samples([])
