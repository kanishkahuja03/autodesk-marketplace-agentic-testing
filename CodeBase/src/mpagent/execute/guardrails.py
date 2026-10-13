"""Guardrails on Agent 2's tool calls (ARCHITECTURE.md D32, D33). Checked in code before every MCP call.

check_tool_call() is a pure function: it returns None to allow the call, or the reason it is rejected.
tool_guardrail() wraps it for the Agents SDK; a rejected call is not executed and the model gets the reason.
"""

import json
import os
import re
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
    "get-ciminstance win32_operatingsystem",
    "([security.principal.windowsprincipal]",
)
# Commands that may follow a pipe: they only shape output.
PS_ALLOWED_PIPES = ("select-object", "format-list", "format-table", "sort-object", "measure-object", "out-string",
                    "convertto-json")
# Characters that would let a second command or a script block hide behind an allowed start.
PS_FORBIDDEN = (";", "&&", "||", "\n", "\r", "`", "$(", "{", "}", ">", "<", "&")
GUID = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}")

REGISTRY_READ_MODES = {"get", "list"}
FS_READ_MODES = {"read", "list", "search", "info"}
PROCESS_KILL_ALLOWED = {"msiexec", "msiexec.exe"}


def check_tool_call(tool: str, args: dict, run_dir: Path) -> str | None:
    if tool == "PowerShell":
        return _check_powershell(str(args.get("command", "")))
    if tool == "Registry":
        mode = str(args.get("mode", "")).lower()
        return None if mode in REGISTRY_READ_MODES else f"Registry mode '{mode}' is not allowed (read-only: get, list)"
    if tool == "FileSystem":
        return _check_filesystem(args, run_dir)
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
    text = " ".join(raw.split())
    first, *pipes = (part.strip() for part in text.split("|"))
    if not (first.lower() + " ").startswith(PS_ALLOWED_STARTS):
        return "PowerShell command must start with one of: " + ", ".join(s.strip() for s in PS_ALLOWED_STARTS)
    for p in pipes:
        if not p.lower().startswith(PS_ALLOWED_PIPES):
            return f"PowerShell pipe target '{p.split(' ')[0]}' is not allowed (only {', '.join(PS_ALLOWED_PIPES)})"
    return None


def _check_filesystem(args: dict, run_dir: Path) -> str | None:
    mode = str(args.get("mode", "")).lower()
    if mode in FS_READ_MODES:
        return None
    if mode == "delete":
        return "FileSystem delete is never allowed"
    if mode == "write":
        targets = [args.get("path")]
    elif mode == "copy":
        targets = [args.get("destination")]
    elif mode == "move":  # moving removes the source, so both ends must be in the run folder
        targets = [args.get("path"), args.get("destination")]
    else:
        return f"FileSystem mode '{mode}' is not allowed"
    for t in targets:
        if not _inside(t, run_dir):
            return f"FileSystem {mode} is only allowed inside the run folder {run_dir} (got {t!r})"
    return None


def _inside(path: object, run_dir: Path) -> bool:
    if not isinstance(path, str) or not path.strip():
        return False
    p = Path(os.path.expandvars(path))
    if not p.is_absolute():  # Windows-MCP resolves relative paths from the Desktop
        return False
    return p.resolve().is_relative_to(run_dir.resolve())


def tool_guardrail(run_dir: Path, trace: Trace):
    """The SDK guardrail for the Windows-MCP connection: rejections are logged, traced and told to the model."""

    @tool_input_guardrail(name="mpagent-guardrail")
    def guard(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
        tool = data.context.tool_name
        try:
            args = json.loads(data.context.tool_arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        reason = check_tool_call(tool, args if isinstance(args, dict) else {}, run_dir)
        if reason is None:
            return ToolGuardrailFunctionOutput.allow()
        log.warning("GUARDRAIL rejected %s: %s", tool, reason)
        trace.write("guardrail_reject", tool=tool, arguments=args, reason=reason)
        return ToolGuardrailFunctionOutput.reject_content(f"Rejected by guardrail: {reason}. Don't retry it.")

    return guard
