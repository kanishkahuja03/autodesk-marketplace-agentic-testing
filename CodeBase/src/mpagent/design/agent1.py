"""Agent 1: Test Designer (ARCHITECTURE.md §4, D4, D15, D18, D23, D24).

One LLM agent with no tools reads the evidence pack and returns a TestPlan. Code self-checks the plan;
on errors the agent gets them back and retries (at most 2 times). Then code adds the built-in ENV-000
(and LOAD-000 for hosts with host_process, LOAD_TESTS_PLAN.md L2) and writes testcases.yaml / testcases.json / understanding.md. Nothing on the machine is inspected.
"""

import io
from collections.abc import Callable
from pathlib import Path

from agents import Agent, Runner
from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML

from mpagent.config import PROJECT_ROOT, Settings
from mpagent.design.evidence import Source, build_sources, render_pack
from mpagent.design.samples import Sample, render_input_files, render_samples
from mpagent.design.selfcheck import (
    BUILT_IN_ENV_ID,
    BUILT_IN_LOAD_ID,
    BUILT_IN_UNIN_ID,
    check_plan,
    sample_card,
)
from mpagent.hostnotes import host_process
from mpagent.models import (
    Category,
    Check,
    Expectation,
    FeatureCard,
    HostProcess,
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


def design_tests(run_dir: Path, manifest: IntakeManifest, facts: InstallerFacts, ask: AskFn,
                 samples: list[Sample] = (), inputs: list[Sample] = ()) -> TestPlan:
    """Run Agent 1 with self-check retries, add ENV-000 and write the outputs. Returns the final plan.
    `samples`: the samples folder's listing (FUNC_TESTS_PLAN.md F18); `inputs`: the input files' listing.
    Feature cards may name these."""
    trace = Trace(run_dir)
    sources = build_sources(run_dir, manifest, facts)
    host_ids = host_catalogue().keys()
    load_hosts = [h for h in host_ids if host_process(h)]
    conversation: str | list = (render_pack(sources) + "\n\n" + render_samples(list(samples)) + "\n\n"
                                + render_input_files(list(inputs)))

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

        errors = check_plan(plan, sources, host_ids, load_hosts, [s.name for s in samples], [s.name for s in inputs])
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

    plan = add_built_in_tests(plan, facts, host_process(plan.app.host_id))
    write_outputs(plan, sources, run_dir)
    return plan


def _retry_message(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors)
    return f"The self-check found these errors in your test plan:\n{lines}\n\nReturn a corrected, complete TestPlan."


# the order Agent 2 runs them; the sort is stable, so FUNC tests keep Agent 1's order (FUNC_TESTS_PLAN.md F13)
CATEGORY_ORDER = [Category.ENV, Category.INST, Category.LOAD, Category.FUNC, Category.UNIN]


def add_built_in_tests(plan: TestPlan, facts: InstallerFacts, host: HostProcess | None = None) -> TestPlan:
    """Prepend ENV-000 (executed by code in the preflight, D23) and make every INST test depend on it.
    For a host with host_process, also add LOAD-000 (executed by Agent 2; on the sample when a FUNC test needs one)."""
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
    tests = [env000, *tests]
    if host is not None:
        tests.append(load000(tests, host, sample_card(plan)))
    tests.append(unin000(tests))
    # built-in tests first in their category; stable, so Agent 1's order is kept otherwise
    tests.sort(key=lambda t: (CATEGORY_ORDER.index(t.category), t.origin is not Origin.BUILT_IN))
    return plan.model_copy(update={"testcases": tests})


def unin000(tests: list[TestCase]) -> TestCase:
    """UNIN-000 "nothing left behind" (ARCHITECTURE.md D64): code compares the machine before the install with the
    state after the uninstall. Program leftovers fail it; leftover user settings become findings."""
    uninstalls = [t.id for t in tests if t.category is Category.UNIN
                  and {"uninstall_exit_code", "uninstall_entry_exists"} & set(t.observe)]
    return TestCase(
        id=BUILT_IN_UNIN_ID, origin=Origin.BUILT_IN, category=Category.UNIN,
        title="Nothing of the app is left behind after the uninstall", source=None, preconditions=uninstalls,
        steps=[("Built-in check run by code after Agent 2: compare the registry Software keys and the data and "
                "program folders before the install with the state after the uninstall")],
        observe=["program_leftovers", "settings_leftovers"],
        expected=[Expectation(key="program_leftovers", check=Check.EQUALS, value=0, values=None)],
        priority=Priority.P2,
    )


def load000(tests: list[TestCase], host: HostProcess, card: FeatureCard | None = None) -> TestCase:
    """LOAD-000 "host ready with a new document" (LOAD_TESTS_PLAN.md L2, L11, L16). Same for every app
    on a host: its regexes come from the host notes. Depends on the INST test(s) observing install_exit_code.
    With `card` (a FUNC test needs a sample, FUNC_TESTS_PLAN.md Q14): the host opens the copy of that sample
    instead, and the LOAD and FUNC tests run in it. Its document's name isn't known in advance, so whether the
    right document is open is a judged claim."""
    installs = [t.id for t in tests if t.category is Category.INST and "install_exit_code" in t.observe]
    if card is not None:
        kind = card.context or "a document of the sample"
        return TestCase(
            id=BUILT_IN_LOAD_ID, origin=Origin.BUILT_IN, category=Category.LOAD,
            title=f"Host starts with the app installed and opens the sample '{card.sample}'", source=None,
            preconditions=installs,
            steps=["Start the host exactly as given in 'App under test' (host-interaction skill)",
                   "Answer a one-time load/trust prompt for the app under test; handle other dialogs by the skill",
                   (f"Open the copy of the sample '{card.sample}' given in your input through the host's UI, and in "
                    f"it a document of this kind: {kind}"),
                   "Take a Snapshot and a Screenshot of the host window, then record this test"],
            observe=["host_started", "document_opened", "error_dialog_seen", "load_prompt_seen"],
            expected=[Expectation(key="host_started", check=Check.WINDOW_IN_UI, value=host.main_window, values=None),
                      Expectation(key="document_opened", check=Check.JUDGED, values=None,
                                  value=f"The host shows a document of the sample '{card.sample}' open, of this "
                                        f"kind: {kind}"),
                      Expectation(key="error_dialog_seen", check=Check.NOT_EXISTS, value=None, values=None)],
            priority=Priority.P1,
        )
    return TestCase(
        id=BUILT_IN_LOAD_ID, origin=Origin.BUILT_IN, category=Category.LOAD,
        title="Host starts with the app installed and opens a new document", source=None, preconditions=installs,
        steps=["Start the host exactly as given in 'App under test' (host-interaction skill)",
               "Answer a one-time load/trust prompt for the app under test; stop at any other dialog",
               "Open the host's default new document (host notes)",
               "Take a Snapshot of the host window, then record this test"],
        observe=["host_started", "document_opened", "error_dialog_seen", "load_prompt_seen"],
        expected=[Expectation(key="host_started", check=Check.WINDOW_IN_UI, value=host.main_window, values=None),
                  Expectation(key="document_opened", check=Check.WINDOW_IN_UI, value=host.new_document, values=None),
                  Expectation(key="error_dialog_seen", check=Check.NOT_EXISTS, value=None, values=None)],
        priority=Priority.P1,
    )


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
