"""Tests for Stage 0. Run with: uv run pytest"""

import json
from pathlib import Path

import pytest

from mpagent.design import intake
from mpagent.design.intake import (
    IntakeError,
    classify,
    common_name,
    normalise,
    read_text_file,
    run_intake,
)
from mpagent.models import FileKind


@pytest.fixture(autouse=True)
def no_powershell(monkeypatch):
    """Don't call PowerShell in unit tests; pretend every installer is signed by 'Test Co'."""
    monkeypatch.setattr(intake, "read_signer_subject", lambda path: "CN=Test Co, O=Test Co, C=DE")


def make_plugin(tmp_path: Path, files: dict[str, bytes]) -> Path:
    folder = tmp_path / "inputs" / "demo-plugin"
    folder.mkdir(parents=True)
    for name, content in files.items():
        (folder / name).write_bytes(content)
    return folder


def test_classify_by_extension(tmp_path):
    assert classify(tmp_path / "Guide.PDF") is FileKind.DOCUMENT
    assert classify(tmp_path / "setup.msi") is FileKind.INSTALLER
    assert classify(tmp_path / "metadata.json") is FileKind.METADATA
    assert classify(tmp_path / "logo.png") is FileKind.UNSUPPORTED


def test_text_encodings(tmp_path):
    text = "Autodesk® Plant 3D™ “Export”"
    for name, data in {
        "utf8.txt": text.encode("utf-8"),
        "utf8bom.txt": text.encode("utf-8-sig"),
        "utf16.txt": text.encode("utf-16"),
    }.items():
        (tmp_path / name).write_bytes(data)
        assert read_text_file(tmp_path / name) == text


def test_normalise():
    assert normalise("a  \r\nb\r\n\r\n\r\n\r\nc") == "a\nb\n\nc\n"


def test_common_name():
    assert common_name("CN=Kleen Software GmbH, O=Kleen Software GmbH, C=DE") == "Kleen Software GmbH"
    assert common_name('CN="Acme, Inc.", O=Acme') == "Acme, Inc."
    assert common_name(None) is None


def test_run_intake_happy_path(tmp_path):
    folder = make_plugin(
        tmp_path,
        {"Description.txt": b"Line one\nLine two\n", "UserGuide.txt": b"Install it.", "setup.msi": b"fake", "logo.png": b"x"},
    )
    manifest, run_dir = run_intake(folder, tmp_path / "runs")

    assert [d.doc_id for d in manifest.documents] == ["D1", "D2"]
    assert manifest.documents[0].source_file == "Description.txt"
    assert (run_dir / "documents" / "D1_Description.txt").read_text(encoding="utf-8") == "Line one\nLine two\n"
    assert manifest.installer.file == "setup.msi"
    assert manifest.installer.signer_name == "Test Co"
    assert any("logo.png" in w for w in manifest.warnings)
    saved = json.loads((run_dir / "intake_manifest.json").read_text(encoding="utf-8"))
    assert saved["plugin"] == "demo-plugin"


def test_requires_exactly_one_installer(tmp_path):
    folder = make_plugin(tmp_path, {"Description.txt": b"x", "a.msi": b"1", "b.exe": b"2"})
    with pytest.raises(IntakeError, match="exactly one installer"):
        run_intake(folder, tmp_path / "runs")


def test_requires_a_document(tmp_path):
    folder = make_plugin(tmp_path, {"setup.msi": b"1"})
    with pytest.raises(IntakeError, match="no documents"):
        run_intake(folder, tmp_path / "runs")
