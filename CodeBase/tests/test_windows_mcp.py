"""Tests for the Windows-MCP connection. The smoke test starts the real, pre-installed server.
Run with: uv run pytest"""

import asyncio
import base64
import shutil
from types import SimpleNamespace

import pytest

from mpagent.config import load_settings
from mpagent.execute.windows_mcp import (
    ALLOWED_TOOLS,
    check_tool_list,
    save_images,
    windows_mcp_server,
)

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_allow_list_has_13_unique_tools():
    assert len(ALLOWED_TOOLS) == len(set(ALLOWED_TOOLS)) == 13
    assert not {"Clipboard", "Scrape", "Notification", "Move", "MultiSelect", "MultiEdit", "DisplayInventory"} & set(ALLOWED_TOOLS)


def test_save_images_writes_only_images(tmp_path):
    content = [
        SimpleNamespace(type="text", text="Cursor Position: (1, 2)"),
        SimpleNamespace(type="image", data=base64.b64encode(PNG_1PX).decode(), mimeType="image/png"),
    ]
    saved = save_images(content, tmp_path / "evidence", "UNIN-001")
    assert [p.name for p in saved] == ["UNIN-001_1.png"]
    assert saved[0].read_bytes() == PNG_1PX


@pytest.mark.skipif(shutil.which(load_settings().windows_mcp_command) is None, reason="Windows-MCP not installed")
def test_smoke_real_server_lists_13_tools_and_screenshots(tmp_path):
    async def smoke():
        async with windows_mcp_server(load_settings()) as server:
            names = await check_tool_list(server)
            result = await server.call_tool("Screenshot", {})
            return names, save_images(result.content, tmp_path, "smoke")

    names, saved = asyncio.run(smoke())
    assert names == sorted(ALLOWED_TOOLS)
    assert len(saved) == 1 and saved[0].stat().st_size > 1000
