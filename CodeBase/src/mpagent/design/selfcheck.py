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
    FeatureCard,
    Origin,
    TestCase,
    TestPlan,
)

BUILT_IN_ENV_ID = "ENV-000"
BUILT_IN_LOAD_ID = "LOAD-000"  # added by code when the host notes have host_process (LOAD_TESTS_PLAN.md L2)
BUILT_IN_UNIN_ID = "UNIN-000"  # "nothing left behind", decided by code after Agent 2 (ARCHITECTURE.md D64)
BUILT_IN_IDS = {BUILT_IN_ENV_ID, BUILT_IN_LOAD_ID, BUILT_IN_UNIN_ID}
ID_PATTERN = re.compile(r"^(ENV|INST|LOAD|FUNC|UNIN)-\d{3}$")
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
USER_PROFILE_PATH = re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)
NEEDS_VALUE = {Check.EQUALS, Check.NOT_EQUALS, Check.CONTAINS, Check.MATCHES, Check.JUDGED}
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
               load_hosts: Iterable[str] = (), sample_names: Iterable[str] = ()) -> list[str]:
    """`load_hosts`: host_ids whose host notes have host_process (only those get LOAD and FUNC tests).
    `sample_names`: the samples feature cards may name (FUNC_TESTS_PLAN.md F18)."""
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
            errors.append(f"{t.id}: id must look like ENV-001, INST-001, LOAD-001, FUNC-001 or UNIN-001")
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
    _check_func(plan, load_host, set(sample_names), errors, check_citation)

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


# Names in a claim are written in quotes; an apostrophe inside a word (plug-in's) is not a quote
QUOTED_NAME = re.compile(r"[\"“”](.{2,80}?)[\"“”]|(?<![A-Za-z])['‘’](.{2,80}?)['‘’](?![A-Za-z])")
MAX_AGENT_LOAD_TESTS = 2  # LOAD-001: the entry point is present; LOAD-002: its documented items are reachable
# where each check decided from the evidence may be used (window_in_ui only in the built-in LOAD-000)
UI_CHECK_CATEGORIES = {Check.WINDOW_IN_UI: (Category.LOAD,), Check.JUDGED: (Category.LOAD, Category.FUNC),
                       Check.OUTPUT_CREATED: (Category.FUNC,)}
FUNC_CHECKS = {Check.JUDGED, Check.OUTPUT_CREATED}


def _check_load(plan: TestPlan, load_host: bool, errors: list[str], check_citation) -> None:
    """LOAD rules (LOAD_TESTS_PLAN.md §4.1, §9): LOAD-001 for a visible entry point, LOAD-002 when its items
    are documented; each has one `judged` claim whose quoted names come from its sources; UNIN never depends
    on LOAD."""
    ep = plan.summary.entry_point
    ep_quotes = ""
    if ep is not None:
        for i, c in enumerate(ep.sources):
            check_citation(f"summary.entry_point.sources[{i}]", c)
        ep_quotes = " ".join(normalise(c.quote) for c in ep.sources)
        for name in [ep.label, *ep.items]:
            if normalise(name) not in ep_quotes:
                errors.append(f"summary.entry_point: {name!r} is not in any quote of entry_point.sources; "
                              "copy names exactly from a source (or leave them out and add an open question)")
    load_ids = {t.id for t in plan.testcases if t.category is Category.LOAD} | {BUILT_IN_LOAD_ID}
    load_tests = [t for t in plan.testcases if t.category is Category.LOAD and t.id not in BUILT_IN_IDS]
    func_ids = {t.id for t in plan.testcases if t.category is Category.FUNC}
    for t in plan.testcases:
        for e in t.expected:
            if e.check in UI_CHECKS and t.category not in UI_CHECK_CATEGORIES[e.check]:
                allowed = " and ".join(c.value for c in UI_CHECK_CATEGORIES[e.check])
                errors.append(f"{t.id}: check '{e.check.value}' is only for {allowed} tests")
        if t.category is Category.UNIN and set(t.preconditions) & (load_ids | func_ids):
            errors.append(f"{t.id}: UNIN tests depend only on INST tests, never on LOAD or FUNC (the uninstall is "
                          "always tested)")
    visible = ep is not None and ep.kind in VISIBLE_ENTRY_POINTS
    if not load_tests:
        if load_host and visible:
            # run 20261013-172934: the card was filled but no LOAD test written
            errors.append(f"summary.entry_point is a visible {ep.kind.value}: write the LOAD test LOAD-001 "
                          "(one 'judged' claim, preconditions ['LOAD-000'])")
        return
    if not load_host:
        errors.append(f"{load_tests[0].id}: this host has no LOAD support (host notes without host_process); "
                      "write no LOAD tests")
        return
    if len(load_tests) > MAX_AGENT_LOAD_TESTS:
        errors.append("write at most two LOAD tests: LOAD-001 (the entry point is present) and LOAD-002 "
                      f"(its documented items are reachable); found {', '.join(t.id for t in load_tests)}")
    if not visible:
        kinds = ", ".join(sorted(k.value for k in VISIBLE_ENTRY_POINTS))
        errors.append(f"{load_tests[0].id}: a LOAD test needs summary.entry_point with kind {kinds}; otherwise write "
                      "no LOAD test and add an open question")
    elif ep.items and len(load_tests) < MAX_AGENT_LOAD_TESTS:
        errors.append("summary.entry_point.items are documented: also write LOAD-002, a 'judged' claim that "
                      "these items are reachable in the entry point (preconditions ['LOAD-000'] or "
                      "['LOAD-000', 'LOAD-001'])")
    for t in load_tests:
        if BUILT_IN_LOAD_ID not in t.preconditions or any(p not in load_ids for p in t.preconditions):
            errors.append(f"{t.id}: preconditions must be ['{BUILT_IN_LOAD_ID}'] (LOAD-002 may also depend on LOAD-001)")
        for e in t.expected:
            if e.check is Check.WINDOW_IN_UI:
                errors.append(f"{t.id}: 'window_in_ui' is reserved for the built-in {BUILT_IN_LOAD_ID}")
        judged = [e for e in t.expected if e.check is Check.JUDGED]
        if len(judged) != 1 or len(t.expected) != 1:
            errors.append(f"{t.id}: a LOAD test has exactly one expected check, 'judged', whose value is the "
                          "documented claim in plain words")
            continue
        support = " ".join(x for x in ((normalise(t.source.quote) if t.source else ""), ep_quotes) if x)
        for m in QUOTED_NAME.finditer(str(judged[0].value or "")):
            name = m.group(1) or m.group(2)
            if normalise(name) not in support:
                errors.append(f"{t.id}: the claim names {name!r}, which is in none of its quotes (the test's source "
                              "or summary.entry_point.sources); copy names exactly from a source")


def _check_func(plan: TestPlan, load_host: bool, sample_names: set[str], errors: list[str], check_citation) -> None:
    """FUNC rules (FUNC_TESTS_PLAN.md F1, F8, F13, F14, F16, §4.1): one feature card per documented feature; one
    FUNC test per testable card, with one `judged` claim per documented result; the tests in class order."""
    func_tests = [t for t in plan.testcases if t.category is Category.FUNC]
    func_ids = {t.id for t in func_tests}
    cards = plan.summary.features
    for i, card in enumerate(cards):
        where = f"summary.features[{i}] ({card.name!r})"
        for j, c in enumerate(card.results):
            check_citation(f"{where}.results[{j}]", c)
        for j, c in enumerate(card.sources):
            check_citation(f"{where}.sources[{j}]", c)
        if card.sample is not None and card.sample not in sample_names:
            known = ", ".join(sorted(sample_names)) or "none are available"
            errors.append(f"{where}: sample {card.sample!r} is not in the samples listing ({known}); use a listed "
                          "name or null")
        if card.testable:
            if card.action_class > 2:
                errors.append(f"{where}: a feature that needs class 3 (lasting) actions is not testable; set testable "
                              "false with the reason")
            if not card.results:
                errors.append(f"{where}: a testable feature needs its documented results (cited statements)")
            if card.test_id not in func_ids:
                errors.append(f"{where}: test_id must name the FUNC test that runs this feature (found "
                              f"{card.test_id!r})")
        else:
            if not card.reason:
                errors.append(f"{where}: not testable, so 'reason' must say which point fails and why")
            if card.test_id is not None:
                errors.append(f"{where}: not testable, so test_id must be null and no FUNC test is written")
    if func_tests and not load_host:
        errors.append(f"{func_tests[0].id}: this host has no FUNC support (host notes without host_process); "
                      "write no FUNC tests and add an open question")
        return
    card_of = {c.test_id: c for c in cards if c.testable and c.test_id}
    previous_group = 0
    for t in func_tests:
        card = card_of.get(t.id)
        if card is None:
            errors.append(f"{t.id}: no testable feature card in summary.features names this test in its test_id")
            continue
        if sum(c.test_id == t.id for c in cards) > 1:
            errors.append(f"{t.id}: named by more than one feature card; write one FUNC test per feature")
        if BUILT_IN_LOAD_ID not in t.preconditions or any(p != BUILT_IN_LOAD_ID and p not in func_ids
                                                          for p in t.preconditions):
            errors.append(f"{t.id}: preconditions must be ['{BUILT_IN_LOAD_ID}'], plus other FUNC tests only when a "
                          "cited statement says this feature needs their result")
        for e in t.expected:
            if e.check not in FUNC_CHECKS:
                errors.append(f"{t.id}: a FUNC test uses only 'judged' claims and 'output_created' (found "
                              f"'{e.check.value}')")
        judged = [e for e in t.expected if e.check is Check.JUDGED]
        if len(judged) != len(card.results):
            errors.append(f"{t.id}: write one 'judged' claim per documented result of its feature card "
                          f"({len(card.results)} results, {len(judged)} claims)")
        support = " ".join(normalise(c.quote) for c in [*([t.source] if t.source else []), *card.results,
                                                         *card.sources])
        for e in judged:
            for m in QUOTED_NAME.finditer(str(e.value or "")):
                name = m.group(1) or m.group(2)
                if normalise(name) not in support:
                    errors.append(f"{t.id}: the claim names {name!r}, which is in none of its quotes (the test's "
                                  "source or its feature card); copy names exactly from a source")
        group = 0 if card.action_class <= 1 else 1  # F13: class 0-1 first, then class 2; else the documents' order
        if group < previous_group:
            errors.append(f"{t.id}: FUNC tests run in class order (class 0-1 first, then class 2); move this "
                          "test before the tests that need class 2")
        previous_group = max(previous_group, group)


def sample_card(plan: TestPlan) -> FeatureCard | None:
    """The feature card whose sample the host session opens in LOAD-000 (FUNC_TESTS_PLAN.md Q14): the first FUNC
    test, in plan order, whose testable card names a sample; None if no FUNC test needs one."""
    cards = {c.test_id: c for c in plan.summary.features if c.testable and c.test_id and c.sample}
    return next((cards[t.id] for t in plan.testcases if t.category is Category.FUNC and t.id in cards), None)


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
