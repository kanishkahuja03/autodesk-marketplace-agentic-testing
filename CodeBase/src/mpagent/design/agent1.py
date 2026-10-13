"""Agent 1: Test Designer (ARCHITECTURE.md §4, D4, D15, D18, D23, D24).

One LLM agent with no tools reads the evidence pack and returns a TestPlan. Code self-checks the plan;
on errors the agent gets them back and retries (at most 2 times). Then code adds the built-in ENV-000
and writes testcases.yaml / testcases.json / understanding.md. Nothing on the machine is inspected.
"""

import io
from collections.abc import Callable
from pathlib import Path

from agents import Agent, Runner
from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML

from mpagent.config import PROJECT_ROOT, Settings
from mpagent.design.evidence import Source, build_sources, render_pack
from mpagent.design.selfcheck import BUILT_IN_ENV_ID, check_plan
from mpagent.models import (
    Category,
    Check,
    Expectation,
    InstallerFacts,
    IntakeManifest,
    Origin,
    Priority,
    TestCase,
    TestPlan,
)
from mpagent.runlog import Trace, log

SKILLS_DIR = PROJECT_ROOT / "skills"
MAX_RETRIES = 2
TEMPLATES = Path(__file__).parent / "templates"

# (conversation so far) -> (plan, conversation including the answer); replaced by a fake in unit tests
AskFn = Callable[[str | list], tuple[TestPlan, list]]


class Agent1Error(Exception):
    """Agent 1 could not produce a plan that passes the self-check (the pipeline stops before Agent 2)."""


def host_catalogue(skills_dir: Path = SKILLS_DIR) -> dict[str, str]:
    """host_id -> host notes text. The host_id is the file name without .md."""
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted((skills_dir / "hosts").glob("*.md"))}


def instructions(skills_dir: Path = SKILLS_DIR) -> str:
    design = (skills_dir / "test-design" / "SKILL.md").read_text(encoding="utf-8")
    hosts = "\n\n".join(f"### host_id: {hid}\n\n{text}" for hid, text in host_catalogue(skills_dir).items())
    return f"{design}\n\n## Host notes catalogue\n\n{hosts}"


def openai_ask(settings: Settings) -> AskFn:
    """The real LLM call through the OpenAI Agents SDK (no tools, structured output)."""
    agent = Agent(name="test-designer", instructions=instructions(), output_type=TestPlan, model=settings.agent_model())
    if settings.uses_temporary_gemini:
        log.warning("Agent 1 uses the TEMPORARY Gemini fallback (%s); no OpenAI key set", settings.gemini_model)

    def ask(conversation: str | list) -> tuple[TestPlan, list]:
        result = Runner.run_sync(agent, conversation, max_turns=3)
        return result.final_output, result.to_input_list()

    return ask


def design_tests(run_dir: Path, manifest: IntakeManifest, facts: InstallerFacts, ask: AskFn) -> TestPlan:
    """Run Agent 1 with self-check retries, add ENV-000 and write the outputs. Returns the final plan."""
    trace = Trace(run_dir)
    sources = build_sources(run_dir, manifest, facts)
    host_ids = host_catalogue().keys()
    conversation: str | list = render_pack(sources)

    plan: TestPlan | None = None
    errors: list[str] = []
    for attempt in range(1, MAX_RETRIES + 2):
        log.info("Agent 1 attempt %d: asking the model", attempt)
        trace.write("agent1_request", attempt=attempt, input=conversation)
        try:
            plan, conversation = ask(conversation)
        except Exception as e:
            raise Agent1Error(f"LLM call failed: {type(e).__name__}: {e}") from e
        trace.write("agent1_response", attempt=attempt, plan=plan.model_dump(mode="json"))

        errors = check_plan(plan, sources, host_ids)
        trace.write("agent1_selfcheck", attempt=attempt, errors=errors)
        if not errors:
            log.info("Agent 1 attempt %d: self-check passed", attempt)
            break
        log.warning("Agent 1 attempt %d: self-check found %d error(s)", attempt, len(errors))
        for err in errors:
            log.warning("  - %s", err)
        conversation = conversation + [{"role": "user", "content": _retry_message(errors)}]

    if errors:
        _write_yaml(plan, run_dir / "testcases.rejected.yaml")
        raise Agent1Error(f"self-check failed after {MAX_RETRIES} retries ({len(errors)} errors; "
                          "see run.log and testcases.rejected.yaml)")

    plan = add_built_in_tests(plan, facts)
    write_outputs(plan, sources, run_dir)
    return plan


def _retry_message(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors)
    return f"The self-check found these errors in your test plan:\n{lines}\n\nReturn a corrected, complete TestPlan."


def add_built_in_tests(plan: TestPlan, facts: InstallerFacts) -> TestPlan:
    """Prepend ENV-000 (executed by code in the preflight, D23) and make every INST test depend on it."""
    props = facts.properties
    product_code, product_name = props.get("ProductCode"), props.get("ProductName")
    lookup = " or ".join(x for x in (f"ProductCode {product_code}" if product_code else "",
                                     f"DisplayName '{product_name}'" if product_name else "") if x)
    env000 = TestCase(
        id=BUILT_IN_ENV_ID, origin=Origin.BUILT_IN, category=Category.ENV,
        title="App is not installed before the test", source=None, preconditions=[],
        steps=[f"Built-in check run by code before Agent 2: no Uninstall entry with {lookup or 'the product name'}"],
        observe=["preinstalled_entry_exists"],
        expected=[Expectation(key="preinstalled_entry_exists", check=Check.NOT_EXISTS, value=None, values=None)],
        priority=Priority.P1,
    )
    tests = []
    for t in plan.testcases:
        if t.category is Category.INST and BUILT_IN_ENV_ID not in t.preconditions:
            t = t.model_copy(update={"preconditions": [BUILT_IN_ENV_ID, *t.preconditions]})
        tests.append(t)
    return plan.model_copy(update={"testcases": [env000, *tests]})


def write_outputs(plan: TestPlan, sources: list[Source], run_dir: Path) -> None:
    _write_yaml(plan, run_dir / "testcases.yaml")
    (run_dir / "testcases.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False, keep_trailing_newline=True)
    text = env.get_template("understanding.md.j2").render(plan=plan, sources=sources)
    (run_dir / "understanding.md").write_text(text, encoding="utf-8")


def load_plan(path: Path) -> TestPlan:
    return TestPlan.model_validate(_yaml().load(path.read_text(encoding="utf-8")))


def _write_yaml(plan: TestPlan, path: Path) -> None:
    buf = io.StringIO()
    _yaml().dump(plan.model_dump(mode="json"), buf)
    path.write_text(buf.getvalue(), encoding="utf-8")


def _yaml() -> YAML:
    y = YAML(typ="safe", pure=True)
    y.default_flow_style = False
    y.sort_base_mapping_type_on_output = False  # keep field order as in the model
    y.width = 120
    y.allow_unicode = True
    return y
