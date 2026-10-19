"""Find, click and type host UI elements by name (UI_FIND_TOOLS_PLAN.md, ADR-047). Windows-MCP stays the fallback.

Windows-MCP can click only by coordinates or by a label from a Snapshot, and a Snapshot of a large host walks the
whole UI tree (~46 s each in run 20261016-172639). These tools ask Windows UI Automation for elements by name
instead; Windows does the search (case-insensitive, name contains the text), so it is fast.

  find_ui   list the matches, change nothing
  click_ui  click the first match (exact names before "contains" matches, G3/G4)
  type_ui   type into the first matching field

Rules kept (G1): only the host's windows are searched (its processes from the host profile, incl. their owned
dialogs); the same call with the same arguments at most 3 times per run (like D36); every call is traced to
trace.jsonl. Nothing here names a host or an app: names come from the navigation file or the test's claims.
"""

import concurrent.futures
import ctypes
import json
import queue
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mpagent.runlog import Trace, log

MAX_MATCHES = 10
SEARCH_TIMEOUT_S = 15  # one UI Automation query; then "not found", and Agent 2 falls back to Windows-MCP
MAX_IDENTICAL_CALLS = 3  # like the guardrail for Windows-MCP calls (D36)
FALLBACK = "Use Windows-MCP instead (Snapshot or Screenshot, then Click by label or coordinates)."
CONTROL_TYPES = ("Button", "CheckBox", "ComboBox", "Edit", "Hyperlink", "List", "ListItem", "Menu", "MenuItem",
                 "Pane", "RadioButton", "Tab", "TabItem", "Text", "Tree", "TreeItem", "Window", "Document",
                 "SplitButton", "ToolBar", "Group", "DataItem")


@dataclass(frozen=True)
class Match:
    name: str
    control_type: str
    window: str  # the top-level host window the element is in
    x: int  # centre of the element on screen (physical pixels)
    y: int
    enabled: bool
    handle: object = None  # the backend's element, used to click or type


class Backend(Protocol):
    """Access to the desktop's UI; replaced by a fake in unit tests."""

    def find(self, pids: set[int], name: str, control_type: str | None) -> list[Match]: ...
    def click(self, m: Match, double: bool) -> None: ...
    def type_into(self, m: Match, text: str, press_enter: bool) -> None: ...


def order_matches(name: str, matches: list[Match]) -> list[Match]:
    """Exact names first (case-insensitive), then the names that only contain `name` (G3); order kept within each."""
    wanted = name.strip().casefold()
    exact = [m for m in matches if m.name.strip().casefold() == wanted]
    return exact + [m for m in matches if all(m is not x for x in exact)]


def describe(m: Match) -> str:
    return (f"'{m.name}' ({m.control_type}) in '{m.window[:80]}' at ({m.x},{m.y})"
            + ("" if m.enabled else ", disabled"))


class UiFinder:
    """The three tools' logic: host-window guard, repeat limit, tracing and time limit around a Backend."""

    def __init__(self, processes: list[str], trace: Trace, backend: Backend | None = None,
                 pids: Callable[[list[str]], dict[int, str]] | None = None, timeout_s: float = SEARCH_TIMEOUT_S):
        from mpagent.execute.host import running_pids

        self.processes, self.trace, self.timeout_s = processes, trace, timeout_s
        self._backend = backend
        self._pids = pids or running_pids
        self._calls: Counter = Counter()
        self._worker = _Worker()

    @property
    def backend(self) -> Backend:
        if self._backend is None:
            self._backend = self._run(UiaBackend)  # built in the worker thread, where its COM objects live
        return self._backend

    def find(self, name: str, control_type: str | None = None) -> str:
        return self._call("find_ui", {"name": name, "control_type": control_type}, lambda ms: (
            f"{len(ms)} match(es), first is used by click_ui/type_ui:\n"
            + "\n".join(f"{i}. {describe(m)}" for i, m in enumerate(ms[:MAX_MATCHES], 1))), None)

    def click(self, name: str, control_type: str | None = None, double: bool = False) -> str:
        return self._call("click_ui", {"name": name, "control_type": control_type, "double": double},
                          lambda ms: f"{'Double-clicked' if double else 'Clicked'} {describe(ms[0])}.",
                          lambda b, m: b.click(m, double))

    def type_text(self, name: str, text: str, control_type: str | None = "Edit", press_enter: bool = False) -> str:
        return self._call("type_ui", {"name": name, "text": text, "control_type": control_type,
                                      "press_enter": press_enter},
                          lambda ms: f"Typed into {describe(ms[0])}" + (" and pressed Enter." if press_enter else "."),
                          lambda b, m: b.type_into(m, text, press_enter))

    def _call(self, tool: str, args: dict, ok_text: Callable[[list[Match]], str],
              act: Callable[[Backend, Match], None] | None) -> str:
        started = time.monotonic()
        matches: list[Match] = []
        try:
            result = self._checked(tool, args)
            if result is None:
                pids = set(self._pids(self.processes))
                if not pids:
                    result = f"The host is not running ({', '.join(self.processes)}). {FALLBACK}"
                else:
                    backend = self.backend
                    found = self._run(backend.find, pids, args["name"], args["control_type"])
                    matches = order_matches(args["name"], found)
                    if not matches:
                        kind = f" of type {args['control_type']}" if args["control_type"] else ""
                        result = f"No element named '{args['name']}'{kind} in the host's windows. {FALLBACK}"
                    else:
                        if act is not None:
                            self._run(act, backend, matches[0])
                        result = ok_text(matches)
        except concurrent.futures.TimeoutError:
            result = f"The UI search took longer than {self.timeout_s:g} s. {FALLBACK}"
        except Exception as e:  # noqa: BLE001 - a UI Automation problem is a message to Agent 2, never a crash
            result = f"{tool} failed ({type(e).__name__}: {e}). {FALLBACK}"
        seconds = round(time.monotonic() - started, 2)
        self.trace.write("ui_find_call", tool=tool, arguments=args, seconds=seconds, result=result,
                         matches=[describe(m) for m in matches[:MAX_MATCHES]])
        log.info("  %s %s -> %s (%.1f s)", tool, json.dumps(args, ensure_ascii=False), result.splitlines()[0][:120],
                 seconds)
        return result

    def _checked(self, tool: str, args: dict) -> str | None:
        """A refusal text, or None if the call may run."""
        if not str(args.get("name") or "").strip():
            return f"{tool} needs a name."
        ct = args.get("control_type")
        if ct and ct not in CONTROL_TYPES:
            return f"Unknown control_type '{ct}'; use one of: {', '.join(CONTROL_TYPES)}, or none."
        key = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
        self._calls[key] += 1
        if self._calls[key] > MAX_IDENTICAL_CALLS:
            return (f"This exact {tool} call was already made {MAX_IDENTICAL_CALLS} times; repeating it won't help. "
                    f"{FALLBACK}")
        return None

    def _run(self, fn, *args):
        return self._worker.submit(fn, *args).result(timeout=self.timeout_s)


class _Worker:
    """One daemon thread that runs every UI Automation call (its COM objects belong to that thread). A daemon
    thread, so a call that hangs never keeps the pipeline from finishing; the caller only waits `timeout_s`."""

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self._loop, name="ui_find", daemon=True).start()

    def submit(self, fn, *args) -> concurrent.futures.Future:
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._jobs.put((future, fn, args))
        return future

    def _loop(self) -> None:
        _init_worker()
        while True:
            future, fn, args = self._jobs.get()
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(*args))
            except BaseException as e:  # noqa: BLE001 - handed to the caller, which turns it into a message
                future.set_exception(e)


def _init_worker() -> None:
    """The worker thread does all UI Automation calls: its own COM apartment, and physical pixels for the
    element rectangles and the mouse (per thread, so the rest of the pipeline is not affected)."""
    import comtypes

    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except OSError:
        pass  # this thread's COM apartment is already set up (comtypes does it for new threads)
    try:
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor aware v2
    except (AttributeError, OSError):
        pass


class UiaBackend:
    """Windows UI Automation through comtypes (installed with pywinauto); input through pywinauto."""

    def __init__(self):
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as uia

        self.uia = uia
        self.auto = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        self.types = {name: getattr(uia, f"UIA_{name}ControlTypeId") for name in CONTROL_TYPES
                      if hasattr(uia, f"UIA_{name}ControlTypeId")}
        self.type_names = {v: k for k, v in self.types.items()}

    def find(self, pids: set[int], name: str, control_type: str | None) -> list[Match]:
        u, auto = self.uia, self.auto
        flags = u.PropertyConditionFlags_IgnoreCase | u.PropertyConditionFlags_MatchSubstring
        cond = auto.CreatePropertyConditionEx(u.UIA_NamePropertyId, name, flags)
        if control_type:
            cond = auto.CreateAndCondition(cond, auto.CreatePropertyCondition(u.UIA_ControlTypePropertyId,
                                                                              self.types[control_type]))
        out: list[Match] = []
        for window in self._host_windows(pids):
            title = window.CurrentName or ""
            found = window.FindAll(u.TreeScope_Subtree, cond)
            for i in range(found.Length):
                e = found.GetElement(i)
                r = e.CurrentBoundingRectangle
                if r.right <= r.left or r.bottom <= r.top:
                    continue  # not on screen
                out.append(Match(e.CurrentName or "", self.type_names.get(e.CurrentControlType, "Other"), title,
                                 (r.left + r.right) // 2, (r.top + r.bottom) // 2, bool(e.CurrentIsEnabled), e))
        return out

    def _host_windows(self, pids: set[int]) -> list:
        u, auto = self.uia, self.auto
        root = auto.GetRootElement()
        conds = [auto.CreatePropertyCondition(u.UIA_ProcessIdPropertyId, p) for p in sorted(pids)]
        cond = conds[0]
        for c in conds[1:]:
            cond = auto.CreateOrCondition(cond, c)
        found = root.FindAll(u.TreeScope_Children, cond)
        return [found.GetElement(i) for i in range(found.Length)]

    def click(self, m: Match, double: bool) -> None:
        from pywinauto import mouse

        (mouse.double_click if double else mouse.click)(button="left", coords=(m.x, m.y))

    def type_into(self, m: Match, text: str, press_enter: bool) -> None:
        from pywinauto import keyboard

        e, u = m.handle, self.uia
        try:
            e.SetFocus()
        except Exception:  # noqa: BLE001 - some elements can't take focus; clicking them gives it
            self.click(m, double=False)
        try:
            pattern = e.GetCurrentPattern(u.UIA_ValuePatternId).QueryInterface(u.IUIAutomationValuePattern)
            pattern.SetValue(text)
        except Exception:  # noqa: BLE001 - no value pattern: type the keys instead
            keyboard.send_keys(escape_keys(text), with_spaces=True, pause=0.01)
        if press_enter:
            keyboard.send_keys("{ENTER}")


def escape_keys(text: str) -> str:
    """Text for pywinauto's send_keys: its special characters are typed literally."""
    return "".join(f"{{{c}}}" if c in "+^%~(){}[]" else c for c in text)


def make_ui_find_tools(finder: UiFinder) -> list:
    """The three Agents SDK tools for Agent 2."""
    from agents import function_tool

    @function_tool
    def find_ui(name: str, control_type: str | None = None) -> str:
        """List UI elements of the host whose name is (or contains) this text. Changes nothing.

        Args:
            name: The element's name as shown, e.g. a button, tree item or field label. Exact names come first.
            control_type: Optional element type to narrow the search, e.g. Button, TreeItem, Edit, ListItem.
        """
        return finder.find(name, control_type)

    @function_tool
    def click_ui(name: str, control_type: str | None = None, double: bool = False) -> str:
        """Click the first UI element of the host with this name (exact names before names that only contain it).

        Args:
            name: The element's name as shown.
            control_type: Optional element type, e.g. Button, TreeItem, ListItem; give it when the name occurs twice.
            double: True for a double-click (e.g. to open a tree item).
        """
        return finder.click(name, control_type, double)

    @function_tool
    def type_ui(name: str, text: str, control_type: str | None = "Edit", press_enter: bool = False) -> str:
        """Type text into the first field of the host with this name (e.g. a dialog's file name box).

        Args:
            name: The field's name or label as shown, e.g. "File name:".
            text: The text to type, e.g. a full path.
            control_type: The field's type; Edit by default.
            press_enter: True to press Enter afterwards (e.g. to confirm a file dialog).
        """
        return finder.type_text(name, text, control_type, press_enter)

    return [find_ui, click_ui, type_ui]
