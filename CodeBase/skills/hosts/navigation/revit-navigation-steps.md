---
name: revit-navigation-steps
description: Step sequences for Autodesk Revit with the find-by-name UI tools (find_ui, click_ui, type_ui), with the exact element names. Host navigation only; it never names an app under test. Given to Agent 2 only when those tools are switched on.
---

# Autodesk Revit: steps with the name tools (Agent 2)

Exact names as Autodesk Revit 2027 shows them (English UI). Take **one Screenshot** after each step that changes the screen, as evidence. If a step answers "not found", use the fallback given for it. Each name search in this host takes several seconds, so don't search for what a Screenshot already shows you.

## 0. Start-up
- Right after starting the host: `wait_for_host(90)`. It skips the splash screen and returns as soon as a dialog opens or the main window is ready.
- For a dialog: Screenshot, answer it with `click_ui("<button>", control_type="Button")` by the host-interaction skill's dialog rules (for a prompt about loading the app under test: `"Load Once"`), then `wait_for_host` again.
- When it reports the main window ready, take **one Screenshot**. The **Home** screen is not in the UI tree: don't search in it.

## A. Open a model file (the copy you were given)
1. Press **Ctrl+O** (Windows-MCP `Shortcut`): the **Open** dialog appears.
2. `type_ui("File name:", "<full path of the copy's .rvt>", press_enter=True)`: the model starts opening.
3. `wait_for_host(90)`: it returns when the model is open (the main window title then ends with `- [<file name>.rvt - …]`) or when a dialog opens on the way. Answer a dialog as in 0; some offer their choices as large link buttons that the name tools may not find: click those by their coordinates from the Screenshot (Windows-MCP `Click`).
4. After answering a dialog, `wait_for_host` again until the model is open.

## B. A new, empty project
1. Press **Ctrl+N** (Windows-MCP `Shortcut`), then `wait_for_host(30)`: it reports the **New Project** dialog.
2. `click_ui("OK", control_type="Button")`: keeps the default template; the title then contains `Project1`.

## C. Project Browser: find and select views or sheets
1. To show only one kind of item: `click_ui("Sheets", control_type="Button")` (or `"Views"`, `"Schedules"`, `"All"`); the tree shows only that kind.
2. To find an item by name: `type_ui("Search", "<part of its name or number>")`; the tree shows the matching rows.
3. `click_ui("<row name>", control_type="ListItem")` selects a row (e.g. `"G000 - Cover"` for a sheet, `"L1"` for a floor plan view). To add more rows, Ctrl+click them by their coordinates, if Windows-MCP's `Click` can hold a key. If it can't, select one row; a test needs more than one row only when its claim says so.
4. `click_ui("<row name>", control_type="ListItem", double=True)` opens that view or sheet.

Use `find_ui("<name>", control_type="ListItem")` to list visible rows when you don't know their exact names. Only rows that are visible in the panel are found; filter or search first.

## D. Ribbon tabs and their buttons
1. `click_ui("<tab name>", control_type="Button")` shows a tab's panels (e.g. `"Add-Ins"`, or the tab a claim names).
2. `click_ui("<button label>", control_type="Button")` starts a command on the shown tab. Labels shown on two lines are found with the label's words separated by a space. Then `wait_for_host(30)`: it reports the window the command opens (or that nothing opened).
3. If a tab or button answers "not found", take a Screenshot and click by its coordinates (Windows-MCP `Click`).

## E. A save or export dialog opened by a feature
- `type_ui("File name:", "<full path in the test's output folder>", press_enter=True)`.
- If the host asks to replace an existing file, answer as the host-interaction skill says (never overwrite a file outside the run folder).

## F. Model elements: a 3D view, picking an element, its parameters
1. **Default 3D view:** `click_ui("View", control_type="Button")` shows the **View** tab; `click_ui("3D View", control_type="Button")` opens its drop-down; click **Default 3D View** in it (`click_ui("Default 3D View")`, or by its coordinates from a Screenshot). Then `wait_for_host(30)`; the main window title then ends with `- 3D View: {3D}]`. If a name answers "not found", click the house icon in the Quick Access Toolbar by its coordinates.
2. **Find the element on a Screenshot** (the drawing area is not in the UI tree). Zoom in with Windows-MCP `Scroll` over that spot if it is small; to see the whole model, type `ZF` with the drawing area focused.
3. **When a command asks you to pick an element** (read the status bar on the Screenshot): click the element by its coordinates (Windows-MCP `Click`), then `wait_for_host(30)` for the window the command opens next. If the wrong element was highlighted, press **Esc** and pick again; where elements overlap, hover and press **Tab** until the right one is highlighted, then click.
4. **Read its parameters:** with the element selected, take a Screenshot of the **Properties** palette; scroll the palette (Windows-MCP `Scroll` over it) to the group you need and take another. `find_ui("<parameter name>")` may find a parameter row by its name; if not, read it from the Screenshot.
5. **Esc** twice clears the selection.

## G. Undo and closing without saving
- **Ctrl+Z** (Windows-MCP `Shortcut`) undoes the last change in the model, only where the host-interaction skill asks you to undo.
- Never save. When closing asks "Save changes …?", `click_ui("No", control_type="Button")`.
