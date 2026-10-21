---
name: ui-find
description: How Agent 2 uses the find-by-name UI tools (find_ui, click_ui, type_ui) in the host's windows, and when it falls back to Windows-MCP. Generic for any host. Used by Agent 2 only, when the tools are switched on.
---

# Finding UI elements by name (Agent 2)

You have three fast tools that act on the **host's windows** by an element's **name**, without a Snapshot:

| Tool | Use it to |
|---|---|
| `find_ui(name, control_type)` | list the elements with that name (changes nothing) |
| `click_ui(name, control_type, double)` | click the first match; `double=True` to double-click (e.g. open a tree item) |
| `type_ui(name, text, control_type, press_enter)` | type into the first matching field (e.g. a dialog's file name box), optionally pressing Enter |

**How they match:** an element whose name is exactly `name` (ignoring upper/lower case) comes first; otherwise names that contain `name`. The **first match** is used. When a name occurs in several places, give `control_type` (e.g. `Button`, `TreeItem`, `ListItem`, `Edit`) so the first match is the right one.

## Rules
1. **Use these tools first** whenever you know an element's name: from the host's navigation steps, from the test's claim, or from a dialog you just saw. They take seconds; a Snapshot can take close to a minute in a large host.
2. **Fall back to Windows-MCP** (a Screenshot, or a Snapshot, then `Click` by label or coordinates) when:
   - a tool answers "not found", "not running", "took longer" or "failed";
   - the element isn't in the UI tree at all: some hosts draw tabs, toolbars or drawing areas themselves. If the navigation steps say an area needs a Screenshot, go there directly, without trying the name tools first.
3. **Check what happened** after a click that changes the screen: take a `Screenshot` (it is also the reviewer's evidence, as before). If the wrong thing opened, close it without saving and use the fallback.
4. **Dialogs and notices:** read their buttons in the Screenshot and answer with `click_ui("<button text>", control_type="Button")`; no Snapshot is needed for that.
5. **Screenshot before Snapshot:** to see what is on screen, take a Screenshot (a few seconds). Take a Snapshot only when a test needs one (e.g. the one its record requires) or when neither the name tools nor a Screenshot give you what you need.
6. **Areas marked "Screenshot only"** in the host's navigation steps: use neither the name tools nor a Snapshot there, **even when a claim names an element in that area**; a Screenshot and a click by its coordinates are the fastest way.
7. All other rules stay: the action classes, "never repeat the action while you wait", one restart per test, where results are saved. The same call with the same arguments works at most three times.
