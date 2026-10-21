"""Tests for UNIN-000 "nothing left behind" (ARCHITECTURE.md D64). Run with: uv run pytest"""

from mpagent.execute import footprint


def fake_machine(tmp_path, monkeypatch):
    """APPDATA/LOCALAPPDATA/ProgramData in a temp folder, no registry."""
    for name in ("APPDATA", "LOCALAPPDATA", "ProgramData"):
        (tmp_path / name).mkdir()
        monkeypatch.setenv(name, str(tmp_path / name))
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(footprint, "REGISTRY_ROOTS", ())
    (tmp_path / "APPDATA" / "Vendor" / "Plugins").mkdir(parents=True)
    (tmp_path / "LOCALAPPDATA" / "Existing").mkdir()
    return [r"%APPDATA%\Vendor\Plugins"]


def test_new_entries_after_the_uninstall_are_leftovers(tmp_path, monkeypatch):
    # run 20261014-153924: the plug-in left %LocalAppData%\PidConnectorExport, a .NET user.config, HKCU\Software\...
    roots = fake_machine(tmp_path, monkeypatch)
    run = tmp_path / "run"
    run.mkdir()
    footprint.save_before(run, roots)
    (tmp_path / "LOCALAPPDATA" / "AppSettings" / "1.0").mkdir(parents=True)          # user settings
    (tmp_path / "LOCALAPPDATA" / "AppSettings" / "1.0" / "user.config").write_text("x")
    (tmp_path / "APPDATA" / "Vendor" / "Plugins" / "app.bundle").mkdir()             # in the install root
    (tmp_path / "ProgramData" / "AppCache").mkdir()                                  # machine-wide
    (tmp_path / "LOCALAPPDATA" / "Temp").mkdir()                                     # Windows' churn

    obs = footprint.record_unin000(run, roots)
    values = {kv.key: kv.value for kv in obs.observed}
    assert values == {"program_leftovers": 2, "settings_leftovers": 1}
    assert len(obs.findings) == 3 and any("(user settings)" in f and "AppSettings" in f for f in obs.findings)
    assert any("app.bundle" in f and "program files" in f for f in obs.findings)
    text = (run / footprint.LEFTOVERS_FILE).read_text()
    assert obs.evidence == [footprint.LEFTOVERS_FILE] and "LOCALAPPDATA\\Temp" not in text  # Windows' own place


def test_nothing_new_means_no_leftovers_and_no_baseline_means_no_observation(tmp_path, monkeypatch):
    roots = fake_machine(tmp_path, monkeypatch)
    run = tmp_path / "run"
    run.mkdir()
    assert footprint.record_unin000(run, roots) is None  # the preflight never saved a baseline
    footprint.save_before(run, roots)
    obs = footprint.record_unin000(run, roots)
    assert {kv.key: kv.value for kv in obs.observed} == {"program_leftovers": 0, "settings_leftovers": 0}
    assert obs.findings == [] and obs.evidence == []


def test_host_churn_can_be_ignored_and_nested_entries_are_reported_once():
    before = {r"DIR:C:\U\A"}
    after = before | {r"DIR:C:\U\Host\Cache", r"DIR:C:\U\App", r"FILE:C:\U\App\x.dat", r"REG:HKCU\Software\App"}
    assert footprint.leftovers(before, after, [r"\\Host\\Cache"]) == [r"DIR:C:\U\App", r"REG:HKCU\Software\App"]
