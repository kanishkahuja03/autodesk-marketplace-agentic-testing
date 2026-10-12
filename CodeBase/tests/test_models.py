"""Tests for the test-plan and execution models (ARCHITECTURE.md §6). Run with: uv run pytest"""

import io

import pytest
from agents import AgentOutputSchema
from pydantic import ValidationError
from ruamel.yaml import YAML

from mpagent.models import (
    Agent2Result,
    Check,
    Observation,
    Origin,
    Status,
    TestPlan,
    TestResult,
)

SAMPLE_PLAN_YAML = r"""
app:
  name: "P&ID Connector Exporter Plant3D"
  publisher: "Kleen Software GmbH"
  version: "1.0.5"
  host_id: autocad-plant3d
  host_evidence:
    - { doc: "D1", line: 1, quote: "This Autodesk® AutoCAD® Plant 3D™ plugin" }
  host_versions: ["2027"]
  installer:
    file: "KleenSoftwareGmbHPIDConnectorExporterPlant3D.msi"
    type: msi
    product_code: "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}"
    signer_claimed: "Kleen Software GmbH"
summary:
  purpose: "Exports P&ID symbols with position data and properties to an interface file."
  install_footprint: ['%AppData%\Autodesk\ApplicationPlugins\pidExport.bundle']
  commands_or_ui: ["P&ID Exporter ribbon tab"]
  open_questions: ["ALLUSERS=1 but files go to %AppData%: which user profile?"]
required_env: [PLUGIN_DIR, INSTALLER_PATH]
testcases:
  - id: ENV-000
    origin: built-in
    category: ENV
    title: "Plug-in is not installed before the test"
    source: null
    preconditions: []
    steps: []
    observe: [preinstalled_entry_exists]
    expected: [{ key: preinstalled_entry_exists, check: not_exists, value: null, values: null }]
    priority: P1
  - id: INST-001
    origin: agent
    category: INST
    title: "Silent install finishes successfully"
    source: { doc: "D2", line: 3, quote: "Run the installer" }
    preconditions: [ENV-000]
    steps: ['Install ${INSTALLER_PATH} silently with a verbose log']
    observe: [install_exit_code]
    expected: [{ key: install_exit_code, check: in, value: null, values: ["0", "3010"] }]
    priority: P1
  - id: UNIN-001
    origin: agent
    category: UNIN
    title: "Bundle folder is removed"
    source: { doc: "I1", line: null, quote: "pidExport.bundle" }
    preconditions: [INST-001]
    steps: ['Check that ${PLUGIN_DIR}\pidExport.bundle no longer exists']
    observe: [bundle_dir_exists]
    expected: [{ key: bundle_dir_exists, check: not_exists, value: null, values: null }]
    priority: P2
"""


def _yaml() -> YAML:
    y = YAML(typ="safe", pure=True)
    y.default_flow_style = False
    return y


def _load_plan() -> TestPlan:
    return TestPlan.model_validate(_yaml().load(SAMPLE_PLAN_YAML))


def test_plan_loads_from_yaml():
    plan = _load_plan()
    assert [t.id for t in plan.testcases] == ["ENV-000", "INST-001", "UNIN-001"]
    assert plan.testcases[0].origin is Origin.BUILT_IN and plan.testcases[0].source is None
    assert plan.testcases[1].expected[0].check is Check.IN
    assert plan.summary.install_footprint == [r"%AppData%\Autodesk\ApplicationPlugins\pidExport.bundle"]


def test_plan_round_trips_through_yaml_and_json():
    plan = _load_plan()
    buf = io.StringIO()
    _yaml().dump(plan.model_dump(mode="json"), buf)
    assert TestPlan.model_validate(_yaml().load(buf.getvalue())) == plan
    assert TestPlan.model_validate_json(plan.model_dump_json()) == plan


def test_plan_rejects_unknown_check():
    data = _yaml().load(SAMPLE_PLAN_YAML)
    data["testcases"][1]["expected"][0]["check"] = "greater_than"
    with pytest.raises(ValidationError):
        TestPlan.model_validate(data)


@pytest.mark.parametrize("model", [TestPlan, Agent2Result])
def test_agent_outputs_are_strict_schemas(model):
    assert AgentOutputSchema(model).is_strict_json_schema()


def test_observation_and_result_round_trip():
    obs = Observation.model_validate({
        "test_id": "INST-001", "executed": True,
        "observed": [{"key": "install_exit_code", "value": 0}],
        "evidence": ["evidence/INST-001_install.log"], "notes": None,
    })
    assert Observation.model_validate_json(obs.model_dump_json()) == obs
    assert obs.observed[0].value == 0  # ints stay ints (not "0")

    result = TestResult.model_validate({
        "test_id": "INST-001", "origin": "agent", "status": "PASS",
        "checks": [{"key": "install_exit_code", "check": "in", "expected": ["0", "3010"], "observed": 0, "ok": True}],
        "evidence": obs.evidence, "notes": None,
    })
    assert result.status is Status.PASS
    assert TestResult.model_validate_json(result.model_dump_json()) == result
