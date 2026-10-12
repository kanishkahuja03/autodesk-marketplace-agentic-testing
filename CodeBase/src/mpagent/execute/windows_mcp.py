"""Connection to the pre-installed Windows-MCP server (ARCHITECTURE.md D6, D21, D31).

Shared by the preflight (tool-list check) and Agent 2. The 13 allowed tools are enforced twice:
Windows-MCP's own --tools flag and the Agents SDK tool filter.
"""

import base64
import shutil
from pathlib import Path

from agents.mcp import MCPServerStdio, create_static_tool_filter

from mpagent.config import Settings

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


def windows_mcp_server(settings: Settings) -> MCPServerStdio:
    """An (unstarted) MCP connection; use it as `async with windows_mcp_server(s) as server:`."""
    return MCPServerStdio(
        name="windows-mcp",
        params={"command": find_command(settings), "args": ["serve", "--transport", "stdio", "--tools", ",".join(ALLOWED_TOOLS)]},
        tool_filter=create_static_tool_filter(allowed_tool_names=list(ALLOWED_TOOLS)),
        client_session_timeout_seconds=settings.agent2_tool_timeout_s,
        cache_tools_list=True,
    )


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
