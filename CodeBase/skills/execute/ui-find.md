---
name: ui-find
description: How Agent 2 uses the find-by-name UI tools (find_ui, click_ui, type_ui) and wait_for_host in the host's windows, and when it falls back to Windows-MCP. Generic for any host. Used by Agent 2 only, when the tools are switched on.
---

# Finding UI elements by name (Agent 2)

You have four fast tools that work on the **host's windows**, without a Snapshot:

| Tool | Use it to |
|---|---|
| `find_ui(name, control_type)` | list the elements with that name (changes nothing): first the text read on the screen, else the UI tree |
| `click_ui(name, control_type, double)` | click the element with that name; `double=True` to double-click (e.g. open a tree item) |
| `type_ui(name, text, control_type, press_enter)` | type into the first matching field (e.g. a dialog's file name box), optionally pressing Enter |
| `wait_for_host(timeout_s)` | wait until the host shows something to act on; it returns **the moment** a new dialog opens (with its title, buttons and text), the main window is ready, or the host closes (changes nothing) |

**Waiting: let `wait_for_host` watch, don't guess.** Right after you start the host, and after any action that may open a window (opening a file, starting a command), call `wait_for_host` instead of `WaitFor`, `Wait` or a Screenshot taken to check. It looks at the host's windows twice a second, so you never sit thinking while a dialog waits. Then act on what it reports at once:
- **"A dialog opened" / "A dialog is waiting for an answer":** take a `Screenshot` (evidence), decide by the host-interaction skill's dialog rules, and answer with `click_ui("<button>", control_type="Button")` using a button name exactly as it listed. A button it just listed is clicked at once, where it was seen, even while the host is busy. Then `wait_for_host` again.
- **"The host is ready":** go on with the test.
- **"Still no ready main window or dialog":** take a Screenshot to see what the host shows; call it again if the host is still loading.
- **"failed", "not running" or "has closed":** handle it as before (Screenshot; a crash allows one restart).

**How they match:** an element whose name is exactly `name` (ignoring upper/lower case and treating any whitespace, including a line break in a two-line label, as one space) comes first; otherwise names that contain `name`. When a name occurs in several places, give `control_type` (e.g. `Button`, `TreeItem`, `ListItem`, `Edit`) so the first match is the right one.

**Text on the screen first:** `click_ui` and `find_ui` first read the text shown in the host's windows (OCR), so they also find labels that aren't in the UI tree, such as tabs and toolbars a host draws itself. `click_ui` clicks there only a label that is **the only exact match**, or, if there is none, **the only one that contains** `name`; then the reply says "(found by OCR)". Otherwise it searches the UI tree as above. If the UI tree has nothing and the screen shows the name several times, the reply lists each place with its coordinates: take a Screenshot and click the right one with Windows-MCP `Click`. So give the name **exactly as the screen shows it** (its language and spelling), not as the documents write it. OCR doesn't know the element's type, and `type_ui` always uses the UI tree.

## Rules
1. **Use these tools first** whenever you know an element's name: from the host's navigation steps, from the test's claim, or from a dialog you just saw. They take seconds; a Snapshot can take close to a minute in a large host.
2. **Fall back to Windows-MCP** (a Screenshot, or a Snapshot, then `Click` by label or coordinates) when:
   - a tool answers "not found", "not running", "took longer" or "failed";
   - the element shows no text (an icon only), or `click_ui` listed it several times on the screen. If the navigation steps say an area needs a Screenshot, go there directly, without trying the name tools first.
3. **Check what happened** after a click that changes the screen: take a `Screenshot` (it is also the reviewer's evidence, as before). If the wrong thing opened, close it without saving and use the fallback.
4. **Dialogs and notices:** read their buttons in the Screenshot and answer with `click_ui("<button text>", control_type="Button")`; no Snapshot is needed for that.
5. **Screenshot before Snapshot:** to see what is on screen, take a Screenshot (a few seconds). Take a Snapshot only when a test needs one (e.g. the one its record requires) or when neither the name tools nor a Screenshot give you what you need.
6. **Areas marked "Screenshot only"** in the host's navigation steps: use neither the name tools nor a Snapshot there, **even when a claim names an element in that area**; a Screenshot and a click by its coordinates are the fastest way.
7. **Between the steps of a known sequence** (e.g. the host's navigation steps), check each result with a Screenshot, never a Snapshot.
8. **LOAD-000 without a Snapshot:** with these tools on, code reads the host's window titles itself when you record LOAD-000, so a Screenshot of the open document is enough. Take a Snapshot only if `record_observation` asks for one.
9. All other rules stay: the action classes, "never repeat the action while you wait", one restart per test, where results are saved. The same call with the same arguments works at most three times.
