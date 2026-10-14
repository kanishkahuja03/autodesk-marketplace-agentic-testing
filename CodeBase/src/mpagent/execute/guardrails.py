"""Guardrails on Agent 2's tool calls (ARCHITECTURE.md D32, D33). Checked in code before every MCP call.

check_tool_call() is a pure function: it returns None to allow the call, or the reason it is rejected.
CallPolicy adds the per-run rules (install only once, no endless repeats of the same call, no uninstall
while the host runs). Host rules (FUNCTIONAL_TESTS_PLAN.md L7, L9, L13, L14): the App tool may start only the
host executable with its exact arguments, Process kill is allowed for the host's processes, waits are capped.
tool_guardrail() wraps both for the Agents SDK; a rejected call is not executed and the model gets the reason.
"""

import json
import os
import re
import shlex
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from agents import (
    ToolGuardrailFunctionOutput,
    ToolInputGuardrailData,
    tool_input_guardrail,
)

from mpagent.execute.host import HostLaunch
from mpagent.runlog import Trace, log

# A PowerShell command must start with one of these (compared case-insensitively, spaces collapsed).
PS_ALLOWED_STARTS = (
    "start-process -filepath msiexec.exe ",
    "get-authenticodesignature ",
    "get-itemproperty ",
    "get-childitem ",
    "test-path ",
    "select-string ",  # read-only search, e.g. the result line of install.log
    "get-ciminstance win32_operatingsystem",
    "([security.principal.windowsprincipal]",
)
# Commands that may follow a pipe: they only shape output.
PS_ALLOWED_PIPES = ("select-object", "format-list", "format-table", "sort-object", "measure-object", "out-string",
                    "convertto-json")
# Characters that would let a second command or a script block hide behind an allowed start.
PS_FORBIDDEN = (";", "||", "\n", "\r", "`", "$(", "{", "}", ">", "<")
# '&' starts or chains commands only outside quotes; inside quotes it's text, e.g. 'P&ID Connector' (run 20261013-145150)
PS_FORBIDDEN_UNQUOTED = ("&",)
GUID = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")

REGISTRY_READ_MODES = {"get", "list"}
FS_READ_MODES = {"read", "list", "search", "info"}
FS_READ_MAX_BYTES = 50_000  # whole-file reads above this flood the model's context (run 20261013-131217)
PROCESS_KILL_ALLOWED = {"msiexec", "msiexec.exe"}

# Per-run rules (run 20261013-125224: the installer ran twice and one FileSystem call was repeated 19 times)
MAX_IDENTICAL_CALLS = 3
REPEATABLE_TOOLS = {"Snapshot", "Screenshot", "Wait", "WaitFor"}  # looking again is normal during UI steps
MSI_INSTALL = re.compile(r"msiexec(\.exe)?\b.*['\"\s,]/(i|package)['\"\s,]", re.IGNORECASE)
MSI_UNINSTALL = re.compile(r"msiexec(\.exe)?\b.*['\"\s,]/(x|uninstall)['\"\s,]", re.IGNORECASE)
APP_WINDOW_MODES = {"switch", "resize"}  # bringing a window to the front or resizing it starts nothing


def check_tool_call(tool: str, args: dict, run_dir: Path, host: HostLaunch | None = None,
                    max_wait_s: float | None = None) -> str | None:
    if tool == "App":
        return _check_app(args, host)
    if tool in ("Wait", "WaitFor") and max_wait_s is not None:
        field = "duration" if tool == "Wait" else "timeout"
        value = _number(args.get(field))
        if value is not None and value > max_wait_s:
            return (f"{tool} {field} {value:g} s is over the maximum of {max_wait_s:g} s (a longer call times out); "
                    f"use {field}={max_wait_s:g} and call again to wait longer")
        return None
    if tool == "PowerShell":
        return _check_powershell(str(args.get("command", "")))
    if tool == "Registry":
        mode = str(args.get("mode", "")).lower()
        return None if mode in REGISTRY_READ_MODES else f"Registry mode '{mode}' is not allowed (read-only: get, list)"
    if tool == "FileSystem":
        return _check_filesystem(args)
    if tool == "Process" and str(args.get("mode", "")).lower() == "kill":
        allowed = {_image(n) for n in PROCESS_KILL_ALLOWED | set(host.processes if host else [])}
        if not args.get("name"):
            return "Process kill needs a process name (name=...); killing by pid is not allowed"
        if _image(str(args["name"])) not in allowed:
            return "Process kill is only allowed for " + ", ".join(sorted(allowed))
    return None


def _check_app(args: dict, host: HostLaunch | None) -> str | None:
    mode = str(args.get("mode") or "launch").lower()
    if mode in APP_WINDOW_MODES:
        return None
    if host is None or not host.executable:
        return "App may not start programs in this run (no host executable was given in 'App under test')"
    exact = f"mode='launch_executable', executable='{host.executable}', args={host.args}"
    if mode != "launch_executable":
        return f"App mode '{mode}' is not allowed; start the host only with {exact}"
    if _path(str(args.get("executable") or "")) != _path(host.executable) or _args(args.get("args")) != host.args:
        return f"App may start only the host, exactly: {exact}"
    return None


def _path(p: str) -> str:
    return os.path.normcase(os.path.normpath(p.strip().strip('"')))


def _args(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [a.strip('"') for a in shlex.split(value, posix=False)]
    return [str(a) for a in value] if isinstance(value, list) else [str(value)]


def _image(name: str) -> str:
    name = name.strip().lower()
    return name if name.endswith(".exe") else name + ".exe"


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _check_powershell(command: str) -> str | None:
    raw = GUID.sub("GUID", command)  # GUIDs like {DFA9...} are fine; other braces are not
    for bad in PS_FORBIDDEN:  # check before collapsing whitespace, so line breaks are still visible
        if bad in raw:
            return f"PowerShell command contains '{bad.strip() or 'a line break'}', which is not allowed"
    unquoted = QUOTED.sub("''", raw)
    for bad in PS_FORBIDDEN_UNQUOTED:
        if bad in unquoted:
            return f"PowerShell command contains '{bad}' outside quotes, which is not allowed"
    text = " ".join(raw.split())
    first, *pipes = (part.strip() for part in text.split("|"))
    if not (first.lower() + " ").startswith(PS_ALLOWED_STARTS):
        return "PowerShell command must start with one of: " + ", ".join(s.strip() for s in PS_ALLOWED_STARTS)
    for p in pipes:
        if not p.lower().startswith(PS_ALLOWED_PIPES):
            return f"PowerShell pipe target '{p.split(' ')[0]}' is not allowed (only {', '.join(PS_ALLOWED_PIPES)})"
    return None


def _check_filesystem(args: dict) -> str | None:
    mode = str(args.get("mode", "")).lower()
    if mode == "read" and not args.get("limit"):
        size = _file_size(args.get("path"))
        if size is not None and size > FS_READ_MAX_BYTES:
            return (f"FileSystem read of a {size:,}-byte file without 'limit' is not allowed (max "
                    f"{FS_READ_MAX_BYTES:,} bytes): use Select-String for a pattern, or read with offset and limit")
    if mode in FS_READ_MODES:
        return None
    # Agent 2 never writes files: results go through record_observation, evidence comes from the tools.
    # (run 20261013-145150: it overwrote the real install.log with its own sentence)
    return (f"FileSystem '{mode}' is not allowed: FileSystem is read-only for you (read, list, search, info). "
            "Report results with record_observation; never create or change files")


def _file_size(path: object) -> int | None:
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        return Path(os.path.expandvars(path)).stat().st_size
    except OSError:
        return None  # missing or unreadable: let the tool report it


class CallPolicy:
    """check_tool_call() plus the rules that need memory of the run so far."""

    def __init__(self, run_dir: Path, host: HostLaunch | None = None, max_wait_s: float | None = None,
                 host_running: Callable[[], bool] = lambda: False):
        self.run_dir, self.host, self.max_wait_s, self.host_running = run_dir, host, max_wait_s, host_running
        self.calls: Counter[str] = Counter()
        self.installed = False

    def check(self, tool: str, args: dict) -> str | None:
        reason = check_tool_call(tool, args, self.run_dir, self.host, self.max_wait_s)
        if reason:
            return reason
        if (tool == "App" and str(args.get("mode") or "launch").lower() not in APP_WINDOW_MODES
                and not self.installed):
            # run 20261013-175002: the host was started before the installer ever ran
            return ("the installer hasn't run yet in this run; do the INST tests first (silent msiexec /i), "
                    "then start the host for the LOAD tests")
        if (tool == "PowerShell" and self.host and MSI_UNINSTALL.search(str(args.get("command", "")))
                and self.host_running()):
            # locked plug-in files would make the uninstall need a reboot and leave files behind (L7)
            return ("the host is still running; kill it first (Process mode='kill', name="
                    f"'{self.host.processes[0]}'), then uninstall")
        if tool == "PowerShell" and MSI_INSTALL.search(str(args.get("command", ""))):
            if self.installed:
                return ("msiexec /i was already run in this run; install only once. Read the result from "
                        "evidence\\install.log with Select-String instead")
            self.installed = True
        if tool not in REPEATABLE_TOOLS:
            key = tool + json.dumps(args, sort_keys=True)
            self.calls[key] += 1
            if self.calls[key] > MAX_IDENTICAL_CALLS:
                return (f"this exact {tool} call was already made {MAX_IDENTICAL_CALLS} times; repeating it won't "
                        "give a different result. Record what you have and move on")
        return None


def tool_guardrail(run_dir: Path, trace: Trace, host: HostLaunch | None = None, max_wait_s: float | None = None,
                   host_running: Callable[[], bool] = lambda: False, policy: CallPolicy | None = None):
    """The SDK guardrail for the Windows-MCP connection: rejections are logged, traced and told to the model.
    Pass `policy` to share its run state (e.g. whether the installer ran) with record_observation."""
    policy = policy or CallPolicy(run_dir, host, max_wait_s, host_running)

    @tool_input_guardrail(name="mpagent-guardrail")
    def guard(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
        tool = data.context.tool_name
        try:
            args = json.loads(data.context.tool_arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        reason = policy.check(tool, args if isinstance(args, dict) else {})
        if reason is None:
            return ToolGuardrailFunctionOutput.allow()
        log.warning("GUARDRAIL rejected %s: %s", tool, reason)
        trace.write("guardrail_reject", tool=tool, arguments=args, reason=reason)
        return ToolGuardrailFunctionOutput.reject_content(f"Rejected by guardrail: {reason}. Don't retry it.")

    return guard
