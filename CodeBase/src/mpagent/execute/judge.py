"""The LLM judge for UI claims (LOAD_TESTS_PLAN.md L20-L26, ARCHITECTURE.md D58-D61).

A separate model call with a fresh context decides whether a documented UI claim holds. It sees only the claim,
its quotes, the app's own UI text (U1), the test's screenshots, the host-window part of its Snapshot texts and
Agent 2's notes (as the executor's description, not proof). Agent 2 never grades its own work. The guards around
the answer (an attached screenshot must be named, errors become ERROR) are in the verdict engine.
"""

import asyncio
import base64
import json
from pathlib import Path

from agents import Agent, Runner

from mpagent.config import PROJECT_ROOT, Settings
from mpagent.execute import ui_tree
from mpagent.models import (
    Expectation,
    InstallerFacts,
    Judgement,
    Observation,
    TestCase,
    TestPlan,
)
from mpagent.runlog import Trace, log

SKILL = PROJECT_ROOT / "skills" / "execute" / "judge.md"
MAX_IMAGES = 6  # default cap per claim; JUDGE_MAX_IMAGES in .env (FUNC_TESTS_PLAN.md F17)
MAX_UI_TEXT_CHARS = 15_000
MAX_TREE_CHARS = 8_000
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def app_ui_text(run_dir: Path) -> str:
    """U1 from the installer read, or '' if the installer had no readable UI text."""
    path = run_dir / "installer_facts.json"
    if not path.exists():
        return ""
    facts = InstallerFacts.model_validate_json(path.read_text(encoding="utf-8"))
    if not facts.ui_text:
        return ""
    return (run_dir / facts.ui_text.text_file).read_text(encoding="utf-8")[:MAX_UI_TEXT_CHARS]


def host_tree_text(run_dir: Path, obs: Observation, main_window: str | None) -> str:
    """The host window's part of the attached Snapshot texts, one `type "name"` line per element."""
    lines: list[str] = []
    for rel in obs.evidence:
        if not rel.endswith("_Snapshot_ui.txt") or not (run_dir / rel).is_file():
            continue
        text = (run_dir / rel).read_text(encoding="utf-8", errors="replace")
        windows = ui_tree.host_windows(text, main_window) if main_window else []
        nodes = [n for w in windows for n in w] or ui_tree.nodes(text)
        lines.append(f"-- {rel}")
        lines += [f'{n.type} "{n.name}"' for n in nodes]
    return "\n".join(lines)[:MAX_TREE_CHARS]


def choose_screenshots(obs: Observation, max_images: int = MAX_IMAGES) -> list[str]:
    """The screenshots Agent 2 named itself first, then the latest ones, up to max_images; shown in the
    order taken (FUNC_TESTS_PLAN.md F17)."""
    images = [r for r in obs.evidence if Path(r).suffix.lower() in IMAGE_TYPES]
    picked = [r for r in images if r in obs.picked][:max_images]
    rest = [r for r in images if r not in picked]
    room = max_images - len(picked)
    chosen = set(picked + (rest[-room:] if room > 0 else []))
    return sorted(chosen, key=_taken_order)


def _taken_order(rel: str) -> tuple[int, str]:
    """Saved files start with the call number (e.g. evidence/012_Screenshot_1.png)."""
    number = Path(rel).name.split("_", 1)[0]
    return (int(number) if number.isdigit() else -1, rel)


def build_request(plan: TestPlan, t: TestCase, e: Expectation, obs: Observation, run_dir: Path,
                  main_window: str | None, max_images: int = MAX_IMAGES) -> tuple[str, list[str]]:
    """The text part of the judge's input and the screenshots to show it (paths relative to the run folder)."""
    quotes = [t.source] if t.source else []
    if plan.summary.entry_point:
        quotes += plan.summary.entry_point.sources
    shots = choose_screenshots(obs, max_images)
    observed = ", ".join(f"{kv.key}={kv.value!r}" for kv in obs.observed) or "-"
    parts = [
        f"Test {t.id}: {t.title}",
        f"CLAIM TO JUDGE: {e.value}",
        "Quotes the claim comes from:\n" + ("\n".join(f'- {q.doc}: "{q.quote}"' for q in quotes) or "- (none)"),
        f"App under test: {plan.app.name} (host: {plan.app.host_id})",
        ("<app_ui_text source=\"U1: readable text found in the app's own binaries; hints, may include text of "
         f"related products\">\n{app_ui_text(run_dir) or '(none found)'}\n</app_ui_text>"),
        ("<executor_notes source=\"Agent 2's own description, not proof\">\n"
         f"observed: {observed}\nnotes: {obs.notes or '-'}\n</executor_notes>"),
        ("<ui_tree source=\"host window part of the test's Snapshots\">\n"
         f"{host_tree_text(run_dir, obs, main_window) or '(none)'}\n</ui_tree>"),
        "Screenshots, in the order taken (cite them by these names):\n" + ("\n".join(f"- {s}" for s in shots) or "- (none)"),
    ]
    return "\n\n".join(parts), shots


def make_judge(plan: TestPlan, run_dir: Path, settings: Settings, main_window: str | None):
    """A JudgeFn for the verdict engine: one fresh model call per judged claim, traced to trace.jsonl.
    Each call gets its own event loop and its own OpenAI client, because Agent 2 ran before in an
    asyncio.run() loop that is closed by now (run 20261014-153924)."""
    instructions = SKILL.read_text(encoding="utf-8")
    trace = Trace(run_dir)

    async def ask(content: list[dict]) -> Judgement:
        agent = Agent(name="ui-claim-judge", instructions=instructions, output_type=Judgement,
                      model=settings.fresh_model())
        result = await Runner.run(agent, [{"role": "user", "content": content}], max_turns=2)
        return result.final_output

    def judge(t: TestCase, e: Expectation, obs: Observation) -> Judgement:
        text, shots = build_request(plan, t, e, obs, run_dir, main_window, settings.judge_max_images)
        content: list[dict] = [{"type": "input_text", "text": text}]
        for rel in shots:
            data = base64.b64encode((run_dir / rel).read_bytes()).decode()
            content.append({"type": "input_text", "text": f"Screenshot {rel}:"})
            content.append({"type": "input_image", "image_url": f"data:{IMAGE_TYPES[Path(rel).suffix.lower()]};base64,{data}",
                            "detail": "high"})
        trace.write("judge_request", test_id=t.id, input=text, images=shots)
        judgement = asyncio.run(ask(content))
        trace.write("judge_response", test_id=t.id, judgement=json.loads(judgement.model_dump_json()))
        log.info("  judge %s: %s — %s", t.id, judgement.verdict.value, judgement.shown[:160])
        return judgement

    return judge
