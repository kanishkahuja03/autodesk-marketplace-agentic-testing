"""The app's own UI text (LOAD_TESTS_PLAN.md L22, ARCHITECTURE.md D60): readable strings from the
binaries in the installer, as the citable source U1 for Agent 1 and for the judge.

Windows UI text (.NET user strings and resources, Win32 string tables) is stored as UTF-16, so only UTF-16
runs are read. Nothing is executed; the binaries are only read as bytes. The result is a *hint*: shared
DLLs can contain text of related products, so only strings that a test cites count.
"""

import re

BINARY_EXTENSIONS = {".dll", ".exe"}
MAX_BINARY_BYTES = 10_000_000
# Third-party libraries add thousands of strings that are never the app's UI
LIBRARY_PREFIXES = ("microsoft.", "system.", "newtonsoft.", "communitytoolkit.", "windowsbase", "presentation")
MAX_STRINGS_PER_FILE = 400
MAX_TOTAL_CHARS = 40_000

_UTF16 = re.compile(rb"(?:[\x20-\x7e\xa0-\xff]\x00){3,200}")
_LETTER = re.compile(r"[A-Za-zÀ-ÿ]")
_DOTTED_NAME = re.compile(r"^[\w`<>$]+(\.[\w`<>$]+)+$")  # e.g. pidexport.Properties.Resources
_NOISE = {"VS_VERSION_INFO", "VarFileInfo", "StringFileInfo", "Translation", "FileDescription", "FileVersion",
          "InternalName", "LegalCopyright", "OriginalFilename", "ProductName", "ProductVersion", "CompanyName",
          "Assembly Version", "Comments", "LegalTrademarks"}


def is_library(file_name: str) -> bool:
    return file_name.casefold().startswith(LIBRARY_PREFIXES)


def _mostly_letters(s: str) -> bool:
    """Real UI text is mostly letters; random bytes that happen to look like UTF-16 are not."""
    chars = [c for c in s if not c.isspace()]
    letters = sum(1 for c in chars if _LETTER.match(c))
    return letters >= 2 and letters >= 0.6 * len(chars)


def ui_strings(data: bytes) -> list[str]:
    """Readable UTF-16 strings in a binary, in order of appearance, without obvious code names."""
    out = []
    for m in _UTF16.finditer(data):
        s = m.group().decode("utf-16-le", errors="ignore").strip()
        if len(s) < 3 or s in _NOISE or _DOTTED_NAME.match(s) or not _mostly_letters(s):
            continue
        out.append(s)
    return out


def build_ui_text(binaries: list[tuple[str, bytes]]) -> str:
    """One section per binary ('== <install path>'), each string once across all binaries
    (copies for several .NET versions repeat the same text), capped in size."""
    seen: set[str] = set()
    sections: list[str] = []
    total = 0
    for label, data in binaries:
        name = label.replace("/", "\\").rsplit("\\", 1)[-1]
        if is_library(name):
            continue
        new = [s for s in dict.fromkeys(ui_strings(data)) if s not in seen][:MAX_STRINGS_PER_FILE]
        if not new:
            continue
        seen.update(new)
        block = "\n".join([f"== {label}", *new])
        if total + len(block) > MAX_TOTAL_CHARS:
            sections.append(f"== (more binaries not shown: the {MAX_TOTAL_CHARS:,}-character limit was reached)")
            break
        sections.append(block)
        total += len(block)
    return "\n\n".join(sections)
