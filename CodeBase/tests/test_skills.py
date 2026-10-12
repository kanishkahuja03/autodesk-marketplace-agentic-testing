"""Checks that the skill files the agents load are present and well-formed. Run with: uv run pytest"""

from pathlib import Path

import pytest

SKILLS = Path(__file__).parent.parent / "skills"
EXPECTED = ["test-design/SKILL.md", "hosts/autocad-plant3d.md", "hosts/none.md",
            "execute/windows-installer.md", "execute/evidence.md"]


@pytest.mark.parametrize("rel", EXPECTED)
def test_skill_has_frontmatter(rel):
    text = (SKILLS / rel).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    header = text.split("---\n", 2)[1]
    fields = dict(line.split(":", 1) for line in header.strip().splitlines())
    assert fields["name"].strip() and fields["description"].strip()


def test_host_note_name_matches_file_name():
    # host_id = file name without .md; Agent 1 picks from these
    for note in (SKILLS / "hosts").glob("*.md"):
        header = note.read_text(encoding="utf-8").split("---\n", 2)[1]
        assert f"name: {note.stem}" in header


def test_required_coverage_keys_are_in_test_design_skill():
    # The self-check (ARCHITECTURE.md D24) looks for exactly these keys
    text = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "`install_exit_code`" in text and "`uninstall_entry_exists`" in text
