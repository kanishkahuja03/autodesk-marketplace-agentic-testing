"""Plans used by several tests, plus a stand-in for the Agent 1 LLM call."""

from mpagent.models import TestPlan


def good_plan_data() -> dict:
    """A plan for the real P&ID Exporter inputs that passes the self-check (quotes are real D1/F1 text)."""
    return {
        "app": {
            "name": "P&ID Connector Exporter Plant3D", "publisher": "Kleen Software GmbH", "version": "1.0.5",
            "host_id": "autocad-plant3d",
            "host_evidence": [{"doc": "D1", "line": 1, "quote": "This Autodesk® AutoCAD® Plant 3D™ plugin"}],
            "host_versions": ["2027"],
            "installer": {"file": "KleenSoftwareGmbHPIDConnectorExporterPlant3D.msi", "type": "msi",
                          "product_code": "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}", "signer_claimed": "Kleen Software GmbH"},
        },
        "summary": {"purpose": "Exports P&ID symbols to an interface file.", "install_footprint": [],
                    "commands_or_ui": [], "entry_point": None, "open_questions": []},
        "required_env": ["INSTALLER_PATH"],
        "testcases": [
            _test("INST-001", "INST", "properties.ProductName = P&ID Connector Exporter Plant3D", [],
                  ["Install ${INSTALLER_PATH} silently with a verbose log"], ["install_exit_code"],
                  [{"key": "install_exit_code", "check": "in", "value": None, "values": ["0", "3010"]}]),
            _test("INST-002", "INST", "properties.Manufacturer = Kleen Software GmbH", ["INST-001"],
                  ["Find the Uninstall entry for the product"], ["uninstall_entry_exists"],
                  [{"key": "uninstall_entry_exists", "check": "exists", "value": None, "values": None}]),
            _test("UNIN-001", "UNIN", "properties.ProductName = P&ID Connector Exporter Plant3D", ["INST-001"],
                  ["Uninstall through Programs and Features, then look for the Uninstall entry"],
                  ["uninstall_entry_exists"],
                  [{"key": "uninstall_entry_exists", "check": "not_exists", "value": None, "values": None}]),
        ],
    }


def _test(tid, category, quote, preconditions, steps, observe, expected) -> dict:
    return {"id": tid, "origin": "agent", "category": category, "title": f"{tid} title",
            "source": {"doc": "F1", "line": None, "quote": quote}, "preconditions": preconditions,
            "steps": steps, "observe": observe, "expected": expected, "priority": "P1"}


def fake_ask(*plans: dict):
    """An AskFn that returns the given plans in order, one per call, and records the conversations."""
    queue = [TestPlan.model_validate(p) for p in plans]
    calls: list = []

    def ask(conversation):
        calls.append(conversation)
        plan = queue.pop(0) if len(queue) > 1 else queue[0]
        history = conversation if isinstance(conversation, list) else [{"role": "user", "content": conversation}]
        return plan, history + [{"role": "assistant", "content": "<plan>"}]

    ask.calls = calls
    return ask


TAB_QUOTE = "you will receive a new tab called “P&ID Exporter”"  # real UserGuide.txt text (D2)


def load_plan_data() -> dict:
    """good_plan_data() plus the entry-point card and LOAD-001 (LOAD_TESTS_PLAN.md §4.1)."""
    data = good_plan_data()
    data["summary"]["entry_point"] = {
        "kind": "ribbon_tab", "label": "P&ID Exporter", "items": [], "use_context": None,
        "sources": [{"doc": "D2", "line": 7, "quote": TAB_QUOTE}]}
    load = _test("LOAD-001", "LOAD", "", ["LOAD-000"],
                 ["With a new document open, find the app's entry point and take a Screenshot of it"],
                 ["entry_point_seen"],
                 [{"key": "entry_point_seen", "check": "judged",
                   "value": "After installation the host shows a new tab called “P&ID Exporter”", "values": None}])
    load["source"] = {"doc": "D2", "line": 7, "quote": TAB_QUOTE}
    data["testcases"].insert(2, load)
    return data
