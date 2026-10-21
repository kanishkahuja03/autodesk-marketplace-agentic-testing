---
name: plant3d-navigation-steps
description: Step sequences for AutoCAD Plant 3D with the find-by-name UI tools (find_ui, click_ui, type_ui), with the exact element names. Host navigation only; it never names an app under test. Given to Agent 2 only when those tools are switched on.
---

# AutoCAD Plant 3D: steps with the name tools (Agent 2)

Exact names as AutoCAD Plant 3D 2027 shows them (English UI). Take **one Screenshot** after each step that changes the screen, as evidence. If a step answers "not found", use the fallback given for it.

## 0. Start-up
- After the main window is there, take **one Screenshot**. A plug-in notice or a host prompt may be open: answer it with `click_ui("<its button text>", control_type="Button")` (e.g. `"OK"`), by the host-interaction skill's dialog rules. No Snapshot is needed.
- The Project Manager panel and the Start page are then ready; go straight to A (or B).

## A. Open a project and a drawing in it (Project Manager)
Do steps 1–3 with the name tools **without a Snapshot first**; only if a step answers "not found", take a Screenshot and click by coordinates.
1. `click_ui("Open", control_type="Button")`: the button beside the project combo box at the top of the Project Manager; the project list opens. *(The quick-access toolbar also has an "Open"; if a file dialog opens instead, close it with Esc and click the button beside the combo box by coordinates.)*
2. `click_ui("Open...", control_type="ListItem")`: the "Select File" dialog opens.
3. `type_ui("File name:", "<full path of the copy's Project.xml>", press_enter=True)`: the project opens; the combo box shows its name.
4. `click_ui("P&ID Drawings", control_type="TreeItem", double=True)`: its folders appear (e.g. a folder per area).
5. `click_ui("<folder name>", control_type="TreeItem", double=True)`: its drawings appear.
6. `click_ui("<drawing name>", control_type="TreeItem", double=True)`: the drawing opens; its name appears in the main window title. Wait 3–5 seconds, then take a Screenshot.

Use `find_ui("<name>", control_type="TreeItem")` to list a folder's drawings when you don't know their names.

## B. Open a single drawing file
1. Click into the command line and type `OPEN` + Enter (Windows-MCP `Type` with its coordinates, as before).
2. `type_ui("File name:", "<full path of the .dwg>", press_enter=True)`.

## C. A save dialog opened by a feature
- `type_ui("File name:", "<full path in the test's output folder>", press_enter=True)`.
- If the host asks to replace an existing file, answer as the host-interaction skill says (never overwrite a file outside the run folder).

## D. Ribbon tabs and their buttons: Screenshot only
The ribbon (its tabs, panels, buttons and drop-downs, including tabs that plug-ins add) is **not in the UI tree**. **Screenshot only:** don't try the name tools there and don't take a Snapshot of it (it shows none of these items); take a Screenshot and click by its coordinates (Windows-MCP `Click`). This holds for the names a test's claim gives too (e.g. a plug-in's tab or button).

## E. Closing without saving
- `CLOSE` on the command line (Windows-MCP `Type`), then `click_ui("No", control_type="Button")` when asked "Save changes to …?".
