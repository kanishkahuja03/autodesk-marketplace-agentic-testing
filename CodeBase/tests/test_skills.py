"""Checks that the skill files the agents load are present and well-formed. Run with: uv run pytest"""

import re
from pathlib import Path

import pytest

from mpagent.hostnotes import front_matter, host_process
from mpagent.models import HostProcess

SKILLS = Path(__file__).parent.parent / "skills"
SRC = Path(__file__).parent.parent / "src" / "mpagent"
EXPECTED = ["test-design/SKILL.md", "hosts/autocad-plant3d.md", "hosts/none.md",
            "execute/windows-installer.md", "execute/evidence.md", "execute/host-interaction.md",
            "execute/judge.md"]
# Generic parts must not name a product (LOAD_TESTS_PLAN.md, rule kept from D1)
PRODUCT_NAMES = re.compile(r"plant ?3d|autocad|acad|p&id", re.IGNORECASE)
GENERIC_FILES = [SKILLS / "execute" / "host-interaction.md", SRC / "hostnotes.py", SRC / "execute" / "host.py",
                 SRC / "execute" / "context.py", SRC / "design" / "samples.py",
                 SRC / "execute" / "ui_tree.py", SRC / "execute" / "verdict.py",
                 SKILLS / "execute" / "judge.md", SRC / "execute" / "judge.py", SRC / "design" / "ui_text.py"]


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
    # code reads it (LOAD_TESTS_PLAN.md L9); 'none' has no host to start
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
    assert "`LOAD-000`" in design and "check: judged" in design and '["LOAD-000"]' in design
    assert "`LOAD-002`" in design and "`U1`" in design and "seen_in_ui" not in design
    host = (SKILLS / "execute" / "host-interaction.md").read_text(encoding="utf-8")
    assert 'mode="launch_executable"' in host and 'mode="kill"' in host and "one-time" in host
    assert "**You decide what to do**" in host and "smallest lasting effect" in host
    assert "never choose \"Always" in host and "Document every dialog in the `notes`" in host
    assert "`timeout` at most 105" in host
    assert "**Show, never run.**" in host and "Make it visible." in host  # generic exploration (L24, D65)


def test_action_policy_and_restart_rule_are_in_the_host_skill():
    # one policy by lasting effect and at most one restart per test (FUNC_TESTS_PLAN.md F4, F9)
    host = (SKILLS / "execute" / "host-interaction.md").read_text(encoding="utf-8")
    for phrase in ("**0 View**", "**1 Session**", "**2 Reversible**", "**3 Lasting**",
                   "treat it as class 3", "you **never run a feature**", "**Each test may use at most one restart.**",
                   "is a normal start, not a restart"):
        assert phrase in host, phrase
    evidence = (SKILLS / "execute" / "evidence.md").read_text(encoding="utf-8")
    assert "Saved as evidence:" in evidence and "the reviewer sees those first" in evidence
    # FUNC (FUNC_TESTS_PLAN.md F4, F5, F9): run only the named feature, save only into the output folder, tidy up
    for phrase in ("## 7. FUNC tests", "**Run only the feature the test names**", ("**Save only into the test's output "
                   "folder.**"), "**Tidy up before the next test:**", "never the original"):
        assert phrase in host, phrase
    assert "go only into that test's output folder" in evidence
    design = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ("## 4b. FUNC", "**A feature card for every feature", "**all four** hold",
                   "**one `judged` claim per statement in `results`**", "check: output_created", "Never invent content"):
        assert phrase in design, phrase


def test_skills_hold_no_host_or_app_specific_knowledge():
    # generic-skills experiment (2026-10-14): only the host profile's front matter may name the host
    words = re.compile(r"p&id|plant ?3d|autocad|ribbon(?!_tab)|hinweis|ctrl\+n|template|palette|kleen|revit",
                       re.IGNORECASE)
    for path in SKILLS.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if path.parent.name == "navigation":
            continue  # host navigation files may name their host's UI (Q14); test_navigation_names_no_app checks them
        if path.parent.name == "hosts":
            text = text.split("\n---\n", 1)[1]  # front matter is data for code; check only the prose
            text = re.sub(r"^# Host: .*$|^An AutoCAD-based Autodesk product\..*$", "", text, flags=re.MULTILINE)
        assert not words.search(text), f"{path.relative_to(SKILLS)}: {words.search(text).group()}"


def test_uninstall_is_silent_and_files_are_read_only():
    # The Programs and Features UI recipe caused wrong-row selections (runs 20261013-132121, -145150);
    # uninstall is now silent like the install, and Agent 2 never writes files.
    text = (SKILLS / "execute" / "windows-installer.md").read_text(encoding="utf-8")
    assert "'/x','<ProductCode>'" in text and "uninstall_exit_code" in text
    assert "appwiz.cpl" not in text and "Search Box" not in text
    assert "you never write, copy, move or delete files" in text
    design = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "Silent uninstall finishes" in design and "Control Panel" not in design


def test_navigation_file_is_named_by_the_host_profile_and_names_no_app():
    # host-only navigation for Agent 2 (FUNC_TESTS_PLAN.md Q14): found through the host profile's front matter;
    # it describes the host's own UI and never an app under test
    from mpagent.execute import agent2
    from mpagent.hostnotes import host_navigation

    nav = host_navigation("autocad-plant3d", SKILLS / "hosts")
    assert nav and "# Navigating AutoCAD Plant 3D" in nav and "host-interaction skill" in nav
    assert host_navigation("none", SKILLS / "hosts") is None
    app_words = re.compile(r"kleen|connector|exporter|revit|export p&id|json", re.IGNORECASE)
    for path in (SKILLS / "hosts" / "navigation").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert not app_words.search(text), f"{path.name}: {app_words.search(text).group()}"
    assert "# Navigating AutoCAD Plant 3D" in agent2.instructions("autocad-plant3d", with_host_interaction=True)
    assert "# Navigating" not in agent2.instructions("autocad-plant3d")  # only with the host tests


def test_waitfor_takes_plain_text_and_load000_can_open_the_sample():
    host = (SKILLS / "execute" / "host-interaction.md").read_text(encoding="utf-8")
    assert "**plain text contained in the window title**" in host  # run 20261016-130450: a regex waited 105 s
    assert '"LOAD-000 context"' in host and "keep working in it" in host


def test_testability_is_judged_from_the_documents_not_from_u1():
    # run 20261016-130450: Agent 1 marked a documented feature untestable from licence messages in U1
    design = (SKILLS / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "**Judge the four points from the documents (`D…`, `I…`) only.**" in design
    assert "**`U1` never makes a feature untestable:**" in design
