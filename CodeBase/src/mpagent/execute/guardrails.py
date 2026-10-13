"""Guardrails on Agent 2's tool calls (ARCHITECTURE.md D32, D33). Checked in code before every MCP call.

check_tool_call() is a pure function: it returns None to allow the call, or the reason it is rejected.
CallPolicy adds the per-run rules (install only once, no endless repeats of the same call).
tool_guardrail() wraps both for the Agents SDK; a rejected call is not executed and the model gets the reason.
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

from agents import (
    ToolGuardrailFunctionOutput,
    ToolInputGuardrailData,
    tool_input_guardrail,
)

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


def check_tool_call(tool: str, args: dict, run_dir: Path) -> str | None:
    if tool == "PowerShell":
        return _check_powershell(str(args.get("command", "")))
    if tool == "Registry":
        mode = str(args.get("mode", "")).lower()
        return None if mode in REGISTRY_READ_MODES else f"Registry mode '{mode}' is not allowed (read-only: get, list)"
    if tool == "FileSystem":
        return _check_filesystem(args)
    if tool == "Process" and str(args.get("mode", "")).lower() == "kill":
        name = str(args.get("name") or "").lower()
        if name not in PROCESS_KILL_ALLOWED:
            return "Process kill is only allowed for msiexec (a stuck installer)"
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

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.calls: Counter[str] = Counter()
        self.installed = False

    def check(self, tool: str, args: dict) -> str | None:
        reason = check_tool_call(tool, args, self.run_dir)
        if reason:
            return reason
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


def tool_guardrail(run_dir: Path, trace: Trace):
    """The SDK guardrail for the Windows-MCP connection: rejections are logged, traced and told to the model."""
    policy = CallPolicy(run_dir)

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
