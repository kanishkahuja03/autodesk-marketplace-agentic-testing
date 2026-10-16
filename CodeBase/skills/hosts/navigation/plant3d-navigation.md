---
name: plant3d-navigation
description: How to move around AutoCAD Plant 3D quickly - its start page, Project Manager, opening projects and drawings, the ribbon, the command line and its dialogs. Host navigation only; it never names an app under test. Given to Agent 2 only, next to the generic host-interaction skill, whose rules always come first.
---

# Navigating AutoCAD Plant 3D (Agent 2)

This file only tells you **where things are in the host** and the fastest way to reach them. The rules of the host-interaction skill (the action classes, what you may run, where to save, one restart per test) always apply. Nothing here names or describes the app under test: find the app's own UI from its claims.

## 1. Start-up: what you will see
- The main window title is like `Autodesk AutoCAD Plant 3D 2027 - … - [Start]` while the **Start** page is shown, and ends with `- [<file name>.dwg]` once a drawing is open. For `WaitFor`, use the plain text `AutoCAD Plant 3D` (it matches text contained in the title, never a regular expression). Startup takes 30–90 seconds.
- Plug-ins may show their own dialogs or notices during start-up (handle them by the host-interaction skill, section 4). The host can also show a security prompt about loading a file; a one-time load ("Load Once") for the app under test is the answer with the smallest lasting effect, never "Always Load".
- The **Start** page (a tab of the main window) has, on its left, the buttons **Open...** and **New**, and the lists **Recent**, **Autodesk Projects** and **Learning**. Don't click the recent files or the learning links.

## 2. Project Manager (projects and their drawings)
- The **Project Manager** is a panel, usually docked at one side of the main window. Its items are in the Snapshot's UI tree, so a Snapshot without vision is enough to find them.
- At its top, a **combo box** shows the current project, and next to it an **Open** button. The host remembers the last project from an earlier session, so the project shown may not be the one your test needs; always check its name.
- To open a project (a folder with a `Project.xml` file): open the combo box's list and choose **Open...**, then in the file dialog type the **full path of that `Project.xml`** into the file name box and confirm. Opening another project only switches the panel to it.
- Below the combo box is the project's tree: the project's name, then **P&ID Drawings**, **Plant 3D Drawings**, and further groups (e.g. **Orthographic Drawings**, **Isometric Drawings**, **Related Files**). Each group may hold folders, and the folders hold the drawings. Expand a group or folder with a click on its arrow or a double-click on its name; **double-click a drawing to open it**.
- To find a drawing of a certain kind, look in the group of that kind (e.g. a P&ID drawing is under **P&ID Drawings**), and in its folders.
- If the host says that the project or drawing was made with an older version or must be upgraded or converted, the copy you were given lives in the run folder, so converting **that copy** is class 1. Never do it for anything outside the run folder.

## 3. Opening a single drawing file (no project)
- Fastest: type `OPEN` on the command line (section 5) and press Enter, or use **Open...** on the Start page. In the file dialog, type the **full path of the `.dwg` file** into the file name box and confirm.
- A drawing opened this way opens on its own tab; its title appears in the main window title.

## 4. Ribbon, tabs and panels
- The **ribbon** is the band of tabs below the title bar. Plug-ins add their own tabs there, usually after the host's own tabs. Which tabs appear depends on the **kind of drawing that is active** and on the current workspace: a tab may only appear once a drawing of the right kind is open.
- **Ribbon tabs and their buttons are usually not in the UI tree.** Take a `Screenshot` (or a Snapshot with vision) to read their names, and click by the coordinates from that screenshot.
- If the ribbon shows only tab names, click a tab name once to show its buttons for a moment. Don't double-click a tab name: that changes how the ribbon is shown (a lasting setting).
- Buttons on a ribbon panel may hide more commands behind a small arrow below or beside them; open it only to show what is in it.
- Don't switch the workspace (the gear in the status bar at the bottom right): it is a lasting setting.

## 5. The command line
- The command line is at the bottom of the drawing area (`Command:`). Click into it, `Type` a command name and press Enter. It is usually faster than hunting through menus.
- Useful host commands: `OPEN` (open a drawing), `CLOSE` (close the active drawing), `PROJECTMANAGER` (show the Project Manager if it is hidden). Press `Esc` (twice) to cancel a running command.
- Never type commands that change settings or system variables, and never `SAVE`, `QSAVE` or `SAVEAS` on a drawing you didn't create in the run folder.

## 6. File dialogs
- The host's open and save dialogs have a **file name** box. Type the **full path** (folder and file name) there and confirm with Enter or the dialog's **Open** / **Save** button; this is faster than browsing folders.
- When a save dialog proposes a folder outside the run folder, replace it by typing the full path into the test's output folder.

## 7. Closing documents and the host
- To close the active drawing without saving: `CLOSE` on the command line, and answer the question "Save changes to …?" with **No**.
- Closing the main window may ask to save every open drawing: answer **No** for each. At the end of the tests the host is killed anyway (host-interaction skill).

## 8. Saving time
- Take a Snapshot **without vision** to find the Project Manager and dialog elements; use a Screenshot only for the ribbon and the drawing area.
- Don't wait longer than needed: after opening a drawing, one short `Wait` (2–5 seconds) is usually enough before the next Snapshot.
