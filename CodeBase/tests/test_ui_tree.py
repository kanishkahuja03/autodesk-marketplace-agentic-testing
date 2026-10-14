"""Tests for the Snapshot UI-tree reader (FUNCTIONAL_TESTS_PLAN.md L4, L11, L17). Run with: uv run pytest"""

import json
from pathlib import Path

from mpagent.execute import ui_tree

FIXTURES = Path(__file__).parent / "fixtures"
# UI-tree part of a real Windows-MCP 0.8.6 Snapshot (run 20261013-145150, Programs and Features)
REAL = (FIXTURES / "snapshot_programs_and_features.txt").read_text(encoding="utf-8")

# Made-up host snapshot in the same format. To be replaced by a real Plant 3D Snapshot (build step 1).
HOST = '''
    Opened Windows:
    P&ID Exporter - Microsoft Edge
    UI Tree:
    desktop
    ├── window "AutoCAD Plant 3D 2027 - [Drawing1.dwg]"
    │   ├── tab "Ribbon"
    │   │   ├── tab item "Home"  [action: click]
    │   │   └── (812,64) tab item "P&ID  Exporter"  [action: click]
    │   └── tab item "Drawing1"  [action: click]
    └── window "P&ID Connector Exporter | AutoCAD Plant 3D | Autodesk App Store - Microsoft Edge"
        └── (300,40) tab item "Search P&ID Exporter tools"  [action: click]
'''
MAIN = r"^(Autodesk )?AutoCAD Plant 3D \d{4}"


def test_real_snapshot_nodes_types_names_and_depths():
    nodes = ui_tree.nodes(REAL)
    assert nodes[0] == ui_tree.Node(depth=8, type="window", name="Programs and Features")
    assert ui_tree.Node(depth=16, type="button", name='Up to "Programs" (Alt + Up Arrow)') in nodes
    title = next(n for n in nodes if n.type == "edit" and n.name == "Title")  # trailing [value:"..."] is not the name
    assert title.depth > nodes[0].depth


def test_json_list_snapshot_text_is_decoded():
    # run 20261013-145150: the Snapshot text came as a JSON list of strings
    assert ui_tree.nodes(json.dumps([REAL])) == ui_tree.nodes(REAL)


def test_seen_in_ui_exact_name_inside_host_window_only():
    assert ui_tree.seen_in_ui([REAL], "^Programs and Features$", "control panel home") == "found"
    assert ui_tree.seen_in_ui([REAL], "^Programs and Features$", "Control Panel") == "found"  # a split button
    assert ui_tree.seen_in_ui([REAL], "^Programs and Features$", "Panel Home") == "not_found"  # no substrings
    assert ui_tree.seen_in_ui([HOST], MAIN, "P&ID Exporter") == "found"  # whitespace collapsed
    assert ui_tree.seen_in_ui([HOST], MAIN, "Search P&ID Exporter tools") == "not_found"  # in the browser window
    assert ui_tree.seen_in_ui([HOST], MAIN, "AutoCAD Plant 3D 2027 - [Drawing1.dwg]") == "not_found"  # the window itself
    assert ui_tree.seen_in_ui([REAL], MAIN, "P&ID Exporter") == "no_host_window"


def test_accelerator_ampersands_are_ignored():
    assert ui_tree.label_key("P&&ID  Exporter") == ui_tree.label_key("p&id exporter") == "pid exporter"
    assert ui_tree.seen_in_ui([REAL], "^Programs and Features$", "Help") == "found"  # button "&Help"


def test_window_in_ui_matches_host_title_or_names_inside_it():
    assert ui_tree.window_in_ui([HOST], MAIN, MAIN)
    assert ui_tree.window_in_ui([HOST], MAIN, r"Drawing\d+(\.dwg)?")
    assert not ui_tree.window_in_ui([HOST], MAIN, "Microsoft Edge")  # only in another window
    assert not ui_tree.window_in_ui([REAL], MAIN, MAIN)
