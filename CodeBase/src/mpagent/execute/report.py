"""Report (ARCHITECTURE.md §5, D19): results.json and report.html, written only if Agent 2 ran."""

from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mpagent.config import Settings
from mpagent.execute.agent2 import RESULT_FILE
from mpagent.execute.host import CRASH_EVENTS_FILE
from mpagent.execute.observations import load_observations
from mpagent.execute.verdict import JudgeFn, UiContext, evaluate
from mpagent.hostnotes import host_process
from mpagent.models import Agent2Result, Check, RunResults, Status, TestPlan

TEMPLATES = Path(__file__).parent / "templates"
RESULTS_FILE = "results.json"
REPORT_FILE = "report.html"


def build_results(plan: TestPlan, run_dir: Path, judge: JudgeFn | None = None) -> RunResults:
    """Verdicts for every test from observations.json (+ agent2_result.json if Agent 2 finished).
    `judge` decides `judged` UI claims; without one they are ERROR."""
    result_path = run_dir / RESULT_FILE
    finished = result_path.exists()
    resolved = None
    if finished:
        agent2 = Agent2Result.model_validate_json(result_path.read_text(encoding="utf-8"))
        resolved = {kv.key for kv in agent2.env if kv.value not in (None, "")}
    host = host_process(plan.app.host_id)
    ui = UiContext(run_dir, host.main_window if host else None, judge)
    results = evaluate(plan, load_observations(run_dir), resolved, ui)
    counts = Counter(r.status.value for r in results)
    return RunResults(app=plan.app.name, run_folder=str(run_dir), agent2_finished=finished,
                      counts={s.value: counts.get(s.value, 0) for s in Status}, results=results)


def make_run_judge(plan: TestPlan, run_dir: Path, settings: Settings | None) -> JudgeFn | None:
    """The LLM judge (same OPENAI_MODEL, D58), only if the plan has judged claims and settings are given."""
    if settings is None or not any(e.check is Check.JUDGED for t in plan.testcases for e in t.expected):
        return None
    from mpagent.execute.judge import (
        make_judge,  # the Agents SDK model is built only when needed
    )

    host = host_process(plan.app.host_id)
    return make_judge(plan, run_dir, settings, host.main_window if host else None)


def write_report(plan: TestPlan, run_dir: Path, settings: Settings | None = None,
                 judge: JudgeFn | None = None) -> RunResults:
    run = build_results(plan, run_dir, judge or make_run_judge(plan, run_dir, settings))
    (run_dir / RESULTS_FILE).write_text(run.model_dump_json(indent=2), encoding="utf-8")
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    tests = {t.id: t for t in plan.testcases}
    crash_file = run_dir / CRASH_EVENTS_FILE
    crashes = crash_file.read_text(encoding="utf-8") if crash_file.exists() else None
    findings = [(r.test_id, f) for r in run.results for f in r.findings]
    html = env.get_template("report.html.j2").render(plan=plan, run=run, tests=tests, crashes=crashes,
                                                     crash_file=CRASH_EVENTS_FILE, findings=findings)
    (run_dir / REPORT_FILE).write_text(html, encoding="utf-8")
    return run


def summary_line(run: RunResults) -> str:
    return ", ".join(f"{n} {s}" for s, n in run.counts.items())
