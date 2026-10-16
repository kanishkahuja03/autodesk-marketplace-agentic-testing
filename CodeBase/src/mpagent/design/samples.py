"""The sample (FUNC_TESTS_PLAN.md F18, Q7a, Q13, Q14): listed for Agent 1, never opened or interpreted.

TEMPORARY for the POC: one fixed sample, SAMPLES_DIR in .env, either a file (e.g. one document) or a folder
(e.g. a project with several files). Code only lists names and sizes. Agent 1 decides whether it gives a
feature's context its content and names it in the feature card; the execution side copies it into the run
folder for Agent 2. (After the POC: several samples per input.)
"""

from dataclasses import dataclass
from pathlib import Path

MAX_FILES_LISTED = 200  # per sample; the rest is counted, not listed


@dataclass(frozen=True)
class Sample:
    name: str  # the file's or folder's name, used in feature cards
    path: Path  # where it is on this machine (copied by the execution side, never opened)
    files: list[tuple[str, int]]  # (path inside the sample, size in bytes), at most MAX_FILES_LISTED
    total_files: int
    total_bytes: int


def list_samples(sample: Path | None) -> list[Sample]:
    """The configured sample as a one-item list; [] when none is set or it doesn't exist."""
    if sample is None:
        return []
    if sample.is_file():
        files = [(sample.name, sample.stat().st_size)]
    elif sample.is_dir():
        files = [(p.relative_to(sample).as_posix(), p.stat().st_size)
                 for p in sorted(sample.rglob("*"), key=lambda p: p.as_posix().lower()) if p.is_file()]
    else:
        return []
    return [Sample(sample.name, sample, files[:MAX_FILES_LISTED], len(files), sum(size for _, size in files))]


def render_samples(samples: list[Sample]) -> str:
    """The samples block of Agent 1's input. Not a citable source: names and sizes only."""
    if not samples:
        return ("<samples>\nNo samples are available. A feature whose claims need a context with content gets no "
                "test (open question).\n</samples>")
    blocks = []
    for s in samples:
        lines = [f"{path} ({size:,} bytes)" for path, size in s.files]
        if s.total_files > len(s.files):
            lines.append(f"... and {s.total_files - len(s.files)} more files")
        kind = "folder" if s.path.is_dir() else "file"
        blocks.append(f'<sample name="{s.name}" kind="{kind}" files="{s.total_files}" bytes="{s.total_bytes:,}">\n'
                      + "\n".join(lines) + "\n</sample>")
    return "<samples>\n" + "\n".join(blocks) + "\n</samples>"
