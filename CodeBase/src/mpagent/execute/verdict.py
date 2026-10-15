"""Verdict engine (ARCHITECTURE.md §5, D7, D25): code turns raw observations into PASS/FAIL/BLOCKED/ERROR.

Precedence for each test:
  BLOCKED       a precondition is not PASS, or a placeholder the test needs was not resolved by Agent 2
  ERROR         no observation, the test was not executed, an expected key is missing / null, or a UI check
                has no Snapshot / no host window to look in
  FAIL          any expected check fails
  NEEDS_REVIEW  the judge couldn't decide a UI claim from the evidence
  PASS          every expected check holds
Values are compared as text after light normalising, so 0 == "0" and True == "true".
`window_in_ui` (LOAD_TESTS_PLAN.md L11, L17) is decided from the raw Snapshot UI-tree files attached to
the observation. `judged` UI claims (L20-L25) are decided by the LLM judge from the attached screenshots, inside
guards kept by code. Agent 2's own value is kept only for the report.
"""

import re
from collections.abc import Callable
from pathlib import Path

from mpagent.design.selfcheck import PLACEHOLDER, texts_of
from mpagent.execute import ui_tree
from mpagent.models import (
    UI_CHECKS,
    Check,
    CheckResult,
    Expectation,
    Judgement,
    JudgeVerdict,
    Observation,
    Scalar,
    Status,
    TestCase,
    TestPlan,
    TestResult,
)

ALWAYS_KNOWN = {"INSTALLER_PATH", "RUN_DIR"}  # given to Agent 2 by code
UI_TEXT_SUFFIX = "_Snapshot_ui.txt"  # raw Snapshot text saved by the call recorder
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")

# (test, its judged expectation, its observation) -> the judge's answer; raises if the call fails
JudgeFn = Callable[[TestCase, Expectation, Observation], Judgement]


def norm(value: Scalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip().casefold()


def check_one(e: Expectation, observed: Scalar) -> bool:
    o = norm(observed)
    if e.check is Check.EQUALS:
        return o == norm(e.value)
    if e.check is Check.NOT_EQUALS:
        return o != norm(e.value)
    if e.check is Check.IN:
        return o in {norm(v) for v in e.values or []}
    if e.check is Check.EXISTS:
        return o == "true"
    if e.check is Check.NOT_EXISTS:
        return o == "false"
    if e.check is Check.CONTAINS:
        return norm(e.value) in o
    if e.check is Check.MATCHES:
        return re.search(str(e.value), str(observed), re.IGNORECASE) is not None
    raise ValueError(f"unknown check {e.check}")


class UiContext:
    """Where UI checks look: the run folder (for the attached evidence files), the host's main-window regex,
    and the judge for `judged` claims (None: no judge available, e.g. in unit tests)."""

    def __init__(self, run_dir: Path | None, main_window: str | None, judge: JudgeFn | None = None):
        self.run_dir, self.main_window, self.judge = run_dir, main_window, judge

    def texts(self, obs: Observation) -> list[str]:
        if self.run_dir is None:
            return []
        out = []
        for rel in obs.evidence:
            path = self.run_dir / rel
            if rel.endswith(UI_TEXT_SUFFIX) and path.is_file():
                out.append(path.read_text(encoding="utf-8", errors="replace"))
        return out


def evaluate(plan: TestPlan, observations: list[Observation], resolved_env: set[str] | None,
             ui: UiContext | None = None) -> list[TestResult]:
    """One TestResult per test, in plan order. `resolved_env` is None when Agent 2 returned no env
    (e.g. it was cut off); then unresolved placeholders don't block, missing observations give ERROR."""
    ui = ui or UiContext(None, None)
    by_id = {o.test_id: o for o in observations}
    tests = {t.id: t for t in plan.testcases}
    results: dict[str, TestResult] = {}

    def result_of(tid: str, visiting: frozenset[str] = frozenset()) -> TestResult:
        if tid not in results:
            if tid in visiting:  # cycles are rejected by the self-check; guard anyway
                raise ValueError(f"precondition cycle at {tid}")
            results[tid] = _evaluate_test(tests[tid], by_id.get(tid), resolved_env, ui,
                                          {p: result_of(p, visiting | {tid}) for p in tests[tid].preconditions
                                           if p in tests})
        return results[tid]

    return [result_of(t.id) for t in plan.testcases]


def _evaluate_test(t: TestCase, obs: Observation | None, resolved_env: set[str] | None, ui: UiContext,
                   preconditions: dict[str, TestResult]) -> TestResult:
    evidence = list(obs.evidence) if obs else []
    notes = obs.notes if obs else None

    judgement: Judgement | None = None

    def result(status: Status, checks: list[CheckResult], reason: str | None) -> TestResult:
        joined = "; ".join(x for x in (reason, notes) if x) or None
        return TestResult(test_id=t.id, origin=t.origin, status=status, checks=checks, evidence=evidence, notes=joined,
                          judgement=judgement,
                          findings=list(judgement.findings) if judgement else list(obs.findings) if obs else [])

    not_passed = [f"{p} is {r.status.value}" for p, r in preconditions.items() if r.status is not Status.PASS]
    if not_passed:
        return result(Status.BLOCKED, [], "precondition " + ", ".join(not_passed))
    if resolved_env is not None:
        needed = {n for s in texts_of(t) for n in PLACEHOLDER.findall(s)} - ALWAYS_KNOWN - resolved_env
        if needed:
            return result(Status.BLOCKED, [], "placeholder not resolved: " + ", ".join(sorted(needed)))
    if obs is None:
        return result(Status.ERROR, [], "no observation recorded")
    if not obs.executed:
        return result(Status.ERROR, [], "not executed by Agent 2")

    values = {kv.key: kv.value for kv in obs.observed}
    checks: list[CheckResult] = []
    missing: list[str] = []
    ui_errors: list[str] = []
    for e in t.expected:
        expected = e.values if e.check is Check.IN else e.value
        if e.check is Check.JUDGED:
            check, problem, judgement = _judged_check(t, e, obs, ui, values.get(e.key))
            checks.append(check)
            if problem:
                ui_errors.append(problem)
            continue
        if e.check in UI_CHECKS:
            check, problem = _ui_check(e, obs, ui, values.get(e.key))
            checks.append(check)
            if problem:
                ui_errors.append(problem)
            continue
        if values.get(e.key) is None:
            missing.append(e.key)
            checks.append(CheckResult(key=e.key, check=e.check, expected=expected, observed=None, ok=False))
            continue
        checks.append(CheckResult(key=e.key, check=e.check, expected=expected, observed=values[e.key],
                                  ok=check_one(e, values[e.key])))
    if missing or ui_errors:
        reasons = (["no value observed for " + ", ".join(missing)] if missing else []) + ui_errors
        return result(Status.ERROR, checks, "; ".join(reasons))
    if any(not c.ok and not c.needs_review for c in checks):
        return result(Status.FAIL, checks, None)
    judged_reason = f"judge: {judgement.reason}" if judgement else None
    if any(not c.ok and not c.needs_review for c in checks):
        return result(Status.FAIL, checks, judged_reason)
    if any(c.needs_review for c in checks):
        return result(Status.NEEDS_REVIEW, checks, judged_reason or "check the screenshot")
    return result(Status.PASS, checks, judged_reason)


def _judged_check(t: TestCase, e: Expectation, obs: Observation, ui: UiContext,
                  reported: Scalar) -> tuple[CheckResult, str | None, Judgement | None]:
    """A UI claim decided by the judge, inside code guards (LOAD_TESTS_PLAN.md L25): never without
    screenshots, never on a screenshot that isn't attached to this test, a failed call is an ERROR."""

    def make(observed: Scalar, ok: bool = False, review: bool = False) -> CheckResult:
        return CheckResult(key=e.key, check=e.check, expected=e.value, observed=observed, ok=ok,
                           needs_review=review, reported=reported)

    shots = [r for r in obs.evidence if r.lower().endswith(IMAGE_SUFFIXES)]
    if not shots:
        return make(None), f"{e.key}: no screenshot attached; a UI claim is never judged from notes alone", None
    if ui.judge is None:
        return make(None), f"{e.key}: no judge available to decide the UI claim", None
    try:
        judgement = ui.judge(t, e, obs)
    except Exception as ex:  # noqa: BLE001 - a judge problem is this test's ERROR, never a crashed run
        return make(None), f"{e.key}: the judge call failed ({type(ex).__name__}: {ex})", None
    names = {s: s for s in shots} | {Path(s).name: s for s in shots}
    cited = [names[x.replace("\\", "/")] for x in judgement.evidence if x.replace("\\", "/") in names]
    if not cited:
        problem = (f"{e.key}: the judge named no screenshot attached to this test "
                   f"({', '.join(judgement.evidence) or 'none'})")
        return make(judgement.shown), problem, judgement
    judgement = judgement.model_copy(update={"evidence": cited})
    check = make(judgement.shown, ok=judgement.verdict is JudgeVerdict.PASS,
                 review=judgement.verdict is JudgeVerdict.NEEDS_REVIEW)
    return check, None, judgement


def _ui_check(e: Expectation, obs: Observation, ui: UiContext, reported: Scalar) -> tuple[CheckResult, str | None]:
    """`window_in_ui`, decided from the attached raw Snapshot texts. Returns the check and an ERROR reason, if any."""
    texts = ui.texts(obs)

    def make(observed: Scalar, ok: bool) -> CheckResult:
        return CheckResult(key=e.key, check=e.check, expected=e.value, observed=observed, ok=ok, reported=reported)

    if not ui.main_window:
        return make(None, False), f"{e.key}: the host notes have no main_window pattern"
    if not texts:
        return make(None, False), f"{e.key}: no Snapshot was attached to this observation"
    ok = ui_tree.window_in_ui(texts, ui.main_window, str(e.value))
    return make("seen" if ok else "not seen", ok), None
