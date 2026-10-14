"""Checks that the skill files the agents load are present and well-formed. Run with: uv run pytest"""

import re
from pathlib import Path

import pytest

from mpagent.hostnotes import front_matter, host_process
from mpagent.models import HostProcess

SKILLS = Path(__file__).parent.parent / "skills"
SRC = Path(__file__).parent.parent / "src" / "mpagent"
EXPECTED = ["test-design/SKILL.md", "hosts/autocad-plant3d.md", "hosts/none.md",
            "execute/windows-installer.md", "execute/evidence.md", "execute/host-interaction.md"]
# Generic parts must not name a product (FUNCTIONAL_TESTS_PLAN.md, rule kept from D1)
PRODUCT_NAMES = re.compile(r"plant ?3d|autocad|acad|p&id", re.IGNORECASE)
GENERIC_FILES = [SKILLS / "execute" / "host-interaction.md", SRC / "hostnotes.py", SRC / "execute" / "host.py",
                 SRC / "execute" / "ui_tree.py", SRC / "execute" / "verdict.py"]


@pytest.mark.parametrize("rel", EXPECTED)
def test_skill_has_frontmatter(rel):
    text = (SKILLS / rel).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fields = front_matter(text)
    assert str(fields["name"]).strip() and str(fields["description"]).strip()


def test_host_note_name_matches_file_name():
    # host_id = file name without .md; Agent 1 picks from these
    for note in (SKILLS / "hosts").glob("*.md"):
        assert front_matter(note.read_text(encoding="utf-8"))["name"] == note.stem


def test_host_process_front_matter():
    # code reads it (FUNCTIONAL_TESTS_PLAN.md L9); 'none' has no host to start
    hp = host_process("autocad-plant3d", SKILLS / "hosts")
    assert isinstance(hp, HostProcess) and hp.processes and hp.args
    for pattern in (hp.locate.match, hp.main_window, hp.new_document):
        re.compile(pattern)
    assert host_process("none", SKILLS / "hosts") is None and host_process("unknown", SKILLS / "hosts") is None


@pytest.mark.parametrize("path", GENERIC_FILES, ids=lambda p: p.name)
def test_generic_files_name_no_product(path):
    assert not PRODUCT_NAMES.search(path.read_text(encoding="utf-8"))


def test_required_coverage_keys_are_in_test_design_skill():
    # The self-check (ARCHITECTURE.md D24) looks for exactly these keys
    text = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "`install_exit_code`" in text and "`uninstall_entry_exists`" in text


def test_load_rules_are_in_the_skills():
    design = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "`LOAD-000`" in design and "seen_in_ui" in design and '["LOAD-000"]' in design
    host = (SKILLS / "execute" / "host-interaction.md").read_text(encoding="utf-8")
    assert 'mode="launch_executable"' in host and 'mode="kill"' in host and "one-time" in host
    assert "You decide what to do with each one" in host and "smallest lasting effect" in host
    assert "Never choose \"Always" in host and "Document every dialog in the `notes`" in host
    assert "timeout` at most 105" in host and "Then stop the LOAD tests" not in host  # no blanket stop rule


def test_uninstall_is_silent_and_files_are_read_only():
    # The Programs and Features UI recipe caused wrong-row selections (runs 20261013-132121, -145150);
    # uninstall is now silent like the install, and Agent 2 never writes files.
    text = (SKILLS / "execute" / "windows-installer.md").read_text(encoding="utf-8")
    assert "'/x','<ProductCode>'" in text and "uninstall_exit_code" in text
    assert "appwiz.cpl" not in text and "Search Box" not in text
    assert "you never write, copy, move or delete files" in text
    design = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "Silent uninstall finishes" in design and "Control Panel" not in design
