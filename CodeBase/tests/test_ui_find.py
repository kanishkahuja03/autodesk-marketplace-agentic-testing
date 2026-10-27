"""Tests for the find-by-name UI tools (UI_FIND_TOOLS_PLAN.md), with a fake desktop. Run with: uv run pytest"""

import json
import time

from mpagent.execute.ui_find import (
    FALLBACK,
    MAX_IDENTICAL_CALLS,
    HostWindow,
    Match,
    UiFinder,
    escape_keys,
    order_matches,
)
from mpagent.runlog import Trace


def m(name, control_type="Button", x=10, y=20):
    return Match(name, control_type, "Host main window", x, y, True, handle=name)


class FakeBackend:
    def __init__(self, elements, delay=0.0, fail=None):
        self.elements, self.delay, self.fail = elements, delay, fail
        self.searched_pids, self.clicks, self.typed = [], [], []

    def find(self, pids, name, control_type):
        self.searched_pids.append(set(pids))
        if self.fail:
            raise self.fail
        time.sleep(self.delay)
        return [e for e in self.elements if name.casefold() in e.name.casefold()
                and (control_type is None or e.control_type == control_type)]

    def titles(self, pids):
        return ["Host main window - [Doc1]"]

    def click(self, match, double):
        self.clicks.append((match.name, double))

    def type_into(self, match, text, press_enter):
        self.typed.append((match.name, text, press_enter))


def finder(tmp_path, backend, pids=None, timeout_s=5):
    f = UiFinder(["host.exe"], Trace(tmp_path), backend=backend,
                 pids=pids or (lambda processes: {4242: "host.exe"}), timeout_s=timeout_s)
    f.retry_after_s = 0.01  # the one retry for a host that is still loading, fast in tests
    return f


def trace_events(tmp_path):
    return [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]


def test_exact_names_come_before_names_that_only_contain_the_text():
    found = [m("Open recent"), m("open"), m("Re-open"), m("Open")]
    assert [x.name for x in order_matches("Open", found)] == ["open", "Open", "Open recent", "Re-open"]


SPLASH = HostWindow("Host 2027", main=False, enabled=True)
PROMPT = HostWindow("Security - Unsigned Add-In", main=False, enabled=True,
                    buttons=("Always Load", "Load Once", "Do Not Load"), texts=("The publisher could not be verified.",),
                    points=((300, 400), (420, 400), (540, 400)))
READY = HostWindow("Host 2027 - [Home]", main=True, enabled=True)


class ScreensBackend(FakeBackend):
    """A desktop that shows one list of host windows per look, then keeps showing the last one."""

    def __init__(self, screens):
        super().__init__([])
        self.screens, self.looks = screens, 0

    def windows(self, pids, main_window):
        self.looks += 1
        return self.screens[min(self.looks, len(self.screens)) - 1]


def waiter(tmp_path, screens, pids=None):
    f = finder(tmp_path, ScreensBackend(screens), pids=pids)
    f.poll_s, f.settle_s = 0.01, 0.05
    return f


def test_wait_returns_the_moment_a_new_dialog_opens_with_its_buttons(tmp_path):
    # ADR-050 (run 20261022-101233): the load prompt waited minutes while Agent 2 reasoned about the splash screen
    f = waiter(tmp_path, [[SPLASH], [SPLASH], [HostWindow("", False, False), PROMPT]])
    reply = f.wait_for_host(30)
    assert reply.startswith("A dialog opened") and "'Security - Unsigned Add-In'" in reply
    assert "'Load Once'" in reply and "The publisher could not be verified." in reply
    [event] = trace_events(tmp_path)
    assert event["tool"] == "wait_for_host" and event["seconds"] < 5 and len(event["matches"]) == 2


def test_click_uses_the_place_of_a_button_wait_for_host_just_reported(tmp_path):
    # ADR-050 (live check 2026-10-22): a new search in the starting host took over 30 s; the place was known
    f = waiter(tmp_path, [[PROMPT]])
    f.wait_for_host(30)
    reply = f.click("load once", control_type="Button")
    assert reply.startswith("Clicked 'Load Once' (Button) in 'Security - Unsigned Add-In' at (420,400)")
    assert f.backend.clicks == [("Load Once", False)] and f.backend.searched_pids == []  # no search
    f.click("Do Not Load")  # the report is used once: the dialog changes after a click
    assert f.backend.searched_pids == [{4242}, {4242}]  # searched (and not found, then once more)


def test_wait_skips_the_splash_and_reports_a_settled_main_window(tmp_path):
    reply = waiter(tmp_path, [[SPLASH], [SPLASH], [READY]]).wait_for_host(30)
    assert reply.startswith("The host is ready") and "'Host 2027 - [Home]'" in reply


def test_wait_looks_again_after_an_error_while_windows_change(tmp_path):
    # live check 2026-10-22: a COMError when the splash screen closed ended the wait at once
    class FlakyBackend(ScreensBackend):
        def windows(self, pids, main_window):
            screen = super().windows(pids, main_window)
            if isinstance(screen, Exception):
                raise screen
            return screen

    f = finder(tmp_path, FlakyBackend([[SPLASH], OSError("An event was unable to invoke any of the subscribers"),
                                       [READY]]))
    f.poll_s, f.settle_s = 0.01, 0.05
    assert f.wait_for_host(30).startswith("The host is ready")


def test_wait_reports_a_dialog_that_was_already_open_and_a_blocked_main_window(tmp_path):
    blocked = HostWindow("Host 2027 - [Home]", main=True, enabled=False)
    reply = waiter(tmp_path, [[blocked, PROMPT]]).wait_for_host(30)
    assert reply.startswith("A dialog is waiting for an answer") and "'Load Once'" in reply


def test_wait_ends_on_timeout_host_closed_or_not_running(tmp_path):
    assert waiter(tmp_path, [[SPLASH]]).wait_for_host(1).startswith("Still no ready main window or dialog after 1 s")
    calls = iter([{4242}] * 3 + [set()] * 100)
    f = waiter(tmp_path, [[SPLASH]])
    f._host_pids = lambda: next(calls)  # the host runs for three looks, then exits
    assert f.wait_for_host(30).startswith("The host has closed")
    assert waiter(tmp_path, [[]], pids=lambda processes: {}).wait_for_host(1).startswith("The host is not running")


def test_two_line_labels_match_with_a_space_between_their_words(tmp_path):
    # ADR-049: a ribbon label shown on two lines has a line break in its UI Automation name
    backend = FakeBackend([m("Duplicate\nSheets"), m("Duplicate\nViews"), m("Views")])
    reply = finder(tmp_path, backend).click("Duplicate Views", control_type="Button")
    assert backend.clicks == [("Duplicate\nViews", False)] and reply.startswith("Clicked 'Duplicate\nViews'")
    assert [x.name for x in order_matches("views", [m("Duplicate\nViews"), m("Views")])] == ["Views", "Duplicate\nViews"]
    assert finder(tmp_path, FakeBackend([m("Duplicate\nSheets")])).click("Duplicate Views").endswith(FALLBACK)


def test_click_uses_the_first_match_and_is_traced(tmp_path):
    backend = FakeBackend([m("Open recent", "MenuItem"), m("Open", "Button", 306, 92)])
    reply = finder(tmp_path, backend).click("Open", double=True)
    assert backend.clicks == [("Open", True)] and reply.startswith("Double-clicked 'Open' (Button)")
    assert backend.searched_pids == [{4242}]  # only the host's processes are searched
    [event] = trace_events(tmp_path)
    assert event["event"] == "ui_find_call" and event["tool"] == "click_ui" and event["arguments"]["name"] == "Open"
    assert event["matches"][0].startswith("'Open' (Button)") and "seconds" in event


def test_type_and_find(tmp_path):
    backend = FakeBackend([m("File name:", "Edit"), m("File name:", "ComboBox")])
    f = finder(tmp_path, backend)
    assert f.type_text("File name:", r"C:\run\context\P\Project.xml", press_enter=True).startswith(
        "Typed into 'File name:' (Edit)")
    assert backend.typed == [("File name:", r"C:\run\context\P\Project.xml", True)]
    listing = f.find("File name")
    assert "2 match(es)" in listing and "1. 'File name:' (Edit)" in listing and backend.clicks == []


def test_not_found_not_running_and_errors_point_to_windows_mcp(tmp_path):
    assert finder(tmp_path, FakeBackend([])).click("Nothing").endswith(FALLBACK)
    not_running = finder(tmp_path, FakeBackend([m("Open")]), pids=lambda processes: {}).click("Open")
    assert "The host is not running" in not_running and FALLBACK in not_running
    broken = finder(tmp_path, FakeBackend([], fail=OSError("COM error"))).click("Open")
    assert "click_ui failed (OSError: COM error)" in broken and FALLBACK in broken
    slow = finder(tmp_path, FakeBackend([m("Open")], delay=1.0), timeout_s=0.2).click("Open")
    assert "took longer than 0.2 s" in slow and FALLBACK in slow


def test_repeat_limit_unknown_type_and_empty_name(tmp_path):
    backend = FakeBackend([m("Open")])
    f = finder(tmp_path, backend)
    replies = [f.click("Open") for _ in range(MAX_IDENTICAL_CALLS + 1)]
    assert len(backend.clicks) == MAX_IDENTICAL_CALLS and "already made 3 times" in replies[-1]
    assert f.click("Open", double=True).startswith("Double-clicked")  # other arguments: a new call
    assert "Unknown control_type 'Knob'" in f.click("Open", control_type="Knob")
    assert f.find("  ") == "find_ui needs a name."


def test_typed_text_keeps_send_keys_special_characters_literal():
    assert escape_keys(r"C:\a (1)+b%{x}~.json") == r"C:\a {(}1{)}{+}b{%}{{}x{}}{~}.json"


def test_not_found_is_searched_once_more_for_a_host_that_is_still_loading(tmp_path):
    class LateBackend(FakeBackend):
        def find(self, pids, name, control_type):
            found = super().find(pids, name, control_type)
            return found if len(self.searched_pids) > 1 else []  # the first search sees nothing yet

    backend = LateBackend([m("OK")])
    assert finder(tmp_path, backend).click("OK").startswith("Clicked 'OK'")
    assert len(backend.searched_pids) == 2 and backend.clicks == [("OK", False)]


def test_host_pids_are_looked_up_once_for_several_calls_and_window_titles(tmp_path):
    lookups = []

    def pids(processes):
        lookups.append(processes)
        return {4242: "host.exe"}

    f = finder(tmp_path, FakeBackend([m("Open")]), pids=pids)
    f.find("Open")
    f.click("Open")
    assert f.window_titles() == ["Host main window - [Doc1]"]
    assert len(lookups) == 1  # cached for a few seconds
    assert trace_events(tmp_path)[-1]["tool"] == "window_titles"
    assert finder(tmp_path, FakeBackend([]), pids=lambda processes: {}).window_titles() == []
