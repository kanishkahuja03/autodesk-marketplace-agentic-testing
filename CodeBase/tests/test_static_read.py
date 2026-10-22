"""Tests for Stage 1. Run with: uv run pytest"""

from pathlib import Path

import pytest

from mpagent.design.intake import run_intake
from mpagent.design.static_read import (
    decode_custom_action,
    install_root,
    install_scope,
    long_name,
    parse_package_contents,
    resolve_directories,
    run_static_read,
    target_dir_name,
)

REAL_PLUGIN = Path(__file__).parent.parent / "inputs" / "pid-connector-exporter"


def test_names():
    assert long_name("PIDEXP~1.DLL|PidExportCore.dll") == "PidExportCore.dll"
    assert long_name("Help.html") == "Help.html"
    assert target_dir_name(".:APPLIC~1|Application Data") == "."
    assert target_dir_name("PIDEXP~1.BUN|pidExport.bundle") == "pidExport.bundle"


def test_resolve_directories_with_override():
    rows = [
        {"Directory": "TARGETDIR", "Directory_Parent": None, "DefaultDir": "SOURCEDIR"},
        {"Directory": "AppDataFolder", "Directory_Parent": "TARGETDIR", "DefaultDir": ".:AppData"},
        {"Directory": "AUTODESK", "Directory_Parent": "AppDataFolder", "DefaultDir": "Autodesk"},
        {"Directory": "Plugins", "Directory_Parent": "AUTODESK", "DefaultDir": "Applic~1|ApplicationPlugins"},
        {"Directory": "Custom", "Directory_Parent": "Plugins", "DefaultDir": "x|Ignored"},
    ]
    dirs = resolve_directories(rows, overrides={"Custom": "[AppDataFolder]"})
    assert dirs["Plugins"] == r"%AppData%\Autodesk\ApplicationPlugins"
    assert dirs["Custom"] == "%AppData%"  # a custom action re-points this folder at install time


def test_decode_custom_action():
    ca = decode_custom_action({"Action": "Cert", "Type": str(1 | 0x400 | 0x2000), "Source": "x.dll", "Target": "Run"})
    assert ca.kind == "runs a DLL function stored in the installer"
    assert ca.flags == ["deferred", "runs as SYSTEM (no impersonation)"]


def test_install_scope_and_root():
    assert install_scope({"ALLUSERS": "1"}) == "per-machine"
    assert install_scope({"ALLUSERS": "2", "MSIINSTALLPERUSER": "1"}) == "per-user"
    assert install_scope({}) == "per-user"
    assert install_root(r"%AppData%\Autodesk\ApplicationPlugins\x.bundle\a.dll") == r"%AppData%\Autodesk\ApplicationPlugins"


def test_parse_package_contents():
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <ApplicationPackage Name="Demo" AppVersion="2.0" ProductCode="{1}">
      <CompanyDetails Name="Acme" Url="https://acme.test" />
      <RuntimeRequirements OS="Win64" Platform="Plant3D" SeriesMin="R25.0" SeriesMax="R26.0" />
      <Components>
        <ComponentEntry AppName="Demo" ModuleName="./Contents/demo.dll" LoadOnAutoCADStartup="True">
          <RuntimeRequirements SeriesMin="R26.0" SeriesMax="R26.0" />
          <Commands GroupName="DEMO"><Command Global="DEMOCMD" Local="DEMOCMD" /></Commands>
        </ComponentEntry>
      </Components>
    </ApplicationPackage>"""
    b = parse_package_contents(xml, "x/PackageContents.xml", None)
    assert (b.name, b.app_version, b.company_name) == ("Demo", "2.0", "Acme")
    assert b.runtime_requirements[0].platform == "Plant3D"
    assert b.runtime_requirements[1].scope == "./Contents/demo.dll"
    assert b.components[0].commands[0].global_name == "DEMOCMD"
    assert b.components[0].commands[0].group == "DEMO"


@pytest.mark.skipif(not REAL_PLUGIN.exists() or not list(REAL_PLUGIN.glob("*.msi")), reason="real P&ID Exporter MSI not present")
def test_real_pid_exporter_msi(tmp_path):
    _, run_dir = run_intake(REAL_PLUGIN, tmp_path / "runs")
    facts = run_static_read(run_dir)
    assert facts.properties["Manufacturer"] == "Kleen Software GmbH"
    assert facts.install_roots == [r"%AppData%\Autodesk\ApplicationPlugins"]
    assert facts.bundles and facts.bundles[0].runtime_requirements[0].platform == "Plant3D"
    assert any(d.name == "Help.html" for d in facts.embedded_documents)
    assert any("EntitlementApiWrapper.dll" in n for n in facts.notable_files)


def test_real_pid_importer_msi_with_long_file_keys(tmp_path):
    # the same DLLs for Revit 2021-2027 and ~100-character File keys: renaming a duplicate after its key
    # passed Windows' 260-character path limit and S1 crashed
    _, run_dir = run_intake(REAL_PLUGIN.parent / "pid-connector-importer", tmp_path / "runs")
    facts = run_static_read(run_dir)
    assert facts.properties["ProductCode"] == "{340D7979-E823-4954-A8CE-978143CAC161}"
    assert facts.bundles and facts.ui_text is not None
    assert not any("could not unpack" in w for w in facts.warnings)
