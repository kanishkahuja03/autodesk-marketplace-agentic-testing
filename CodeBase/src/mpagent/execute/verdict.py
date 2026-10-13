"""Verdict engine (ARCHITECTURE.md §5, D7, D25): code turns raw observations into PASS/FAIL/BLOCKED/ERROR.

Precedence for each test:
  BLOCKED  a precondition is not PASS, or a placeholder the test needs was not resolved by Agent 2
  ERROR    no observation, the test was not executed, or an expected key is missing / null
  FAIL     any expected check fails
  PASS     every expected check holds
Values are compared as text after light normalising, so 0 == "0" and True == "true".
"""

import re

from mpagent.design.selfcheck import PLACEHOLDER, texts_of
from mpagent.models import (
    Check,
    CheckResult,
    Expectation,
    Observation,
    Scalar,
    Status,
    TestCase,
    TestPlan,
    TestResult,
)

ALWAYS_KNOWN = {"INSTALLER_PATH", "RUN_DIR"}  # given to Agent 2 by code


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


def evaluate(plan: TestPlan, observations: list[Observation], resolved_env: set[str] | None) -> list[TestResult]:
    """One TestResult per test, in plan order. `resolved_env` is None when Agent 2 returned no env
    (e.g. it was cut off); then unresolved placeholders don't block, missing observations give ERROR."""
    by_id = {o.test_id: o for o in observations}
    tests = {t.id: t for t in plan.testcases}
    results: dict[str, TestResult] = {}

    def result_of(tid: str, visiting: frozenset[str] = frozenset()) -> TestResult:
        if tid not in results:
            if tid in visiting:  # cycles are rejected by the self-check; guard anyway
                raise ValueError(f"precondition cycle at {tid}")
            results[tid] = _evaluate_test(tests[tid], by_id.get(tid), resolved_env,
                                          {p: result_of(p, visiting | {tid}) for p in tests[tid].preconditions
                                           if p in tests})
        return results[tid]

    return [result_of(t.id) for t in plan.testcases]


def _evaluate_test(t: TestCase, obs: Observation | None, resolved_env: set[str] | None,
                   preconditions: dict[str, TestResult]) -> TestResult:
    evidence = list(obs.evidence) if obs else []
    notes = obs.notes if obs else None

    def result(status: Status, checks: list[CheckResult], reason: str | None) -> TestResult:
        joined = "; ".join(x for x in (reason, notes) if x) or None
        return TestResult(test_id=t.id, origin=t.origin, status=status, checks=checks, evidence=evidence, notes=joined)

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
    for e in t.expected:
        expected = e.values if e.check is Check.IN else e.value
        if values.get(e.key) is None:
            missing.append(e.key)
            checks.append(CheckResult(key=e.key, check=e.check, expected=expected, observed=None, ok=False))
            continue
        checks.append(CheckResult(key=e.key, check=e.check, expected=expected, observed=values[e.key],
                                  ok=check_one(e, values[e.key])))
    if missing:
        return result(Status.ERROR, checks, "no value observed for " + ", ".join(missing))
    return result(Status.PASS if all(c.ok for c in checks) else Status.FAIL, checks, None)
