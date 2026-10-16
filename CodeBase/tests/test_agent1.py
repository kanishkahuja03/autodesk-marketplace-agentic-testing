"""Tests for Agent 1's workflow with a stand-in LLM (no API calls). Run with: uv run pytest"""

import copy
from datetime import datetime

import pytest
from plans import fake_ask, good_plan_data

from mpagent.design.agent1 import (
    Agent1Error,
    add_built_in_tests,
    design_tests,
    instructions,
    load_plan,
)
from mpagent.design.evidence import facts_lines
from mpagent.models import (
    Document,
    InstallerFacts,
    InstallerInfo,
    IntakeManifest,
    Origin,
    TestPlan,
)


@pytest.fixture
def run_dir(tmp_path):
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "D1_Description.txt").write_text(
        "Note: This Autodesk® AutoCAD® Plant 3D™ plugin is part of the P&ID Connector workflow.\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def manifest(run_dir):
    return IntakeManifest(
        plugin="pid", input_dir=str(run_dir), created_at=datetime.now().astimezone(), files=[],
        documents=[Document(doc_id="D1", source_file="Description.txt", format="txt",
                            text_file="documents/D1_Description.txt", line_count=1, char_count=80)],
        installer=InstallerInfo(file="x.msi", type="msi", size_bytes=1, sha256="0"), estimated_tokens=20,
    )


@pytest.fixture
def facts():
    return InstallerFacts(installer_file="x.msi", installer_type="msi", sha256="0", properties={
        "ProductName": "P&ID Connector Exporter Plant3D", "Manufacturer": "Kleen Software GmbH",
        "ProductCode": "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}"})


def bad_plan_data() -> dict:
    data = copy.deepcopy(good_plan_data())
    data["testcases"][0]["source"]["quote"] = "an invented sentence"
    return data


def test_facts_are_rendered_as_key_value_lines(facts):
    lines = facts_lines(facts)
    assert "properties.ProductName = P&ID Connector Exporter Plant3D" in lines
    assert all(" = " in line for line in lines)


def test_instructions_contain_skill_and_host_catalogue():
    text = instructions()
    assert "# Test design (Agent 1)" in text
    assert "### host_id: autocad-plant3d" in text and "### host_id: none" in text


def test_good_plan_is_written_with_env000(run_dir, manifest, facts):
    ask = fake_ask(good_plan_data())
    plan = design_tests(run_dir, manifest, facts, ask)

    assert len(ask.calls) == 1
    assert plan.testcases[0].id == "ENV-000" and plan.testcases[0].origin is Origin.BUILT_IN
    assert all("ENV-000" in t.preconditions for t in plan.testcases if t.category.value == "INST")
    assert load_plan(run_dir / "testcases.yaml") == plan
    assert TestPlan.model_validate_json((run_dir / "testcases.json").read_text(encoding="utf-8")) == plan
    understanding = (run_dir / "understanding.md").read_text(encoding="utf-8")
    assert "# P&ID Connector Exporter Plant3D 1.0.5" in understanding and "| ENV-000 |" in understanding
    assert (run_dir / "trace.jsonl").exists()


def test_errors_are_sent_back_and_retry_succeeds(run_dir, manifest, facts):
    ask = fake_ask(bad_plan_data(), good_plan_data())
    design_tests(run_dir, manifest, facts, ask)
    assert len(ask.calls) == 2
    assert "quote not found" in ask.calls[1][-1]["content"]


def test_still_failing_after_two_retries_stops(run_dir, manifest, facts):
    ask = fake_ask(bad_plan_data())
    with pytest.raises(Agent1Error, match="self-check failed after 2 retries"):
        design_tests(run_dir, manifest, facts, ask)
    assert len(ask.calls) == 3
    assert (run_dir / "testcases.rejected.yaml").exists()
    assert not (run_dir / "testcases.yaml").exists()


def test_llm_error_becomes_agent1_error(run_dir, manifest, facts):
    def broken(_conversation):
        raise RuntimeError("401 invalid api key")
    with pytest.raises(Agent1Error, match="LLM call failed: RuntimeError: 401"):
        design_tests(run_dir, manifest, facts, broken)


def test_env000_uses_product_code(facts):
    plan = add_built_in_tests(TestPlan.model_validate(good_plan_data()), facts)
    assert "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}" in plan.testcases[0].steps[0]
    assert plan.testcases[0].expected[0].check.value == "not_exists"


def test_load000_is_added_for_hosts_with_host_process(facts):
    from plans import load_plan_data

    from mpagent.hostnotes import host_process

    hp = host_process("autocad-plant3d")
    plan = add_built_in_tests(TestPlan.model_validate(load_plan_data()), facts, hp)
    assert [t.id for t in plan.testcases] == ["ENV-000", "INST-001", "INST-002", "LOAD-000", "LOAD-001", "UNIN-000",
                                              "UNIN-001"]
    load000 = plan.testcases[3]
    assert load000.origin is Origin.BUILT_IN and load000.source is None
    assert load000.preconditions == ["INST-001"]  # only the INST test observing install_exit_code
    checks = {e.key: (e.check.value, e.value) for e in load000.expected}
    assert checks == {"host_started": ("window_in_ui", hp.main_window),
                      "document_opened": ("window_in_ui", hp.new_document),
                      "error_dialog_seen": ("not_exists", None)}
    assert "load_prompt_seen" in load000.observe  # reported, not checked
    no_host = add_built_in_tests(TestPlan.model_validate(good_plan_data()), facts)
    assert "LOAD-000" not in [t.id for t in no_host.testcases]


def test_func_tests_run_between_load_and_unin_in_agent1s_order(facts):
    from plans import _test, load_plan_data

    from mpagent.hostnotes import host_process

    data = load_plan_data()
    func = [_test(tid, "FUNC", "export", ["LOAD-000"], ["Run the feature"], ["what_happened"],
                  [{"key": "what_happened", "check": "judged", "value": "a file is written", "values": None}])
            for tid in ("FUNC-002", "FUNC-001")]  # Agent 1's order (F13) is kept, not the ID order
    data["testcases"] = func + data["testcases"]
    plan = add_built_in_tests(TestPlan.model_validate(data), facts, host_process("autocad-plant3d"))
    assert [t.id for t in plan.testcases] == ["ENV-000", "INST-001", "INST-002", "LOAD-000", "LOAD-001", "FUNC-002",
                                              "FUNC-001", "UNIN-000", "UNIN-001"]


def test_samples_listing_is_in_agent1s_input_and_features_in_understanding(run_dir, manifest, facts):
    from mpagent.design.samples import Sample

    data = copy.deepcopy(good_plan_data())
    data["summary"]["features"] = [{
        "name": "Export", "how_started": "a button", "context": None, "sample": None, "results": [], "sources": [],
        "action_class": 3, "testable": False, "reason": "point 2: it changes settings", "test_id": None}]
    ask = fake_ask(data)
    design_tests(run_dir, manifest, facts, ask, [Sample("MyProject", run_dir, [("a.dat", 5)], 1, 5)])
    assert '<sample name="MyProject" kind="folder" files="1" bytes="5">' in ask.calls[0]
    understanding = (run_dir / "understanding.md").read_text(encoding="utf-8")
    assert "## Features (1)" in understanding and "not testable: point 2: it changes settings" in understanding


def test_load000_opens_the_sample_when_a_func_test_needs_one(facts):
    from test_selfcheck import func_plan_data

    from mpagent.hostnotes import host_process

    hp = host_process("autocad-plant3d")
    plan = add_built_in_tests(TestPlan.model_validate(func_plan_data()), facts, hp)
    load000 = next(t for t in plan.testcases if t.id == "LOAD-000")
    assert "SampleProject" in load000.title and any("copy of the sample 'SampleProject'" in s for s in load000.steps)
    checks = {e.key: (e.check.value, e.value) for e in load000.expected}
    assert checks["host_started"] == ("window_in_ui", hp.main_window)
    assert checks["document_opened"][0] == "judged" and "in a P&ID project" in checks["document_opened"][1]
    assert checks["error_dialog_seen"] == ("not_exists", None)
