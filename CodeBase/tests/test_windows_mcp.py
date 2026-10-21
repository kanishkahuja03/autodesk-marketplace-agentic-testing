"""Tests for the Windows-MCP connection. The smoke test starts the real, pre-installed server.
Run with: uv run pytest"""

import asyncio
import base64
import os
import shutil
from types import SimpleNamespace

import pytest

from mpagent.config import load_settings
from mpagent.execute.windows_mcp import (
    ALLOWED_TOOLS,
    MAX_RESULT_CHARS,
    check_tool_list,
    clean_result,
    clean_text,
    save_images,
    server_env,
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


# A real Windows-MCP PowerShell result from run 20261013-131217 (progress noise + an error, as CLIXML)
CLIXML_RESULT = (
    'Response: #< CLIXML\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
    '<Obj S="progress" RefId="0"><TN RefId="0"><T>System.Management.Automation.PSCustomObject</T></TN><MS>'
    '<PR N="Record"><AV>Preparing modules for first use.</AV></PR></MS></Obj>'
    '<S S="Error">Select-Object : Exception getting "ExitCode": "Process must exit before requested '
    'information can be determined."_x000D__x000A_</S><S S="Error">At line:1 char:432_x000D__x000A_</S>'
    '</Objs>\nStatus Code: 1'
)


def test_clixml_is_replaced_by_its_error_lines():
    text = clean_text(CLIXML_RESULT)
    assert "CLIXML" not in text and "Preparing modules" not in text
    assert '(PowerShell error output)\nSelect-Object : Exception getting "ExitCode"' in text
    assert text.rstrip().endswith("Status Code: 1")


def test_progress_only_clixml_becomes_no_output():
    progress_only = CLIXML_RESULT.split("<S S=")[0] + "</Objs>\nStatus Code: 0"
    assert clean_text(progress_only) == "Response: (no output)\n\nStatus Code: 0"


def test_long_results_are_truncated_with_a_hint():
    text = clean_text("x" * (MAX_RESULT_CHARS + 5_000))
    assert len(text) < MAX_RESULT_CHARS + 300 and "truncated: 5,000 more characters" in text


def test_clean_result_keeps_images_and_returns_a_copy():
    from mcp.types import CallToolResult, ImageContent, TextContent

    original = CallToolResult(content=[TextContent(type="text", text=CLIXML_RESULT),
                                       ImageContent(type="image", data="AAAA", mimeType="image/png")])
    cleaned = clean_result(original)
    assert "CLIXML" in original.content[0].text  # the original (traced) result is untouched
    assert "CLIXML" not in cleaned.content[0].text and cleaned.content[1] == original.content[1]


def test_server_gets_the_normal_environment_without_secrets():
    # runs 20261013-175002/-184220: with the MCP SDK's 12-variable environment, acad.exe crashed at start
    env = server_env({"ProgramData": r"C:\ProgramData", "ProgramFiles": r"C:\Program Files",
                      "CommonProgramFiles": r"C:\Program Files\Common Files", "PATH": r"C:\Windows",
                      "OPENAI_API_KEY": "sk-x", "GEMINI_API_KEY": "g", "GITHUB_TOKEN": "t", "DB_PASSWORD": "p",
                      "CLAUDE_CODE_MESSAGING_TOKEN": "m", "OPENAI_MODEL": "gpt-5.5"})
    assert {"ProgramData", "ProgramFiles", "CommonProgramFiles", "PATH", "OPENAI_MODEL"} <= set(env)
    assert not {"OPENAI_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN", "DB_PASSWORD", "CLAUDE_CODE_MESSAGING_TOKEN"} & set(env)


def test_server_params_carry_the_environment():
    server = windows_mcp_server(load_settings())
    env = server.params.env
    upper = {k.upper(): v for k, v in env.items()}  # Windows names are case-insensitive; os.environ upper-cases them
    assert upper["PROGRAMDATA"] == os.environ["ProgramData"] and "PROGRAMFILES" in upper
    assert "OPENAI_API_KEY" not in upper and "GEMINI_API_KEY" not in upper
