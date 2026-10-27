"""Find, click and type host UI elements by name (UI_FIND_TOOLS_PLAN.md, ADR-047). Windows-MCP stays the fallback.

Windows-MCP can click only by coordinates or by a label from a Snapshot, and a Snapshot of a large host walks the
whole UI tree (~46 s each in run 20261016-172639). These tools ask Windows UI Automation for elements by name
instead; Windows does the search (case-insensitive, name contains the text), so it is fast.

  find_ui        list the matches, change nothing
  click_ui       click the first match (exact names before "contains" matches, G3/G4)
  type_ui        type into the first matching field
  wait_for_host  wait until the host shows a new dialog or its main window is ready (ADR-050), change nothing

Rules kept (G1): only the host's windows are searched (its processes from the host profile, incl. their owned
dialogs); the same call with the same arguments at most 3 times per run (like D36); every call is traced to
trace.jsonl. Nothing here names a host or an app: names come from the navigation file or the test's claims.
"""

import concurrent.futures
import contextlib
import ctypes
import json
import queue
import re
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mpagent.runlog import Trace, log

MAX_MATCHES = 10
SEARCH_TIMEOUT_S = 30  # one UI Automation query; then "not found", and Agent 2 falls back to Windows-MCP
# (15 s was too short for a host with a large UI tree: 12-26 s per search, ADR-049)
MAX_IDENTICAL_CALLS = 3  # like the guardrail for Windows-MCP calls (D36)
RETRY_AFTER_S = 2.0  # a host that is still starting or loading may not expose its elements yet: search once more
PIDS_CACHE_S = 10.0  # the host's process IDs are looked up (tasklist, ~1 s) at most this often
FALLBACK = "Use Windows-MCP instead (Snapshot or Screenshot, then Click by label or coordinates)."
CONTROL_TYPES = ("Button", "CheckBox", "ComboBox", "Edit", "Hyperlink", "List", "ListItem", "Menu", "MenuItem",
                 "Pane", "RadioButton", "Tab", "TabItem", "Text", "Tree", "TreeItem", "Window", "Document",
                 "SplitButton", "ToolBar", "Group", "DataItem")
POLL_S = 0.5  # wait_for_host looks at the host's windows this often (about 0.1 s per look)
SETTLE_S = 2.0  # the main window counts as ready once it is enabled and unchanged for this long
MAX_WAIT_S = 120  # longest wait_for_host call, like the time limit of a Windows-MCP call
MAX_DIALOG_NODES = 300  # elements read per dialog for its buttons and text; a host's main window is never read
MAX_LABELS = 12
REPORTED_BUTTON_S = 60.0  # click_ui clicks a button wait_for_host just reported where it was, for this long


@dataclass(frozen=True)
class Match:
    name: str
    control_type: str
    window: str  # the top-level host window the element is in
    x: int  # centre of the element on screen (physical pixels)
    y: int
    enabled: bool
    handle: object = None  # the backend's element, used to click or type


@dataclass(frozen=True)
class HostWindow:
    """A visible window of the host: its top-level windows and the windows they own (dialogs)."""
    title: str
    main: bool  # the title matches the host profile's main_window
    enabled: bool  # a window is disabled while a modal dialog it owns is open
    buttons: tuple[str, ...] = ()  # read only for windows that aren't the main window
    texts: tuple[str, ...] = ()
    points: tuple[tuple[int, int], ...] = ()  # the centre of each button on screen (physical pixels)


class Backend(Protocol):
    """Access to the desktop's UI; replaced by a fake in unit tests."""

    def find(self, pids: set[int], name: str, control_type: str | None) -> list[Match]: ...
    def titles(self, pids: set[int]) -> list[str]: ...
    def windows(self, pids: set[int], main_window: re.Pattern | None) -> list[HostWindow]: ...
    def click(self, m: Match, double: bool) -> None: ...
    def type_into(self, m: Match, text: str, press_enter: bool) -> None: ...


def normalize(name: str) -> str:
    """Case-insensitive, with every run of whitespace (incl. the line break of a two-line label) as one space."""
    return " ".join(name.split()).casefold()


def search_word(name: str) -> str:
    """The text the backend searches for: the longest word, so that a name whose words are separated by a line
    break in the UI ("Duplicate\\nViews") is still found; `matching` then compares the whole name."""
    return max(name.split(), key=len) if name.split() else name


def matching(name: str, found: list[Match]) -> list[Match]:
    """The backend's matches whose name contains `name`, whitespace-insensitive (ADR-049)."""
    wanted = normalize(name)
    return [m for m in found if wanted in normalize(m.name)]


def order_matches(name: str, matches: list[Match]) -> list[Match]:
    """Exact names first (case- and whitespace-insensitive), then the names that only contain `name` (G3);
    order kept within each."""
    wanted = normalize(name)
    exact = [m for m in matches if normalize(m.name) == wanted]
    return exact + [m for m in matches if all(m is not x for x in exact)]


def describe(m: Match) -> str:
    return (f"'{m.name}' ({m.control_type}) in '{m.window[:80]}' at ({m.x},{m.y})"
            + ("" if m.enabled else ", disabled"))


def describe_dialogs(dialogs: list[HostWindow]) -> str:
    """One line per dialog: its title, its buttons (for click_ui) and the start of its text."""
    lines = []
    for w in dialogs:
        line = f"- '{w.title or '(untitled)'}' buttons: " + ", ".join(f"'{b}'" for b in w.buttons)
        if w.texts:
            line += " | text: " + " / ".join(t[:200] for t in w.texts)
        lines.append(line)
    return "\n".join(lines)


class UiFinder:
    """The three tools' logic: host-window guard, repeat limit, tracing and time limit around a Backend."""

    def __init__(self, processes: list[str], trace: Trace, backend: Backend | None = None,
                 pids: Callable[[list[str]], dict[int, str]] | None = None, timeout_s: float = SEARCH_TIMEOUT_S,
                 main_window: str | None = None):
        """`main_window`: the host profile's regex for its main window title (wait_for_host)."""
        from mpagent.execute.host import running_pids

        self.processes, self.trace, self.timeout_s = processes, trace, timeout_s
        self.main_window = re.compile(main_window) if main_window else None
        self.retry_after_s = RETRY_AFTER_S
        self.poll_s, self.settle_s = POLL_S, SETTLE_S
        self._reported: tuple[float, list[Match]] = (0.0, [])  # the buttons of the dialogs last reported
        self._backend = backend
        self._pids = pids or running_pids
        self._calls: Counter = Counter()
        self._pid_cache: tuple[float, set[int]] = (0.0, set())
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
        args = {"name": name, "control_type": control_type, "double": double}
        reported = self._reported_button(name, control_type, double)
        if reported is not None and self._checked("click_ui", args) is None:
            # ADR-050: a busy host can keep a new search waiting for over 30 s, but the button's place is known
            started = time.monotonic()
            self._reported = (0.0, [])  # the dialog closes or changes after the click
            with physical_pixels():  # a mouse click at a point: no UI Automation, so not on the busy worker
                self.backend.click(reported, False)
            result = f"Clicked {describe(reported)} (the button wait_for_host reported)."
            self.trace.write("ui_find_call", tool="click_ui", arguments=args,
                             seconds=round(time.monotonic() - started, 2), result=result, matches=[describe(reported)])
            log.info("  click_ui %s -> %s", json.dumps(args, ensure_ascii=False), result[:120])
            return result
        return self._call("click_ui", args,
                          lambda ms: f"{'Double-clicked' if double else 'Clicked'} {describe(ms[0])}.",
                          lambda b, m: b.click(m, double))

    def _reported_button(self, name: str, control_type: str | None, double: bool) -> Match | None:
        """A button of a dialog that wait_for_host reported in the last REPORTED_BUTTON_S, named exactly `name`."""
        stamp, buttons = self._reported
        if double or control_type not in (None, "Button") or time.monotonic() - stamp > REPORTED_BUTTON_S:
            return None
        return next((b for b in buttons if normalize(b.name) == normalize(name)), None)

    def _remember(self, dialogs: list[HostWindow]) -> None:
        self._reported = (time.monotonic(), [Match(b, "Button", w.title, x, y, True)
                                             for w in dialogs for b, (x, y) in zip(w.buttons, w.points)])

    def type_text(self, name: str, text: str, control_type: str | None = "Edit", press_enter: bool = False) -> str:
        return self._call("type_ui", {"name": name, "text": text, "control_type": control_type,
                                      "press_enter": press_enter},
                          lambda ms: f"Typed into {describe(ms[0])}" + (" and pressed Enter." if press_enter else "."),
                          lambda b, m: b.type_into(m, text, press_enter))

    def wait_for_host(self, timeout_s: float = 60) -> str:
        """Wait until something is in front of the tester (ADR-050): a new dialog of the host (a window with buttons
        that wasn't there when the wait began), the main window ready (enabled and unchanged for `settle_s`), a
        dialog blocking a main window that isn't ready, or the host closed. Returns at once when one of these
        holds, else after `timeout_s`. Changes nothing; Agent 2 decides what to do with what it reports."""
        timeout_s = min(max(float(timeout_s), 1.0), MAX_WAIT_S)
        started = time.monotonic()
        baseline: set[str] | None = None
        seen_running, last_sig, stable_since, timeline = False, None, started, []
        result, windows, last_error = None, [], None
        try:
            while result is None:
                elapsed = time.monotonic() - started
                pids = self._host_pids()
                if not pids:
                    if seen_running:
                        result = f"The host has closed (after {elapsed:.1f} s)."
                    elif elapsed >= timeout_s:
                        result = f"The host is not running (waited {elapsed:.0f} s)."
                else:
                    seen_running = True
                    try:
                        windows = self._run(self.backend.windows, pids, self.main_window)
                    except Exception as e:  # noqa: BLE001 - busy, or a window closed while it was read: look again
                        windows, last_error = None, f"{type(e).__name__}: {e}"
                    if windows is not None:
                        dialogs = [w for w in windows if not w.main and w.buttons]
                        if baseline is None:
                            baseline = {w.title for w in dialogs}
                        sig = tuple(sorted((w.title, w.main, w.enabled) for w in windows))
                        if sig != last_sig:
                            last_sig, stable_since = sig, time.monotonic()
                            timeline.append(f"{elapsed:.1f}s: " + (" | ".join(w.title or "(untitled)" for w in windows)
                                                                   or "(no window yet)"))
                        stable = time.monotonic() - stable_since >= self.settle_s
                        new = [w for w in dialogs if w.title not in baseline]
                        ready = [w for w in windows if w.main and w.enabled]
                        if new:
                            result = f"A dialog opened (after {elapsed:.1f} s):\n" + describe_dialogs(new)
                            self._remember(new)
                        elif ready and stable:
                            result = (f"The host is ready (after {elapsed:.1f} s): main window '{ready[0].title}', "
                                      "no new dialog." + (f" Also open:\n{describe_dialogs(dialogs)}" if dialogs else ""))
                            self._remember(dialogs)
                        elif dialogs and stable:
                            result = (f"A dialog is waiting for an answer (after {elapsed:.1f} s):\n"
                                      + describe_dialogs(dialogs))
                            self._remember(dialogs)
                if result is None:
                    if time.monotonic() - started >= timeout_s:
                        now = " | ".join(w.title or "(untitled)" for w in windows or []) or "none"
                        result = (f"Still no ready main window or dialog after {timeout_s:.0f} s; host windows now: "
                                  f"{now}. Take a Screenshot to see what the host shows."
                                  + (f" (Last UI Automation error: {last_error})" if last_error else ""))
                    else:
                        time.sleep(self.poll_s)
        except Exception as e:  # noqa: BLE001 - a UI Automation problem is a message to Agent 2, never a crash
            result = f"wait_for_host failed ({type(e).__name__}: {e}). Take a Screenshot to see what the host shows."
        seconds = round(time.monotonic() - started, 2)
        self.trace.write("ui_find_call", tool="wait_for_host", arguments={"timeout_s": timeout_s}, seconds=seconds,
                         result=result, matches=timeline)
        log.info("  wait_for_host -> %s (%.1f s)", result.splitlines()[0][:120], seconds)
        return result

    def window_titles(self) -> list[str]:
        """The titles of the host's top-level windows (for LOAD-000's window check without a Snapshot);
        [] if the host isn't running or UI Automation fails. Traced like the tools."""
        started = time.monotonic()
        try:
            pids = self._host_pids()
            titles = self._run(self.backend.titles, pids) if pids else []
            result = f"{len(titles)} host window(s)"
        except Exception as e:  # noqa: BLE001 - the caller falls back to asking Agent 2 for a Snapshot
            titles, result = [], f"window_titles failed ({type(e).__name__}: {e})"
        self.trace.write("ui_find_call", tool="window_titles", arguments={},
                         seconds=round(time.monotonic() - started, 2), result=result, matches=titles)
        return titles

    def _host_pids(self) -> set[int]:
        stamp, pids = self._pid_cache
        if pids and time.monotonic() - stamp < PIDS_CACHE_S:
            return pids
        pids = set(self._pids(self.processes))
        self._pid_cache = (time.monotonic(), pids)
        return pids

    def _call(self, tool: str, args: dict, ok_text: Callable[[list[Match]], str],
              act: Callable[[Backend, Match], None] | None) -> str:
        started = time.monotonic()
        matches: list[Match] = []
        try:
            result = self._checked(tool, args)
            if result is None:
                pids = self._host_pids()
                if not pids:
                    result = f"The host is not running ({', '.join(self.processes)}). {FALLBACK}"
                else:
                    backend = self.backend
                    word = search_word(args["name"])
                    found = matching(args["name"], self._run(backend.find, pids, word, args["control_type"]))
                    if not found:  # once more, for a host that is still starting or loading
                        time.sleep(self.retry_after_s)
                        found = matching(args["name"], self._run(backend.find, self._host_pids(), word,
                                                                 args["control_type"]))
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


@contextlib.contextmanager
def physical_pixels():
    """This thread uses physical pixels for the mouse while inside, like the worker thread (per-monitor aware)."""
    try:
        set_context = ctypes.windll.user32.SetThreadDpiAwarenessContext
        set_context.restype, set_context.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
        old = set_context(-4)
    except (AttributeError, OSError):
        set_context, old = None, None
    try:
        yield
    finally:
        if set_context and old:
            set_context(old)


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
        tops = self._host_windows(pids)
        # the windows the host's windows own (dialogs) first: they are small, and what is clicked most; a host's
        # main window is searched only when no dialog has a match (ADR-050: 17 s for one click in a busy host)
        owned = auto.CreatePropertyCondition(u.UIA_ControlTypePropertyId, u.UIA_WindowControlTypeId)
        dialogs = [(w, t) for t in tops for w in _elements(t.FindAll(u.TreeScope_Children, owned))]
        for roots in (dialogs, [(t, t) for t in tops]):
            out: list[Match] = []
            for window, top in roots:
                title = top.CurrentName or ""
                for e in _elements(window.FindAll(u.TreeScope_Subtree, cond)):
                    r = e.CurrentBoundingRectangle
                    if r.right <= r.left or r.bottom <= r.top:
                        continue  # not on screen
                    out.append(Match(e.CurrentName or "", self.type_names.get(e.CurrentControlType, "Other"), title,
                                     (r.left + r.right) // 2, (r.top + r.bottom) // 2, bool(e.CurrentIsEnabled), e))
            if out:
                return out
        return []

    def titles(self, pids: set[int]) -> list[str]:
        return [w.CurrentName or "" for w in self._host_windows(pids)]

    def windows(self, pids: set[int], main_window: re.Pattern | None) -> list[HostWindow]:
        """The host's visible top-level windows and the windows they own. Buttons and text are read only for
        windows that aren't the main window (a main window's tree is large and slow to read)."""
        u, auto = self.uia, self.auto
        owned = auto.CreatePropertyCondition(u.UIA_ControlTypePropertyId, u.UIA_WindowControlTypeId)
        out: list[HostWindow] = []
        for top in self._host_windows(pids):
            if not _visible(top):
                continue
            title = top.CurrentName or ""
            main = bool(main_window and main_window.search(title))
            # an untitled top-level window owns its dialogs or is a main window between two titles: not read
            labels = self._labels(top) if title and not main else ((), (), ())
            out.append(HostWindow(title, main, bool(top.CurrentIsEnabled), *labels))
            for child in _elements(top.FindAll(u.TreeScope_Children, owned)):
                if _visible(child):
                    out.append(HostWindow(child.CurrentName or "", False, bool(child.CurrentIsEnabled),
                                          *self._labels(child)))
        return out

    def _labels(self, window) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[int, int], ...]]:
        """The names of a dialog's own buttons and its texts, read in one UI Automation call (a cache request:
        a busy host answers each separate property read slowly). Title-bar buttons (close, minimize) are not the
        dialog's own: a window with only those, like a hidden helper window, is no dialog."""
        u, auto = self.uia, self.auto
        kinds = (u.UIA_ButtonControlTypeId, u.UIA_SplitButtonControlTypeId, u.UIA_HyperlinkControlTypeId,
                 u.UIA_TextControlTypeId, u.UIA_TitleBarControlTypeId)
        cond = auto.CreateFalseCondition()
        for k in kinds:
            cond = auto.CreateOrCondition(cond, auto.CreatePropertyCondition(u.UIA_ControlTypePropertyId, k))
        cache = auto.CreateCacheRequest()
        for prop in (u.UIA_NamePropertyId, u.UIA_ControlTypePropertyId, u.UIA_BoundingRectanglePropertyId):
            cache.AddProperty(prop)
        found = _elements(window.FindAllBuildCache(u.TreeScope_Descendants, cond, cache))[:MAX_DIALOG_NODES]
        bars = [e.CachedBoundingRectangle for e in found if e.CachedControlType == u.UIA_TitleBarControlTypeId]
        buttons: list[str] = []
        texts: list[str] = []
        points: list[tuple[int, int]] = []
        for e in found:
            name, kind = " ".join((e.CachedName or "").split()), e.CachedControlType
            if not name or kind == u.UIA_TitleBarControlTypeId:
                continue
            if kind == u.UIA_TextControlTypeId:
                if name not in texts:
                    texts.append(name)
                continue
            r = e.CachedBoundingRectangle
            x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            if r.right <= r.left or any(b.left <= x <= b.right and b.top <= y <= b.bottom for b in bars):
                continue  # not on screen, or a title-bar button
            if name not in buttons:
                buttons.append(name)
                points.append((x, y))
        return tuple(buttons[:MAX_LABELS]), tuple(texts[:MAX_LABELS // 2]), tuple(points[:MAX_LABELS])

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


def _elements(array) -> list:
    """A UI Automation element array as a list."""
    return [array.GetElement(i) for i in range(array.Length)] if array else []


def _visible(element) -> bool:
    """On screen: a non-empty rectangle and not marked off-screen (hidden helper windows are both)."""
    try:
        r = element.CurrentBoundingRectangle
        return r.right > r.left and r.bottom > r.top and not element.CurrentIsOffscreen
    except Exception:  # noqa: BLE001 - a window that closes while it is read is not visible
        return False


def escape_keys(text: str) -> str:
    """Text for pywinauto's send_keys: its special characters are typed literally."""
    return "".join(f"{{{c}}}" if c in "+^%~(){}[]" else c for c in text)


def make_ui_find_tools(finder: UiFinder) -> list:
    """The four Agents SDK tools for Agent 2."""
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

    @function_tool
    def wait_for_host(timeout_s: int = 60) -> str:
        """Wait until the host shows something to act on, and return at once when it does: a new dialog (with its
        buttons and text), the main window ready, or the host closed. Use it after starting the host and after an
        action that may open a window. Changes nothing.

        Args:
            timeout_s: The longest wait in seconds (at most 120). It returns earlier as soon as something is there.
        """
        return finder.wait_for_host(timeout_s)

    return [find_ui, click_ui, type_ui, wait_for_host]
