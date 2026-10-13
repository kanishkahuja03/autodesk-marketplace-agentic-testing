"""Connection to the pre-installed Windows-MCP server (ARCHITECTURE.md D6, D21, D31).

Shared by the preflight (tool-list check) and Agent 2. The 13 allowed tools are enforced twice:
Windows-MCP's own --tools flag and the Agents SDK tool filter.
"""

import base64
import shutil
from pathlib import Path

from agents.mcp import MCPServerStdio, create_static_tool_filter

from mpagent.config import Settings
from mpagent.runlog import log

# Version installed with `uv tool install windows-mcp==0.8.6` (README setup step).
PINNED_VERSION = "0.8.6"

ALLOWED_TOOLS: tuple[str, ...] = (
    "PowerShell", "Registry", "FileSystem", "Process", "App",
    "Snapshot", "Click", "Type", "Shortcut", "WaitFor", "Wait", "Screenshot", "Scroll",
)


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
        params={"command": find_command(settings), "args": ["serve", "--transport", "stdio", "--tools", ",".join(ALLOWED_TOOLS)]},
        tool_filter=create_static_tool_filter(allowed_tool_names=list(ALLOWED_TOOLS)),
        client_session_timeout_seconds=settings.agent2_tool_timeout_s,
        cache_tools_list=True,
        tool_input_guardrails=guardrails or None,
    )
    if recorder:
        server.recorder = recorder
    return server


class CallRecorder:
    """Traces MCP calls and saves screenshots to evidence/. Screenshots taken since the last
    record_observation call are handed over with take_pending() (ARCHITECTURE.md D31)."""

    def __init__(self, run_dir: Path, trace):
        self.evidence_dir = run_dir / "evidence"
        self.run_dir = run_dir
        self.trace = trace
        self.count = 0
        self.pending: list[str] = []

    def record(self, tool: str, arguments: dict | None, result) -> None:
        self.count += 1
        saved = save_images(result.content, self.evidence_dir, f"{self.count:03d}_{tool}")
        rel = [p.relative_to(self.run_dir).as_posix() for p in saved]
        self.pending += rel
        text = " ".join(getattr(c, "text", "") for c in result.content if getattr(c, "type", None) == "text")
        is_error = getattr(result, "is_error", getattr(result, "isError", None))
        self.trace.write("mcp_call", n=self.count, tool=tool, arguments=arguments, is_error=is_error,
                         text=text[:2000], images=rel)

    def take_pending(self) -> list[str]:
        out, self.pending = self.pending, []
        return out


class RecordingMCPServer(MCPServerStdio):
    recorder: CallRecorder

    async def call_tool(self, tool_name, arguments, meta=None):
        result = await super().call_tool(tool_name, arguments, meta)
        try:
            self.recorder.record(tool_name, arguments, result)
        except Exception as e:  # noqa: BLE001 - recording evidence must never break the tool call itself
            log.warning("could not record MCP call %s: %s: %s", tool_name, type(e).__name__, e)
        return result


async def check_tool_list(server: MCPServerStdio) -> list[str]:
    """Return the tool names the server exposes; raise if they differ from ALLOWED_TOOLS."""
    names = sorted(t.name for t in await server.list_tools())
    expected = sorted(ALLOWED_TOOLS)
    if names != expected:
        extra = sorted(set(names) - set(expected))
        missing = sorted(set(expected) - set(names))
        raise WindowsMcpError(f"tool list mismatch: extra={extra or '-'} missing={missing or '-'}")
    return names


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
