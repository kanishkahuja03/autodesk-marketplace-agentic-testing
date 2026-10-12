# Desktop UI Automation for Agent 2 — Research Notes

**Date:** 2026-10-12
**Status:** Early research, still being explored. **Nothing below has been installed or tested yet.** The descriptions come from the projects' own pages and from directory listings.
**Question:** Can Agent 2 drive a plug-in's desktop UI (AutoCAD Plant 3D) from plain-English test steps, with no locators written in advance, using an existing MCP server so we don't have to build one?

---

## 1. How runtime element resolution works

Playwright MCP doesn't know selectors in advance. It takes an **accessibility snapshot** of the page, the LLM maps the test step to a node in that snapshot, it acts on the node, then it takes a fresh snapshot.

Windows has the same mechanism in **UI Automation (UIA)**. WinForms and WPF dialogs and palettes (which is most Plant 3D plug-in UI) expose a tree of elements with:

| Property | Example | Notes |
|---|---|---|
| Name | "Export", "Output folder" | The visible label |
| ControlType | Button, Edit, ComboBox, TreeItem | |
| AutomationId | `btnExport` | In WinForms this is the control's code name. Often stable. |
| Patterns | Invoke, Value, Toggle, ExpandCollapse | The actions the element supports |
| BoundingRectangle | screen coordinates | Used for the vision or coordinate fallback |

**Agent loop for each test step:**

1. Snapshot the active window's UIA tree, pruned to interactive elements.
2. Give the LLM the step text plus the snapshot. It returns an element and an action.
3. Code runs the action. The LLM chooses but never clicks freely.
4. Snapshot again and check the result, which gives the verdict or the next step.
5. *(Optional)* Save the resolved locators (AutomationId, Name, ControlType path) back into the test case, so later runs replay **without the LLM**, deterministically and cheaply.

**Black-box by design:** this needs no publisher API and no plug-in source code. UIA properties are read at runtime from the compiled plug-in, from outside its process. Microsoft's free inspectors (Inspect.exe, Accessibility Insights for Windows) show the same tree to a human.

---

## 2. Candidate tools

### 2.1 Built on pywinauto

| Tool | Key features | Fit | Caveats |
|---|---|---|---|
| **windows-gui-mcp** ([Glama](https://glama.ai/mcp/servers/dcl632/windows-gui-mcp)) | 12 tools: `list_windows`, `focus_window`, `dump_ui_tree`, `find_element`, `click_element`, `type_text`, `hotkey`, `screenshot`, `wait_until_element`, `verify_text_exists`, `fallback_click_by_image_or_ocr`, `generate_stable_script_from_trace`. It tries pywinauto UIA first, then win32, then pyautogui image or coordinate clicks. A trace recorder turns a session into a **pywinauto replay script**. MIT license, Python 3.12+. | **Best fit, so spike it first.** It matches "LLM finds the controls, code replays and decides the verdict." | Glama lists it as "Inactive". OCR needs Tesseract installed separately. Must run in the desktop session that owns the UI. |
| **PyWinAuto MCP** (sandraschi) ([LobeHub](https://lobehub.com/mcp/sandraschi-pywinauto-mcp)) | Window, UI element, mouse, keyboard, screenshot and OCR tools, grouped into a few combined tools. FastMCP 3.2+, Python 3.12+. | Broader alternative. | Optional face features and a global keylogger, both off by default; keep them off. Its docs recommend a sandbox or VM. |
| **windows-computer-use-mcp** ([Glama](https://glama.ai/mcp/servers/l80mkljjgn)) | 22 tools on pywinauto (`automation_click`, `automation_screenshot`, `automation_ocr`, …). | Alternative. | Not evaluated. |

### 2.2 Built on Robot Framework

| Tool | Key features | Fit | Caveats |
|---|---|---|---|
| **rf-mcp / RobotMCP** (manykarim) ([PyPI](https://pypi.org/project/rf-mcp/), [forum](https://forum.robotframework.org/t/introducing-robotmcp-rf-mcp-ai-powered-test-automation-bridge/9225/3)) | The agent discovers keywords, runs steps live, then `build_test_suite` writes a `.robot` file (BDD or data-driven styles supported). Supports Browser, Selenium, Appium, Requests and Database libraries. Plug-in system for adding libraries. Apache-2.0, ~13k downloads a month, actively developed. | Only if we choose Robot Framework. | **Desktop support uses its own PlatynUI backend (pre-release), not pywinauto or FlaUILibrary.** `rf-mcp[desktop]` needs Python 3.12+ and runs in rf-mcp's own environment. Using another Windows library would mean writing a plug-in. |
| **SourceFuse robotframework-mcp** ([Glama](https://glama.ai/mcp/servers/@sourcefuse/robotframework-mcp/tree)) | Generates Robot tests and page objects with SeleniumLibrary. | Not a fit. | Web only. |

### 2.3 Other UIA-based servers (not pywinauto or Robot)

| Tool | Key features | Fit | Caveats |
|---|---|---|---|
| **Windows-MCP** (CursorTouch) ([GitHub](https://github.com/CursorTouch/Windows-MCP), [review](https://chatforest.com/reviews/windows-mcp-server/)) | A `Snapshot` tool returns the window's UIA tree, and `Click` targets elements from that tree or by coordinates. No vision model needed. ~5k stars. | Closest match to how Playwright MCP works. Good for comparison. | No replay script. Works best on English-locale Windows. |
| **WinWright** (civyk) ([Glama](https://glama.ai/mcp/servers/civyk-official/civyk-winwright), [mcp.so](https://mcp.so/servers/civyk-winwright)) | Describes itself as "Playwright-style": UIA3 for desktop (WPF, WinForms, Win32) and CDP for browsers. Saves sessions as JSON scripts that **`winwright run` replays without an LLM**, and **`winwright heal`** tries to repair broken selectors. | Strong comparison candidate; its replay model fits our goals. | .NET program, not Python. Listings disagree on the tool count (52–110). |
| **Terminator** (mediar-ai) ([tomevault](https://tomevault.io/tome/mediar-ai/terminator)) | Rust core, MCP server (`terminator-mcp-agent`), Python and JS SDKs, accessibility-tree based, workflow recording. | Option. | Sources disagree on platform support. The "100x faster" claim is marketing. |
| **FlaUI-based:** WpfPilot ([mcpservers](https://mcpservers.org/servers/skuzadev/wpfpilot-mcp)), WinForms MCP ([plugin](https://www.claudepluginhub.com/plugins/fnrhombus-winforms-mcp)), WinApp MCP, FlaUI MCP ([mcpmarket](https://mcpmarket.com/server/flaui)) | UIA tree inspection and semantic selectors. WpfPilot can record workflows and generate xUnit + FlaUI tests. | Useful if a plug-in's UI is purely WPF or WinForms. | .NET. Community projects. |

### 2.4 Screenshot-based computer-use models

| Model / framework | Notes | Fit |
|---|---|---|
| **Fara-7B** (Microsoft) ([blog](https://www.microsoft.com/en-us/research/blog/fara-7b-an-efficient-agentic-model-for-computer-use/), [TechRepublic](https://www.techrepublic.com/de/article/news-microsoft-fara-7b-launch/)) | 7B model that works only from screenshots. Trained on web tasks (73.5% on WebVoyager). MIT license, runs locally. | Not tuned for desktop apps. Hosting it locally conflicts with our no-local-LLM direction. |
| **UFO²** (Microsoft) ([paper](https://arxiv.org/html/2504.14603v2), [MSR](https://www.microsoft.com/en-us/research/publication/ufo2-the-desktop-agentos/)) | Desktop agent framework: a HostAgent plus per-app AppAgents. Combines UIA with OmniParser-v2 vision. Tested on 20+ Windows apps. Can run on a separate virtual desktop. | A good reference design, but a full framework and heavy for the POC. |
| **UI-TARS** (ByteDance) | Open screenshot-based GUI model that also targets desktops. Used as a baseline by Fara-7B. | Not evaluated. |

**Position:** use vision models **only as a fallback** for controls that UIA can't see.

---

## 3. Plant 3D / AutoCAD caveats

- **The drawing canvas is invisible to UIA.** It's one opaque surface. Don't verify results from pixels. Instead:
  - trigger the plug-in through AutoCAD COM (`AcadApplication.ActiveDocument.SendCommand("PLUGINCMD ")` via `pywin32`), and
  - check the effect through drawing queries (object counts, layers, blocks) or the plug-in's output files.
  This uses the host's public interface only as a probe; the test claims are still about the plug-in.
- **Ribbon (AdWindows, built on WPF):** only partly exposed to UIA. Prefer typing the plug-in's command names.
- **Startup and modal dialogs:** AutoCAD is slow to start and shows startup popups. The host profile needs "wait for window", "dismiss known popups" and timeout rules.
- **Custom-drawn controls:** some plug-ins expose nothing to UIA. Use the vision or OCR fallback, and accept lower confidence.
- **Things a user could observe:** output files, UI state after actions, install and uninstall footprint (`ApplicationPlugins`, `PackageContents.xml`, registry, Programs & Features), and errors on the AutoCAD command line.

---

## 4. Integration notes

- Agent 2 acts as an **MCP client**: a small amount of code with the Python `mcp` SDK, connected to Gemini. That's far less work than writing an MCP server.
- **Verdicts are decided by code.** The LLM only resolves elements and chooses actions.
- Prefer tools that **produce a replay script** (windows-gui-mcp → pywinauto, WinWright → JSON, rf-mcp → `.robot`). After the first LLM-assisted run, later runs need no LLM.
- **Run in a VM or sandbox.** These tools drive the real mouse and keyboard.
- They're all community projects, so check license, maintenance and safety docs before adopting one.

---

## 5. Recommended evaluation plan

1. **Spike windows-gui-mcp** on the P&ID Connector Exporter dialog in Plant 3D 2027.
2. **Compare with Windows-MCP and WinWright** on the same dialog.
3. **Try rf-mcp** only if ARCHITECTURE.md §8 settles on Robot Framework.

**Evaluation checklist (per tool):**

- [ ] Sees the plug-in's dialogs and palettes (element coverage, Names and AutomationIds present)
- [ ] Handles the AutoCAD ribbon and command line, and modal and startup dialogs
- [ ] Waits and synchronizes reliably (no flaky timing)
- [ ] Replay script quality: readable, deterministic, runs without an LLM
- [ ] Recovers when a control isn't found (OCR or vision fallback)
- [ ] Works with Gemini as the MCP client
- [ ] License, maintenance activity, safety (no unwanted features)
- [ ] Setup effort on the dev machine

---

## 6. Open questions

- pywinauto vs Robot Framework (ARCHITECTURE.md §8): does the tooling above change the balance?
- Is a vision fallback needed for the shortlisted plug-ins, or is UIA enough?
- How exactly do we wire up the MCP client with Gemini (SDK support, tool-call format)?
- Do we adopt an MCP server as-is, or keep only its replay output (scripts) inside our own runner?

---

## 7. Sources

- windows-gui-mcp — https://glama.ai/mcp/servers/dcl632/windows-gui-mcp
- PyWinAuto MCP (sandraschi) — https://lobehub.com/mcp/sandraschi-pywinauto-mcp
- windows-computer-use-mcp — https://glama.ai/mcp/servers/l80mkljjgn
- rf-mcp / RobotMCP — https://pypi.org/project/rf-mcp/
- rf-mcp forum announcement — https://forum.robotframework.org/t/introducing-robotmcp-rf-mcp-ai-powered-test-automation-bridge/9225/3
- SourceFuse robotframework-mcp — https://glama.ai/mcp/servers/@sourcefuse/robotframework-mcp/tree
- Windows-MCP (CursorTouch) — https://github.com/CursorTouch/Windows-MCP
- Windows-MCP review — https://chatforest.com/reviews/windows-mcp-server/
- WinWright — https://glama.ai/mcp/servers/civyk-official/civyk-winwright , https://mcp.so/servers/civyk-winwright
- Terminator (mediar-ai) — https://tomevault.io/tome/mediar-ai/terminator
- WpfPilot MCP — https://mcpservers.org/servers/skuzadev/wpfpilot-mcp
- WinForms MCP — https://www.claudepluginhub.com/plugins/fnrhombus-winforms-mcp
- FlaUI MCP — https://mcpmarket.com/server/flaui
- Fara-7B — https://www.microsoft.com/en-us/research/blog/fara-7b-an-efficient-agentic-model-for-computer-use/ , https://www.techrepublic.com/de/article/news-microsoft-fara-7b-launch/
- UFO² — https://arxiv.org/html/2504.14603v2 , https://www.microsoft.com/en-us/research/publication/ufo2-the-desktop-agentos/
- Microsoft UI Automation overview — https://learn.microsoft.com/en-us/windows/win32/WinAuto/uiauto-msaa
