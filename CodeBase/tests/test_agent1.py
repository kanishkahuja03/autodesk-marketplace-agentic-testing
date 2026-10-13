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
