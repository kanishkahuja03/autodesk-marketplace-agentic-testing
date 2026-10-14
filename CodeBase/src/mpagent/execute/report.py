"""Report (ARCHITECTURE.md §5, D19): results.json and report.html, written only if Agent 2 ran."""

from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mpagent.execute.agent2 import RESULT_FILE
from mpagent.execute.host import CRASH_EVENTS_FILE
from mpagent.execute.observations import load_observations
from mpagent.execute.verdict import UiContext, evaluate
from mpagent.hostnotes import host_process
from mpagent.models import Agent2Result, RunResults, Status, TestPlan

TEMPLATES = Path(__file__).parent / "templates"
RESULTS_FILE = "results.json"
REPORT_FILE = "report.html"


def build_results(plan: TestPlan, run_dir: Path) -> RunResults:
    """Verdicts for every test from observations.json (+ agent2_result.json if Agent 2 finished)."""
    result_path = run_dir / RESULT_FILE
    finished = result_path.exists()
    resolved = None
    if finished:
        agent2 = Agent2Result.model_validate_json(result_path.read_text(encoding="utf-8"))
        resolved = {kv.key for kv in agent2.env if kv.value not in (None, "")}
    host = host_process(plan.app.host_id)
    ui = UiContext(run_dir, host.main_window if host else None)
    results = evaluate(plan, load_observations(run_dir), resolved, ui)
    counts = Counter(r.status.value for r in results)
    return RunResults(app=plan.app.name, run_folder=str(run_dir), agent2_finished=finished,
                      counts={s.value: counts.get(s.value, 0) for s in Status}, results=results)


def write_report(plan: TestPlan, run_dir: Path) -> RunResults:
    run = build_results(plan, run_dir)
    (run_dir / RESULTS_FILE).write_text(run.model_dump_json(indent=2), encoding="utf-8")
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    tests = {t.id: t for t in plan.testcases}
    crash_file = run_dir / CRASH_EVENTS_FILE
    crashes = crash_file.read_text(encoding="utf-8") if crash_file.exists() else None
    html = env.get_template("report.html.j2").render(plan=plan, run=run, tests=tests, crashes=crashes,
                                                     crash_file=CRASH_EVENTS_FILE)
    (run_dir / REPORT_FILE).write_text(html, encoding="utf-8")
    return run


def summary_line(run: RunResults) -> str:
    return ", ".join(f"{n} {s}" for s, n in run.counts.items())
