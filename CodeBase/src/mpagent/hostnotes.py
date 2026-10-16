"""Host notes front matter (LOAD_TESTS_PLAN.md L9): the host facts code needs, read from skills/hosts/<id>.md.

Shared by the design side (the built-in LOAD-000) and the execution side (launch, guardrails, verdict).
Product knowledge stays in the host-notes files; nothing here names a product.
"""

from pathlib import Path

from ruamel.yaml import YAML

from mpagent.config import PROJECT_ROOT
from mpagent.models import HostProcess

HOSTS_DIR = PROJECT_ROOT / "skills" / "hosts"


def front_matter(text: str) -> dict:
    """The YAML between the leading '---' lines of a Markdown file ({} if there is none)."""
    if not text.startswith("---\n"):
        return {}
    header = text.split("---\n", 2)[1]
    return YAML(typ="safe", pure=True).load(header) or {}


def host_process(host_id: str, hosts_dir: Path = HOSTS_DIR) -> HostProcess | None:
    """The host's `host_process` facts, or None for hosts without one (e.g. 'none', 'unknown')."""
    path = hosts_dir / f"{host_id}.md"
    if not path.is_file():
        return None
    data = front_matter(path.read_text(encoding="utf-8")).get("host_process")
    return HostProcess.model_validate(data) if data else None


def host_navigation(host_id: str, hosts_dir: Path = HOSTS_DIR) -> str | None:
    """The host's navigation guidance for Agent 2 (FUNC_TESTS_PLAN.md Q14): the prose file the host profile's
    `navigation:` front matter names, relative to the hosts folder; None if the host has none."""
    path = hosts_dir / f"{host_id}.md"
    if not path.is_file():
        return None
    rel = front_matter(path.read_text(encoding="utf-8")).get("navigation")
    if not rel:
        return None
    nav = hosts_dir / str(rel)
    if not nav.is_file():
        raise FileNotFoundError(f"host profile {host_id}: navigation file not found: {nav}")
    return nav.read_text(encoding="utf-8")
