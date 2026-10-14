"""Self-check of Agent 1's test plan (ARCHITECTURE.md §4, D24). Pure code, no LLM.

check_plan() returns a list of plain-language errors; an empty list means the plan may be executed.
The errors are sent back to Agent 1 for a retry, so each one names the test and what to fix.
"""

import re
from collections.abc import Iterable

from mpagent.design.evidence import Source
from mpagent.models import (
    UI_CHECKS,
    VISIBLE_ENTRY_POINTS,
    Category,
    Check,
    Citation,
    Origin,
    TestCase,
    TestPlan,
)

BUILT_IN_ENV_ID = "ENV-000"
BUILT_IN_LOAD_ID = "LOAD-000"  # added by code when the host notes have host_process (FUNCTIONAL_TESTS_PLAN.md L2)
BUILT_IN_IDS = {BUILT_IN_ENV_ID, BUILT_IN_LOAD_ID}
ID_PATTERN = re.compile(r"^(ENV|INST|LOAD|UNIN)-\d{3}$")
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
USER_PROFILE_PATH = re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)
NEEDS_VALUE = {Check.EQUALS, Check.NOT_EQUALS, Check.CONTAINS, Check.MATCHES, Check.SEEN_IN_UI}
HOST_NONE, HOST_UNKNOWN = "none", "unknown"
# Keys about the app's own installation; an ENV test using them checks the wrong thing (run 20261013-145150)
APP_INSTALL_KEYS = {"install_exit_code", "uninstall_exit_code", "uninstall_entry_exists", "preinstalled_entry_exists"}


QUOTE_MARKS = re.compile(r"[\"'`“”‘’„‚«»]")  # all count as one mark (run 20261013-172934: “P&ID Exporter” -> 'P&ID Exporter')


def normalise(text: str) -> str:
    """Compare quotes loosely: case, runs of whitespace and the kind of quote marks don't matter, nor do
    quote marks/punctuation around the quote. The words themselves must match exactly."""
    text = QUOTE_MARKS.sub("'", re.sub(r"\s+", " ", text)).strip().casefold()
    return text.strip(" '.,;:")


def check_plan(plan: TestPlan, sources: list[Source], host_ids: Iterable[str],
               load_hosts: Iterable[str] = ()) -> list[str]:
    """`load_hosts`: host_ids whose host notes have host_process (only those get LOAD tests)."""
    errors: list[str] = []
    texts = {s.id: normalise(s.text) for s in sources}

    def check_citation(where: str, c: Citation) -> None:
        if c.doc not in texts:
            errors.append(f"{where}: cites '{c.doc}', which is not a source (use one of {', '.join(texts)})")
        elif not normalise(c.quote) or normalise(c.quote) not in texts[c.doc]:
            # run 20261013-172934: an exact quote cited with the wrong doc id was resent unchanged twice
            elsewhere = [d for d, t in texts.items() if normalise(c.quote) and normalise(c.quote) in t]
            hint = (f"; this text is in {', '.join(elsewhere)}, not {c.doc}: set doc to {elsewhere[0]}" if elsewhere
                    else " (copy the text exactly)")
            errors.append(f"{where}: quote not found in {c.doc}: {c.quote!r}{hint}")

    # host decision
    host_ids = set(host_ids)
    host = plan.app.host_id
    if host not in host_ids | {HOST_NONE, HOST_UNKNOWN}:
        errors.append(f"app.host_id '{host}' is not in the catalogue; use one of {sorted(host_ids)}, 'none' or 'unknown'")
    if host in host_ids and not plan.app.host_evidence:
        errors.append(f"app.host_evidence is empty; cite why the host is '{host}'")
    if host == HOST_UNKNOWN and not plan.summary.open_questions:
        errors.append("app.host_id is 'unknown' but summary.open_questions doesn't say why")
    for i, c in enumerate(plan.app.host_evidence):
        check_citation(f"app.host_evidence[{i}]", c)

    # ids, origin, sources, categories
    ids = [t.id for t in plan.testcases]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"test id {dup} is used more than once")
    for t in plan.testcases:
        if t.id in BUILT_IN_IDS:
            errors.append(f"{t.id} is reserved for a built-in test added by code; don't write it")
            continue
        if not ID_PATTERN.match(t.id):
            errors.append(f"{t.id}: id must look like ENV-001, INST-001, LOAD-001 or UNIN-001")
        elif t.id.split("-")[0] != t.category.value:
            errors.append(f"{t.id}: id prefix doesn't match category {t.category.value}")
        if t.origin is not Origin.AGENT:
            errors.append(f"{t.id}: origin must be 'agent'")
        if t.source is None:
            errors.append(f"{t.id}: source citation is missing")
        else:
            check_citation(f"{t.id}.source", t.source)
        _check_expectations(t, errors)
        if t.category is Category.ENV:
            for key in sorted(set(t.observe) & APP_INSTALL_KEYS):
                errors.append(f"{t.id}: ENV tests check the machine/host, not the app's installation; "
                              f"'{key}' belongs in INST/UNIN tests (use e.g. host_installed, host_version)")
        for text in texts_of(t):
            if USER_PROFILE_PATH.search(text):
                errors.append(f"{t.id}: hard-coded user profile path {text!r}; use a placeholder or %AppData%")

    load_host = host in set(load_hosts)
    _check_load(plan, load_host, errors, check_citation)

    # preconditions: known ids, no cycles
    known = set(ids) | {BUILT_IN_ENV_ID} | ({BUILT_IN_LOAD_ID} if load_host else set())
    for t in plan.testcases:
        for p in t.preconditions:
            if p not in known:
                errors.append(f"{t.id}: precondition {p} is not a test in this plan")
    cycle = _find_cycle({t.id: [p for p in t.preconditions if p in known] for t in plan.testcases})
    if cycle:
        errors.append(f"preconditions form a cycle: {' -> '.join(cycle)}")

    # placeholders
    used = {name for t in plan.testcases for text in texts_of(t) for name in PLACEHOLDER.findall(text)}
    for name in sorted(used - set(plan.required_env)):
        errors.append(f"placeholder ${{{name}}} is used but not listed in required_env")

    # basic coverage (D24)
    if not _has(plan, Category.INST, "install_exit_code", {Check.IN, Check.EQUALS}):
        errors.append("missing required INST test observing 'install_exit_code' (expected: in ['0', '3010'])")
    if not _has(plan, Category.INST, "uninstall_entry_exists", {Check.EXISTS}):
        errors.append("missing required INST test observing 'uninstall_entry_exists' (expected: exists)")
    if not _has(plan, Category.UNIN, "uninstall_entry_exists", {Check.NOT_EXISTS}):
        errors.append("missing required UNIN test observing 'uninstall_entry_exists' (expected: not_exists)")
    return errors


def _check_load(plan: TestPlan, load_host: bool, errors: list[str], check_citation) -> None:
    """LOAD rules (FUNCTIONAL_TESTS_PLAN.md §4.1): at most one agent LOAD test, for a visible entry point,
    looking for exactly the quoted label, depending only on LOAD-000; UNIN never depends on LOAD."""
    ep = plan.summary.entry_point
    if ep is not None:
        for i, c in enumerate(ep.sources):
            check_citation(f"summary.entry_point.sources[{i}]", c)
        quoted = " ".join(normalise(c.quote) for c in ep.sources)
        for name in [ep.label, *ep.items]:
            if normalise(name) not in quoted:
                errors.append(f"summary.entry_point: {name!r} is not in any quote of entry_point.sources; "
                              "copy names exactly from a source (or leave them out and add an open question)")
    load_ids = {t.id for t in plan.testcases if t.category is Category.LOAD} | {BUILT_IN_LOAD_ID}
    load_tests = [t for t in plan.testcases if t.category is Category.LOAD and t.id not in BUILT_IN_IDS]
    for t in plan.testcases:
        if t.category is not Category.LOAD:
            for e in t.expected:
                if e.check in UI_CHECKS:
                    errors.append(f"{t.id}: check '{e.check.value}' is only for LOAD tests")
        if t.category is Category.UNIN and set(t.preconditions) & load_ids:
            errors.append(f"{t.id}: UNIN tests depend only on INST tests, never on LOAD (the uninstall is always tested)")
    if not load_tests:
        if load_host and ep is not None and ep.kind in VISIBLE_ENTRY_POINTS:
            # run 20261013-172934: the card was filled but no LOAD test written
            errors.append(f"summary.entry_point is a visible {ep.kind.value}: write the LOAD test LOAD-001 "
                          "(seen_in_ui with the label, preconditions ['LOAD-000'])")
        return
    if not load_host:
        errors.append(f"{load_tests[0].id}: this host has no LOAD support (host notes without host_process); "
                      "write no LOAD tests")
        return
    if len(load_tests) > 1:
        errors.append(f"write at most one LOAD test (the entry point check); found {', '.join(t.id for t in load_tests)}")
    visible = ", ".join(sorted(k.value for k in VISIBLE_ENTRY_POINTS))
    for t in load_tests:
        if ep is None or ep.kind not in VISIBLE_ENTRY_POINTS:
            errors.append(f"{t.id}: a LOAD test needs summary.entry_point with kind {visible}; otherwise write "
                          "no LOAD test and add an open question")
        if t.preconditions != [BUILT_IN_LOAD_ID]:
            errors.append(f"{t.id}: preconditions must be exactly ['{BUILT_IN_LOAD_ID}']")
        ui = [e for e in t.expected if e.check is Check.SEEN_IN_UI]
        if len(ui) != 1 or len(t.expected) != 1:
            errors.append(f"{t.id}: a LOAD test has exactly one expected check, 'seen_in_ui' with the entry point label")
        elif ep is not None and normalise(str(ui[0].value)) != normalise(ep.label):
            errors.append(f"{t.id}: seen_in_ui value {ui[0].value!r} must equal summary.entry_point.label {ep.label!r}")
        for e in t.expected:
            if e.check is Check.WINDOW_IN_UI:
                errors.append(f"{t.id}: 'window_in_ui' is reserved for the built-in {BUILT_IN_LOAD_ID}")


def _check_expectations(t: TestCase, errors: list[str]) -> None:
    if not t.expected:
        errors.append(f"{t.id}: no expected checks")
    for e in t.expected:
        if e.key not in t.observe:
            errors.append(f"{t.id}: expected key '{e.key}' is not in observe {t.observe}")
        if e.check is Check.IN and not e.values:
            errors.append(f"{t.id}: check 'in' on '{e.key}' needs a non-empty 'values' list")
        if e.check in NEEDS_VALUE and e.value is None:
            errors.append(f"{t.id}: check '{e.check.value}' on '{e.key}' needs a 'value'")
        if e.check is Check.MATCHES and isinstance(e.value, str):
            try:
                re.compile(e.value)
            except re.error as exc:
                errors.append(f"{t.id}: 'matches' pattern for '{e.key}' is not a valid regular expression ({exc})")


def texts_of(t: TestCase) -> list[str]:
    """Strings Agent 2 will act on or code will compare: steps and expected values."""
    out = list(t.steps)
    for e in t.expected:
        if isinstance(e.value, str):
            out.append(e.value)
        out += e.values or []
    return out


def _has(plan: TestPlan, category: Category, key: str, checks: set[Check]) -> bool:
    return any(
        t.category is category and key in t.observe and any(e.key == key and e.check in checks for e in t.expected)
        for t in plan.testcases
    )


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(node: str, path: list[str]) -> list[str] | None:
        if state.get(node) == 1:
            return path[path.index(node):] + [node]
        if state.get(node) == 2:
            return None
        state[node] = 1
        for nxt in graph.get(node, []):
            found = visit(nxt, path + [node])
            if found:
                return found
        state[node] = 2
        return None

    for n in graph:
        found = visit(n, [])
        if found:
            return found
    return None
