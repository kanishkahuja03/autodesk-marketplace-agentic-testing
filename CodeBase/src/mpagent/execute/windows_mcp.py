"""Connection to the pre-installed Windows-MCP server (ARCHITECTURE.md D6, D21, D31).

Shared by the preflight (tool-list check) and Agent 2. The 13 allowed tools are enforced twice:
Windows-MCP's own --tools flag and the Agents SDK tool filter.
"""

import base64
import html
import os
import re
import shutil
from pathlib import Path

from agents.mcp import MCPServerStdio, create_static_tool_filter

from mpagent.config import Settings
from mpagent.execute.ui_tree import decode
from mpagent.runlog import log

# Version installed with `uv tool install windows-mcp==0.8.6` (README setup step).
PINNED_VERSION = "0.8.6"

ALLOWED_TOOLS: tuple[str, ...] = (
    "PowerShell", "Registry", "FileSystem", "Process", "App",
    "Snapshot", "Click", "Type", "Shortcut", "WaitFor", "Wait", "Screenshot", "Scroll",
)


# The MCP SDK starts a stdio server with only 12 environment variables, and every program Windows-MCP starts
# inherits that. Without ProgramData, ProgramFiles, CommonProgramFiles, … a host can crash at start (runs
# 20261013-175002 and -184220: acad.exe in ODISSDK.dll, reproduced with the SDK's environment). So the server
# gets this process's normal environment, minus anything that looks like a secret.
SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|COOKIE", re.IGNORECASE)


def server_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for the Windows-MCP server: the normal one without secrets (API keys never reach
    Windows-MCP or the programs it starts)."""
    environ = dict(os.environ if environ is None else environ)
    return {k: v for k, v in environ.items() if not SECRET_ENV.search(k)}


class WindowsMcpError(Exception):
    """Windows-MCP is missing or doesn't expose exactly the allowed tools."""


def find_command(settings: Settings) -> str:
    """Full path of the installed windows-mcp executable."""
    path = shutil.which(settings.windows_mcp_command)
    if not path:
        raise WindowsMcpError(
            f"'{settings.windows_mcp_command}' not found; install it once with: uv tool install windows-mcp=={PINNED_VERSION}"
        )
    return path


def windows_mcp_server(settings: Settings, recorder: "CallRecorder | None" = None,
                       guardrails: list | None = None) -> MCPServerStdio:
    """An (unstarted) MCP connection; use it as `async with windows_mcp_server(s) as server:`.
    With a recorder, every call is traced and every returned image is saved as evidence (Agent 2)."""
    cls = RecordingMCPServer if recorder else MCPServerStdio
    server = cls(
        name="windows-mcp",
        params={"command": find_command(settings), "args": ["serve", "--transport", "stdio", "--tools", ",".join(ALLOWED_TOOLS)],
                "env": server_env()},
        tool_filter=create_static_tool_filter(allowed_tool_names=list(ALLOWED_TOOLS)),
        client_session_timeout_seconds=settings.agent2_tool_timeout_s,
        cache_tools_list=True,
        tool_input_guardrails=guardrails or None,
    )
    if recorder:
        server.recorder = recorder
    return server


class CallRecorder:
    """Traces MCP calls and saves screenshots to evidence/, plus the full raw text of every Snapshot
    (evidence/<n>_Snapshot_ui.txt) for the UI checks (FUNCTIONAL_TESTS_PLAN.md L17). Files saved since the
    last record_observation call are handed over with take_pending() (ARCHITECTURE.md D31)."""

    def __init__(self, run_dir: Path, trace):
        self.evidence_dir = run_dir / "evidence"
        self.run_dir = run_dir
        self.trace = trace
        self.count = 0
        self.pending: list[str] = []

    def record(self, tool: str, arguments: dict | None, result, cleaned_chars: int | None = None) -> None:
        self.count += 1
        saved = save_images(result.content, self.evidence_dir, f"{self.count:03d}_{tool}")
        text = " ".join(getattr(c, "text", "") for c in result.content if getattr(c, "type", None) == "text")
        if tool == SNAPSHOT_TOOL and text:
            saved.append(save_ui_text(text, self.evidence_dir, f"{self.count:03d}_{tool}"))
        rel = [p.relative_to(self.run_dir).as_posix() for p in saved]
        self.pending += rel
        is_error = getattr(result, "is_error", getattr(result, "isError", None))
        self.trace.write("mcp_call", n=self.count, tool=tool, arguments=arguments, is_error=is_error,
                         text=text[:TRACE_TEXT_CHARS], text_chars=len(text), sent_to_model_chars=cleaned_chars,
                         images=rel)

    def take_pending(self) -> list[str]:
        out, self.pending = self.pending, []
        return out

    def has_pending_snapshot(self) -> bool:
        return any(p.endswith(UI_TEXT_SUFFIX) for p in self.pending)


class RecordingMCPServer(MCPServerStdio):
    recorder: CallRecorder

    async def call_tool(self, tool_name, arguments, meta=None):
        result = await super().call_tool(tool_name, arguments, meta)
        cleaned = clean_result(result)
        try:
            self.recorder.record(tool_name, arguments, result, cleaned_chars=_text_chars(cleaned))
        except Exception as e:  # noqa: BLE001 - recording evidence must never break the tool call itself
            log.warning("could not record MCP call %s: %s: %s", tool_name, type(e).__name__, e)
        return cleaned


# ---------------------------------------------------------------- what the model gets back
# Run 20261013-131217: one FileSystem read of a 354 KB UTF-16 install.log overflowed gpt-4o-mini's context window.
# Every PowerShell result also carries CLIXML progress noise that hides the real output and errors.

MAX_RESULT_CHARS = 20_000
TRACE_TEXT_CHARS = 20_000
_CLIXML = re.compile(r"#< CLIXML\s*(<Objs\b.*?</Objs>)", re.DOTALL)
_ERROR_LINE = re.compile(r'<S S="Error">(.*?)</S>', re.DOTALL)
_XML_CHAR = re.compile(r"_x([0-9A-Fa-f]{4})_")


def clean_text(text: str) -> str:
    """Replace PowerShell CLIXML blocks by their error lines (progress records are dropped), then cap the size."""

    def readable(match: re.Match) -> str:
        lines = (_XML_CHAR.sub(lambda m: chr(int(m.group(1), 16)), html.unescape(s))
                 for s in _ERROR_LINE.findall(match.group(1)))
        errors = "".join(lines).strip()
        return f"(PowerShell error output)\n{errors}\n" if errors else "(no output)\n"

    text = _CLIXML.sub(readable, text)
    if len(text) > MAX_RESULT_CHARS:
        text = (text[:MAX_RESULT_CHARS] + f"\n[... truncated: {len(text) - MAX_RESULT_CHARS:,} more characters not "
                "shown. Read only the part you need: Select-String for a pattern, or FileSystem read with "
                "offset and limit.]")
    return text


def clean_result(result):
    """A copy of an MCP CallToolResult with every text item cleaned; images are passed on unchanged."""
    content = [c.model_copy(update={"text": clean_text(c.text)}) if getattr(c, "type", None) == "text" else c
               for c in result.content]
    return result.model_copy(update={"content": content})


def _text_chars(result) -> int:
    return sum(len(getattr(c, "text", "")) for c in result.content if getattr(c, "type", None) == "text")


async def check_tool_list(server: MCPServerStdio) -> list[str]:
    """Return the tool names the server exposes; raise if they differ from ALLOWED_TOOLS."""
    names = sorted(t.name for t in await server.list_tools())
    expected = sorted(ALLOWED_TOOLS)
    if names != expected:
        extra = sorted(set(names) - set(expected))
        missing = sorted(set(expected) - set(names))
        raise WindowsMcpError(f"tool list mismatch: extra={extra or '-'} missing={missing or '-'}")
    return names


SNAPSHOT_TOOL = "Snapshot"
UI_TEXT_SUFFIX = "_ui.txt"


def save_ui_text(text: str, evidence_dir: Path, prefix: str) -> Path:
    """Save a Snapshot's full raw text (decoded if Windows-MCP returned it as a JSON list); never cut off."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{prefix}{UI_TEXT_SUFFIX}"
    path.write_text(decode(text), encoding="utf-8")
    return path


def save_images(content: list, evidence_dir: Path, prefix: str) -> list[Path]:
    """Save every image in an MCP tool result to evidence_dir/<prefix>_<n>.png. Windows-MCP returns images
    inline as base64 and saves nothing itself (verified on 0.8.6)."""
    saved: list[Path] = []
    for item in content:
        if getattr(item, "type", None) != "image":
            continue
        ext = (getattr(item, "mimeType", None) or getattr(item, "mime_type", None) or "image/png").split("/")[-1]
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{prefix}_{len(saved) + 1}.{ext}"
        path.write_bytes(base64.b64decode(item.data))
        saved.append(path)
    return saved
