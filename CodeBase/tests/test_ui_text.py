"""Tests for the app's UI text from its binaries (LOAD_TESTS_PLAN.md L22, source U1). Run with: uv run pytest"""

from pathlib import Path

import pytest

from mpagent.design.evidence import build_sources
from mpagent.design.intake import run_intake
from mpagent.design.static_read import run_static_read
from mpagent.design.ui_text import build_ui_text, is_library, ui_strings
from mpagent.models import IntakeManifest

REAL_PLUGIN = Path(__file__).parent.parent / "inputs" / "pid-connector-exporter"


def utf16(*texts: str) -> bytes:
    return b"\x00\x01junk\xff".join(t.encode("utf-16-le") for t in texts)


def test_ui_strings_keep_ui_text_and_drop_noise():
    data = utf16("Export selection", "VS_VERSION_INFO", "pidexport.Properties.Resources", "z.#{", "Hi", "Tools")
    assert ui_strings(data) == ["Export selection", "Tools"]


def test_each_string_once_and_libraries_skipped():
    text = build_ui_text([(r"X\NET10\app.dll", utf16("Settings", "Language")),
                          (r"X\NET8\app.dll", utf16("Settings", "Language")),  # the same text for another .NET
                          (r"X\Newtonsoft.Json.dll", utf16("Unexpected JSON token"))])
    assert text == "== X\\NET10\\app.dll\nSettings\nLanguage"
    assert is_library("System.Memory.dll") and not is_library("pid-export.dll")


@pytest.mark.skipif(not REAL_PLUGIN.exists(), reason="real plug-in inputs not present")
def test_real_msi_gives_the_plugins_ui_text(tmp_path):
    # run 20261014-124157: the guide says 'P&ID Exporter'; the plug-in's own text says 'P&ID Connector'
    _, run_dir = run_intake(REAL_PLUGIN, tmp_path / "runs")
    facts = run_static_read(run_dir)
    assert facts.ui_text and facts.ui_text.doc_id == "U1" and not facts.warnings
    text = (run_dir / facts.ui_text.text_file).read_text(encoding="utf-8")
    for word in ("P&ID Connector", "Tools", "Export selection", "Settings", "Language", "Help", "Info"):
        assert word in text, word
    assert not list((run_dir / "installer_extract").rglob("*.dll"))  # untrusted binaries are not kept
    manifest = IntakeManifest.model_validate_json(
        (run_dir / "intake_manifest.json").read_text(encoding="utf-8"))
    assert "U1" in [s.id for s in build_sources(run_dir, manifest, facts)]
