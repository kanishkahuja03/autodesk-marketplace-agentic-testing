"""Self-check of Agent 1's test plan (ARCHITECTURE.md §4, D24). Pure code, no LLM.

check_plan() returns a list of plain-language errors; an empty list means the plan may be executed.
The errors are sent back to Agent 1 for a retry, so each one names the test and what to fix.
"""

import re
from collections.abc import Iterable

from mpagent.design.evidence import Source
from mpagent.models import Category, Check, Citation, Origin, TestCase, TestPlan

BUILT_IN_ENV_ID = "ENV-000"
ID_PATTERN = re.compile(r"^(ENV|INST|UNIN)-\d{3}$")
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
USER_PROFILE_PATH = re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)
NEEDS_VALUE = {Check.EQUALS, Check.NOT_EQUALS, Check.CONTAINS, Check.MATCHES}
HOST_NONE, HOST_UNKNOWN = "none", "unknown"


def normalise(text: str) -> str:
    """Compare quotes loosely: case, runs of whitespace and surrounding quote marks/punctuation don't matter."""
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text.strip(" \"'`“”‘’.,;:")


def check_plan(plan: TestPlan, sources: list[Source], host_ids: Iterable[str]) -> list[str]:
    errors: list[str] = []
    texts = {s.id: normalise(s.text) for s in sources}

    def check_citation(where: str, c: Citation) -> None:
        if c.doc not in texts:
            errors.append(f"{where}: cites '{c.doc}', which is not a source (use one of {', '.join(texts)})")
        elif not normalise(c.quote) or normalise(c.quote) not in texts[c.doc]:
            errors.append(f"{where}: quote not found in {c.doc}: {c.quote!r} (copy the text exactly)")

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
        if t.id == BUILT_IN_ENV_ID:
            errors.append(f"{t.id} is reserved for the built-in 'not already installed' test; don't write it")
            continue
        if not ID_PATTERN.match(t.id):
            errors.append(f"{t.id}: id must look like ENV-001, INST-001 or UNIN-001")
        elif t.id.split("-")[0] != t.category.value:
            errors.append(f"{t.id}: id prefix doesn't match category {t.category.value}")
        if t.origin is not Origin.AGENT:
            errors.append(f"{t.id}: origin must be 'agent'")
        if t.source is None:
            errors.append(f"{t.id}: source citation is missing")
        else:
            check_citation(f"{t.id}.source", t.source)
        _check_expectations(t, errors)
        for text in _texts_of(t):
            if USER_PROFILE_PATH.search(text):
                errors.append(f"{t.id}: hard-coded user profile path {text!r}; use a placeholder or %AppData%")

    # preconditions: known ids, no cycles
    known = set(ids) | {BUILT_IN_ENV_ID}
    for t in plan.testcases:
        for p in t.preconditions:
            if p not in known:
                errors.append(f"{t.id}: precondition {p} is not a test in this plan")
    cycle = _find_cycle({t.id: [p for p in t.preconditions if p in known] for t in plan.testcases})
    if cycle:
        errors.append(f"preconditions form a cycle: {' -> '.join(cycle)}")

    # placeholders
    used = {name for t in plan.testcases for text in _texts_of(t) for name in PLACEHOLDER.findall(text)}
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


def _texts_of(t: TestCase) -> list[str]:
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
