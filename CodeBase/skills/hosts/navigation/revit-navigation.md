---
name: revit-navigation
description: How to move around Autodesk Revit quickly - its Home screen, opening models, the Project Browser, the ribbon and its dialogs. Host navigation only; it never names an app under test. Given to Agent 2 only, next to the generic host-interaction skill, whose rules always come first.
---

# Navigating Autodesk Revit (Agent 2)

This file only tells you **where things are in the host** and the fastest way to reach them. The rules of the host-interaction skill (the action classes, what you may run, where to save, one restart per test) always apply. Nothing here names or describes the app under test: find the app's own UI from its claims.

## 1. Start-up: what you will see
- A **splash screen** comes first, for about 8 seconds; its title is just `Autodesk Revit 2027.3`, so a window with that title is **not** the main window yet. The main window title is like `Autodesk Revit 2027.3 - … - [Home]` while the **Home** screen is shown, and ends with `- [<file name>.rvt - <view kind>: <view name>]` once a model is open (e.g. `[sample.rvt - Sheet: G000 - Cover]`). Start-up takes 20–90 seconds; opening a large model takes another 30–60 seconds.
- Plug-ins may show their own dialogs or notices during start-up (handle them by the host-interaction skill, section 4). The host shows a **security prompt** before it loads an add-in it doesn't trust yet; a one-time load (**"Load Once"**) for the app under test is the answer with the smallest lasting effect, never "Always Load".
- The **Home** screen is a web page inside the main window: **none of its content is in the UI tree.** Take a Screenshot to see it. Don't click its recent models, cloud models or learning links; open files with **Ctrl+O** instead (section 2).

## 2. Opening a model file
- Press **Ctrl+O** (from the Home screen or with a model open): the **Open** dialog appears. Type the **full path of the `.rvt` file** into its file name box and confirm with Enter or **Open**. Leave the dialog's other options as they are.
- While the model opens, the host may ask about things the file refers to:
  - **"Unresolved References"** ("Revit could not find or read … references"): the model links to files that aren't there. Choose **"Ignore and continue opening the project"** (nothing changes until the model is saved). Its choices are large link buttons, not ordinary buttons; click them by their coordinates from a Screenshot.
  - A notice that the model was made with an **older version** and will be upgraded: the copy you were given lives in the run folder, so upgrading **that copy** is class 1. Never do it for anything outside the run folder.
  - Other notices: handle them by the host-interaction skill, section 4.
- The model opens in the view it was saved in; its name and the view appear in the main window title.

## 3. A new, empty project
- **File** tab (the blue tab at the left of the ribbon) → **New** → **Project**, or **Ctrl+N**: the **New Project** dialog asks for a template. Keep the default template and **Project**, and confirm with **OK**.
- The new project's title contains `Project1` (the number may differ).

## 4. Project Browser (views, sheets, schedules)
- The **Project Browser** is a panel, usually docked at the left below **Properties**; its title is `Project Browser - <file name>`. It is a web page inside the host, and its tree **is** in the UI tree: its rows are `ListItem` elements named like the view or sheet. **Only the rows currently visible are in the tree**; scroll the panel (or use its search) to reach others.
- At its top are buttons that filter the tree: **All**, **Views**, **Legends**, **Schedules**, **Sheets**, **Families**, **Groups**, **Links**, and a **Search** box. Filtering and searching only change what the panel shows (class 0). Sheets are listed by number and name (e.g. `G000 - Cover`).
- **Select** rows with a click; add rows with **Ctrl**+click, a range with **Shift**+click. Commands that work "on the selected views or sheets" use this selection, so select first, then start the command.
- **Double-click** a row to open that view or sheet (class 1).
- Never rename (F2, slow double-click), delete, drag or drop rows unless the test's feature does it, and never use the right-click menu's Delete, Rename or Duplicate unless the test names them.
- Keep the Project Browser **docked**: don't drag it out or close it (some plug-ins need it docked). If it is hidden, **View** tab → **User Interface** → **Project Browser** shows it again.

## 5. Ribbon, tabs and panels
- The **ribbon** is the band of tabs below the title bar: **File**, **Architecture**, **Structure**, …, **Add-Ins**, **Modify**. Plug-ins add their own tab (usually after the host's tabs, before **Modify**) or a panel on **Add-Ins**.
- **The tab names are in the UI tree as `Button` elements** named like the tab. Click a tab once to show its panels. Don't double-click a tab name: that changes how the ribbon is shown (a lasting setting).
- **Only the active tab's panels and buttons are in the UI tree.** A button whose label is shown on two lines has a **line break in its name** (e.g. a label shown as "Duplicate / Views" is named `Duplicate⏎Views`), so a search for the label with a space between its words may not find it.
- Buttons may hide more commands behind a small arrow below or beside them; open it only to show what is in it.
- The tab **Modify** (and contextual tabs that appear when something is selected) change with the selection; that is normal.

## 6. Dialogs and file dialogs
- Dialogs of the host and of plug-ins are separate windows of the host; their buttons are usually in the UI tree.
- The host's open and save dialogs have a **file name** box. Type the **full path** (folder and file name) there and confirm; this is faster than browsing folders.
- When a save or export dialog proposes a folder outside the run folder, replace it by typing the full path into the test's output folder.

## 7. Model elements: seeing, picking, reading their parameters
- **The drawing area is not in the UI tree**; elements in it are found only on a Screenshot and clicked by their coordinates.
- **A 3D view** shows all model elements: **View** tab → **3D View** → **Default 3D View** (or the house icon in the Quick Access Toolbar at the top). Opening a view is class 1. In a plan view, elements of other levels or disciplines may not be visible.
- **Zoom** with the mouse wheel over the drawing area, or type **ZF** (zoom to fit) while the drawing area has focus: class 0. Don't change **Visibility/Graphics** (VV) or the view's properties: that changes the view in the model.
- **Hovering** over an element highlights it and shows a tooltip with its category, family and type. Where elements overlap, **Tab** cycles the highlight between them; a click then selects the highlighted one.
- **When a command asks you to pick an element**, the prompt is in the **status bar** at the bottom left of the main window (e.g. "Select an element …"). Click the element in the drawing area; **Esc** cancels the pick. Pick an element whose category fits what the command is for.
- **Selecting** an element (a click, class 0) shows its parameters in the **Properties** palette, usually docked at the left above the Project Browser: at its top the type, below it the instance parameters in groups (e.g. **Identity Data**, **Constraints**, **Dimensions**). Scroll the palette to reach a group; take a Screenshot to read values. If the palette is hidden: **View** tab → **User Interface** → **Properties**. **Edit Type** shows the type's parameters; close it with **Cancel**.
- **Esc** (once or twice) clears the selection.

## 8. Changes in the model, closing
- A feature that changes the model (new or renamed views or sheets, new or changed parameter values) changes only the open copy in the run folder, as long as it is **not saved**. Never press **Ctrl+S** or use **Save** / **Save As** on a model you didn't create in the run folder.
- **Ctrl+Z** undoes the last change in the model (class 2); use it only where the host-interaction skill asks you to undo.
- Closing the host asks to save changed models: answer **No**. At the end of the tests the host is killed anyway (host-interaction skill).

## 9. Saving time
- The host's UI tree is large: each search takes several seconds. Use the Project Browser's **Search** box or filter buttons instead of scrolling through long lists.
- Use a Screenshot for the Home screen and the drawing area (neither is in the UI tree).
- After opening a model or a view, one short `Wait` (3–5 seconds) is usually enough before the next look.
