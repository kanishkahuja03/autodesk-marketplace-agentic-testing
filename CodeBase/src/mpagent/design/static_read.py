"""Stage 1: Installer static read.

Reads the installer file *without running it* and writes installer_facts.json:
  - MSI: properties, the files it would install and where, custom actions, upgrade rules, registry,
    plus PackageContents.xml and readable documents (e.g. Help.html) unpacked from its embedded cabinet.
  - ZIP containing a .bundle: PackageContents.xml and the file list.
  - EXE: only basic facts for now.

Every fact here comes from the installer file. The machine is not inspected.
"""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from mpagent.design.intake import extract_text, sha256_of
from mpagent.design.msi import MsiDatabase
from mpagent.models import (
    BundleCommand,
    BundleComponent,
    BundleManifest,
    CustomActionInfo,
    EmbeddedDocument,
    InstalledFile,
    InstallerFacts,
    IntakeManifest,
    RegistryEntry,
    RuntimeRequirement,
    UpgradeRule,
)


class StaticReadError(Exception):
    pass


# MSI properties worth recording (most of the ~100 properties are UI text).
INTERESTING_PROPERTIES = [
    "ProductName", "ProductVersion", "Manufacturer", "ProductCode", "UpgradeCode", "ProductLanguage",
    "ALLUSERS", "MSIINSTALLPERUSER", "ARPNOREMOVE", "ARPNOMODIFY", "ARPNOREPAIR", "ARPSYSTEMCOMPONENT",
    "ARPCONTACT", "ARPHELPLINK", "ARPURLINFOABOUT", "ARPCOMMENTS", "DOCUMENTATIONURL", "EULAURL",
]  # fmt: skip

# Windows Installer's built-in folder names -> the environment-style placeholder people know.
STANDARD_FOLDERS = {
    "ProgramFilesFolder": "%ProgramFiles(x86)%",
    "ProgramFiles64Folder": "%ProgramFiles%",
    "CommonFilesFolder": "%CommonProgramFiles(x86)%",
    "CommonFiles64Folder": "%CommonProgramFiles%",
    "CommonAppDataFolder": "%ProgramData%",
    "AppDataFolder": "%AppData%",
    "LocalAppDataFolder": "%LocalAppData%",
    "WindowsFolder": "%WINDIR%",
    "TempFolder": "%TEMP%",
    "PersonalFolder": "%USERPROFILE%\\Documents",
}
OTHER_STANDARD_FOLDERS = {
    "SystemFolder", "System64Folder", "System16Folder", "DesktopFolder", "ProgramMenuFolder", "StartMenuFolder",
    "StartupFolder", "FontsFolder", "SendToFolder", "TemplateFolder", "FavoritesFolder", "NetHoodFolder",
    "PrintHoodFolder", "RecentFolder", "AdminToolsFolder", "MyPicturesFolder", "ProfilesFolder",
}  # fmt: skip

# Custom action type: low 6 bits = what kind of action it is.
CUSTOM_ACTION_KINDS = {
    1: "runs a DLL function stored in the installer",
    2: "runs an EXE stored in the installer",
    5: "runs JScript stored in the installer",
    6: "runs VBScript stored in the installer",
    17: "runs a DLL function from an installed file",
    18: "runs an installed EXE",
    19: "shows an error message and stops the installation",
    21: "runs JScript from an installed file",
    22: "runs VBScript from an installed file",
    34: "runs an EXE from a folder",
    35: "sets a folder path",
    37: "runs inline JScript",
    38: "runs inline VBScript",
    50: "runs an EXE named by a property",
    51: "sets a property",
    53: "runs JScript from a property",
    54: "runs VBScript from a property",
}
CUSTOM_ACTION_FLAGS = {0x400: "deferred", 0x800: "rollback", 0x200: "commit", 0x2000: "runs as SYSTEM (no impersonation)"}

REGISTRY_ROOTS = {"-1": "HKLM or HKCU (depends on install scope)", "0": "HKCR", "1": "HKCU", "2": "HKLM", "3": "HKU"}

# File types worth unpacking from the installer and reading.
DOC_EXTENSIONS = {".htm", ".html", ".txt", ".md", ".pdf"}
MAX_EMBEDDED_DOC_BYTES = 5 * 1024 * 1024

# File names that point to licensing / entitlement checks.
NOTABLE_NAME_PATTERNS = {
    r"entitlement": "file name mentions 'entitlement' (Autodesk store licence check API)",
    r"licen[cs]": "file name mentions 'licence/license'",
    r"activat": "file name mentions 'activation'",
    r"adlm|flexnet|flexlm": "file name suggests a licensing library",
}


# ---------------------------------------------------------------- helpers


def long_name(msi_name: str) -> str:
    """MSI stores names as 'SHORT~1.DLL|LongName.dll'; return the long name."""
    return msi_name.split("|")[-1]


def target_dir_name(default_dir: str) -> str:
    """Directory.DefaultDir is 'target:source'; each part may be 'short|long'. Return the target long name."""
    return long_name(default_dir.split(":")[0])


def attr(element: ET.Element, name: str) -> str | None:
    """XML attribute lookup that ignores upper/lower case (publishers aren't consistent)."""
    lname = name.lower()
    for key, value in element.attrib.items():
        if key.lower() == lname:
            return value
    return None


def children(element: ET.Element, tag: str) -> list[ET.Element]:
    ltag = tag.lower()
    return [c for c in element if c.tag.split("}")[-1].lower() == ltag]


# ---------------------------------------------------------------- PackageContents.xml


def parse_package_contents(xml_bytes: bytes, source: str, install_path: str | None) -> BundleManifest:
    root = ET.fromstring(xml_bytes)
    company = next(iter(children(root, "CompanyDetails")), None)

    def runtime(el: ET.Element, scope: str) -> list[RuntimeRequirement]:
        return [
            RuntimeRequirement(
                scope=scope,
                os=attr(rr, "OS"),
                platform=attr(rr, "Platform"),
                series_min=attr(rr, "SeriesMin"),
                series_max=attr(rr, "SeriesMax"),
            )
            for rr in children(el, "RuntimeRequirements")
        ]

    requirements = runtime(root, "package")
    components: list[BundleComponent] = []
    for comps in children(root, "Components"):
        requirements += runtime(comps, "components")
        for entry in children(comps, "ComponentEntry"):
            module = attr(entry, "ModuleName")
            requirements += runtime(entry, module or "component")
            commands = [
                BundleCommand(global_name=attr(cmd, "Global"), local_name=attr(cmd, "Local"), group=attr(cmds, "GroupName"))
                for cmds in children(entry, "Commands")
                for cmd in children(cmds, "Command")
            ]
            components.append(
                BundleComponent(
                    app_name=attr(entry, "AppName"),
                    module_name=module,
                    app_type=attr(entry, "AppType"),
                    description=attr(entry, "AppDescription"),
                    load_on_startup=attr(entry, "LoadOnAutoCADStartup"),
                    load_on_command=attr(entry, "LoadOnCommandInvocation"),
                    commands=commands,
                )
            )

    return BundleManifest(
        source=source,
        install_path=install_path,
        name=attr(root, "Name"),
        app_version=attr(root, "AppVersion"),
        author=attr(root, "Author"),
        description=attr(root, "Description"),
        product_code=attr(root, "ProductCode"),
        upgrade_code=attr(root, "UpgradeCode"),
        company_name=attr(company, "Name") if company is not None else None,
        company_url=attr(company, "Url") if company is not None else None,
        company_email=attr(company, "Email") if company is not None else None,
        runtime_requirements=requirements,
        components=components,
    )


# ---------------------------------------------------------------- MSI


def resolve_directories(directory_rows, overrides: dict[str, str]) -> dict[str, str]:
    """Turn the MSI Directory table (a tree of parent links) into full paths."""
    table = {r["Directory"]: r for r in directory_rows}
    cache: dict[str, str] = {}

    def resolve(d: str, depth: int = 0) -> str:
        if d in cache:
            return cache[d]
        if depth > 50:
            return f"[{d}]"  # guard against a broken (circular) table
        if d in overrides:
            m = re.fullmatch(r"\[([\w.]+)\]", overrides[d])
            if m and (m.group(1) in table or m.group(1) in STANDARD_FOLDERS):
                path = resolve(m.group(1), depth + 1)
            else:
                path = f"<set during install to {overrides[d]}>"
        elif d in STANDARD_FOLDERS:
            path = STANDARD_FOLDERS[d]
        elif d in OTHER_STANDARD_FOLDERS:
            path = f"[{d}]"
        elif d not in table or not table[d]["Directory_Parent"] or d == "TARGETDIR":
            path = "[TARGETDIR]"
        else:
            parent = resolve(table[d]["Directory_Parent"], depth + 1)
            name = target_dir_name(table[d]["DefaultDir"] or ".")
            path = parent if name == "." else f"{parent}\\{name}"
        cache[d] = path
        return path

    return {d: resolve(d) for d in table}


def decode_custom_action(row) -> CustomActionInfo:
    code = int(row["Type"] or 0)
    base = code & 0x3F
    return CustomActionInfo(
        name=row["Action"],
        type_code=code,
        kind=CUSTOM_ACTION_KINDS.get(base, f"custom action type {base}"),
        flags=[label for bit, label in CUSTOM_ACTION_FLAGS.items() if code & bit],
        source=row["Source"],
        target=row["Target"],
    )


def install_scope(props: dict[str, str]) -> str:
    allusers = props.get("ALLUSERS", "")
    if allusers == "1":
        return "per-machine"
    if allusers == "2":
        return "per-user" if props.get("MSIINSTALLPERUSER") == "1" else "dual"
    return "per-user"


def install_root(path: str) -> str:
    """'%AppData%\\Autodesk\\ApplicationPlugins\\x.bundle\\a.dll' -> '%AppData%\\Autodesk\\ApplicationPlugins'."""
    parts = path.split("\\")
    return "\\".join(parts[:3]) if len(parts) > 3 else "\\".join(parts[:-1])


def extract_from_cabinet(db: MsiDatabase, msi_path: Path, media_rows, file_rows, out_dir: Path) -> dict[str, Path]:
    """Unpack selected files from the MSI's cabinet(s). Returns {File key: extracted path}.

    The cabinet is copied out of the MSI (or found next to it), then Windows' own expand.exe pulls out
    only the requested files. Nothing from the installer is executed.
    """
    media = sorted(media_rows, key=lambda r: int(r["LastSequence"] or 0))
    wanted: dict[str, list] = {}
    for f in file_rows:
        seq = int(f["Sequence"] or 0)
        cab = next((m["Cabinet"] for m in media if seq <= int(m["LastSequence"] or 0) and m["Cabinet"]), None)
        if cab:
            wanted.setdefault(cab, []).append(f)

    cab_dir = out_dir / "_cabinets"
    cab_dir.mkdir(parents=True, exist_ok=True)
    expand = Path(shutil.which("expand.exe") or r"C:\Windows\System32\expand.exe")
    extracted: dict[str, Path] = {}
    try:
        for cab, files in wanted.items():
            if cab.startswith("#"):
                cab_path = cab_dir / cab[1:]
                cab_path.write_bytes(db.read_stream(cab[1:]))
            else:
                cab_path = msi_path.parent / cab
                if not cab_path.exists():
                    continue
            for f in files:
                key = f["File"]
                subprocess.run(
                    [str(expand), str(cab_path), f"-F:{key}", str(out_dir)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                raw = out_dir / key
                if raw.exists():
                    final = out_dir / long_name(f["FileName"])
                    if final.exists():  # same long name in two folders: keep both
                        final = out_dir / f"{key}_{long_name(f['FileName'])}"
                    raw.replace(final)
                    extracted[key] = final
    finally:
        shutil.rmtree(cab_dir, ignore_errors=True)
    return extracted


def read_msi(msi_path: Path, run_dir: Path, facts: InstallerFacts) -> None:
    with MsiDatabase(msi_path) as db:
        props = {r["Property"]: r["Value"] or "" for r in db.rows("Property")}
        facts.properties = {k: props[k] for k in INTERESTING_PROPERTIES if k in props}
        facts.install_scope = install_scope(props)

        actions = db.rows("CustomAction")
        facts.custom_actions = [decode_custom_action(r) for r in actions]
        # Actions of type 35/51 that set a folder path change where files go at install time.
        overrides = {r["Source"]: r["Target"] or "" for r in actions if int(r["Type"] or 0) & 0x3F in (35, 51)}
        dirs = resolve_directories(db.rows("Directory"), overrides)

        components = {r["Component"]: r for r in db.rows("Component")}
        file_rows = db.rows("File")
        file_paths: dict[str, str] = {}
        for f in sorted(file_rows, key=lambda r: int(r["Sequence"] or 0)):
            comp = components.get(f["Component_"], {})
            folder = dirs.get(comp.get("Directory_") or "", "[unknown]")
            path = f"{folder}\\{long_name(f['FileName'])}"
            file_paths[f["File"]] = path
            facts.files.append(
                InstalledFile(
                    name=long_name(f["FileName"]),
                    install_path=path,
                    size_bytes=int(f["FileSize"]) if f["FileSize"] else None,
                    version=f["Version"] or None,
                    condition=comp.get("Condition"),
                )
            )
        facts.install_roots = sorted({install_root(p) for p in file_paths.values()})

        for r in db.rows("Upgrade"):
            a = int(r["Attributes"] or 0)
            facts.upgrade_rules.append(
                UpgradeRule(
                    upgrade_code=r["UpgradeCode"],
                    version_min=r["VersionMin"],
                    version_max=r["VersionMax"],
                    only_detect=bool(a & 0x2),
                    removes_older=bool(r["Remove"]) and not a & 0x2,
                )
            )
        facts.launch_conditions = [
            {"condition": r["Condition"], "message": r["Description"]} for r in db.rows("LaunchCondition")
        ]
        facts.registry = [
            RegistryEntry(root=REGISTRY_ROOTS.get(r["Root"] or "", r["Root"] or ""), key=r["Key"], name=r["Name"], value=r["Value"])
            for r in db.rows("Registry")
        ]

        # Unpack only the plug-in manifest(s) and readable documents.
        to_extract = [
            f
            for f in file_rows
            if long_name(f["FileName"]).lower() == "packagecontents.xml"
            or (
                Path(long_name(f["FileName"])).suffix.lower() in DOC_EXTENSIONS
                and int(f["FileSize"] or 0) <= MAX_EMBEDDED_DOC_BYTES
            )
        ]
        extract_dir = run_dir / "installer_extract"
        extracted = extract_from_cabinet(db, msi_path, db.rows("Media"), to_extract, extract_dir) if to_extract else {}

    for f in to_extract:
        if f["File"] not in extracted:
            facts.warnings.append(f"could not unpack {long_name(f['FileName'])} from the installer")
    add_extracted(extracted, file_paths, run_dir, facts)


def add_extracted(extracted: dict[str, Path], install_paths: dict[str, str], run_dir: Path, facts: InstallerFacts) -> None:
    """Parse unpacked PackageContents.xml files and turn unpacked documents into citable text (I1, I2, ...)."""
    doc_n = 0
    for key, path in extracted.items():
        rel = path.relative_to(run_dir).as_posix()
        if path.name.lower().endswith("packagecontents.xml"):
            try:
                facts.bundles.append(parse_package_contents(path.read_bytes(), rel, install_paths.get(key)))
            except ET.ParseError as e:
                facts.warnings.append(f"{rel}: not valid XML ({e})")
            continue
        text, doc_warnings = extract_text(path)
        if not text.strip():
            continue
        doc_n += 1
        doc_id = f"I{doc_n}"
        text_rel = Path("documents") / f"{doc_id}_{path.stem}.txt"
        (run_dir / text_rel).parent.mkdir(exist_ok=True)
        (run_dir / text_rel).write_text(text, encoding="utf-8")
        facts.embedded_documents.append(
            EmbeddedDocument(
                doc_id=doc_id,
                name=path.name,
                install_path=install_paths.get(key),
                text_file=text_rel.as_posix(),
                line_count=text.count("\n"),
                char_count=len(text),
            )
        )
        facts.warnings.extend(f"{doc_id} ({path.name}): {w}" for w in doc_warnings)


# ---------------------------------------------------------------- ZIP (.bundle)


def read_zip_bundle(zip_path: Path, run_dir: Path, facts: InstallerFacts) -> None:
    extract_dir = run_dir / "installer_extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("/", "\\")
            facts.files.append(InstalledFile(name=Path(name).name, install_path=f"[copied manually]\\{name}", size_bytes=info.file_size))
            lower = name.lower()
            readable = Path(lower).suffix in DOC_EXTENSIONS and info.file_size <= MAX_EMBEDDED_DOC_BYTES
            if lower.endswith("packagecontents.xml") or readable:
                target = extract_dir / f"{len(extracted)}_{Path(name).name}"
                target.write_bytes(zf.read(info))  # written under our own name: zip paths are never trusted
                extracted[name] = target
    facts.install_roots = ["[copied manually]"]
    add_extracted(extracted, {k: f"[copied manually]\\{k}" for k in extracted}, run_dir, facts)


# ---------------------------------------------------------------- main entry


def flag_notable_files(facts: InstallerFacts) -> None:
    seen = set()
    for f in facts.files:
        for pattern, reason in NOTABLE_NAME_PATTERNS.items():
            if re.search(pattern, f.name, re.IGNORECASE) and f.name not in seen:
                seen.add(f.name)
                facts.notable_files.append(f"{f.name}: {reason}")


def run_static_read(run_dir: Path) -> InstallerFacts:
    """Run Stage 1 on a run folder created by Stage 0. Saves installer_facts.json in that folder."""
    run_dir = run_dir.resolve()
    manifest_path = run_dir / "intake_manifest.json"
    if not manifest_path.exists():
        raise StaticReadError(f"no intake_manifest.json in {run_dir}; run Stage 0 (mpagent intake) first")
    manifest = IntakeManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    installer_path = Path(manifest.input_dir) / manifest.installer.file
    if not installer_path.exists():
        raise StaticReadError(f"installer not found: {installer_path}")
    if sha256_of(installer_path) != manifest.installer.sha256:
        raise StaticReadError("the installer changed since Stage 0 ran; run mpagent intake again")

    facts = InstallerFacts(
        installer_file=manifest.installer.file, installer_type=manifest.installer.type, sha256=manifest.installer.sha256
    )
    if facts.installer_type == "msi":
        read_msi(installer_path, run_dir, facts)
    elif facts.installer_type == "zip-bundle":
        read_zip_bundle(installer_path, run_dir, facts)
    else:
        facts.warnings.append(f"static read of .{facts.installer_type} installers is not supported yet; only basic facts recorded")

    if facts.installer_type != "exe" and not facts.bundles:
        facts.warnings.append("no PackageContents.xml found in the installer")
    flag_notable_files(facts)
    (run_dir / "installer_facts.json").write_text(facts.model_dump_json(indent=2), encoding="utf-8")
    return facts


def latest_run(path: Path) -> Path:
    """Accept a run folder, or runs/<plugin> and pick its newest run."""
    if (path / "intake_manifest.json").exists():
        return path
    runs = sorted((p for p in path.iterdir() if (p / "intake_manifest.json").exists()), reverse=True) if path.is_dir() else []
    if not runs:
        raise StaticReadError(f"no Stage 0 run found in {path}")
    return runs[0]
