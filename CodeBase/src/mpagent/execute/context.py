"""What each FUNC test starts from (FUNC_TESTS_PLAN.md F2, F5, Q13): its output folder and, if its feature card
names a sample, a copy of that sample. Done by code before Agent 2 starts.

  runs/<run>/evidence/<test_id>/   empty; everything the app under test produces in this test goes here
  runs/<run>/context/<sample>/     a copy of the sample from the samples folder; Agent 2 opens the copy, never
                                   the original (one copy per sample, shared by the tests that name it)
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from mpagent.design.samples import list_samples
from mpagent.execute.verdict import output_dir
from mpagent.models import Category, TestPlan
from mpagent.runlog import log

CONTEXT_DIR = "context"


@dataclass(frozen=True)
class FuncSetup:
    test_id: str
    output: Path  # the test's output folder
    sample: str | None  # the sample its feature card names, if any
    context: Path | None  # the copy of that sample; None if no sample is named or it couldn't be copied
    problem: str | None = None  # why a named sample has no copy


def prepare_func_tests(plan: TestPlan, run_dir: Path, samples_dir: Path | None) -> list[FuncSetup]:
    """Create each FUNC test's output folder and copy the samples their feature cards name."""
    sample_of = {c.test_id: c.sample for c in plan.summary.features if c.testable and c.test_id}
    copies: dict[str, tuple[Path | None, str | None]] = {}
    out: list[FuncSetup] = []
    for t in (t for t in plan.testcases if t.category is Category.FUNC):
        folder = output_dir(run_dir, t.id)
        folder.mkdir(parents=True, exist_ok=True)
        sample = sample_of.get(t.id)
        if sample and sample not in copies:
            copies[sample] = _copy_sample(sample, samples_dir, run_dir)
        context, problem = copies.get(sample, (None, None)) if sample else (None, None)
        out.append(FuncSetup(t.id, folder, sample, context, problem))
    return out


def _copy_sample(name: str, samples_dir: Path | None, run_dir: Path) -> tuple[Path | None, str | None]:
    source = next((s.path for s in list_samples(samples_dir) if s.name == name), None)
    if source is None:
        problem = f"sample '{name}' not found ({'SAMPLES_DIR is not set' if samples_dir is None else samples_dir})"
        log.warning("FUNC: %s", problem)
        return None, problem
    target = run_dir / CONTEXT_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    except OSError as e:
        problem = f"sample '{name}' could not be copied: {type(e).__name__}: {e}"
        log.warning("FUNC: %s", problem)
        return None, problem
    log.info("FUNC: copied sample '%s' to %s", name, target)
    return target, None


def func_block(setups: list[FuncSetup], load_sample: str | None = None) -> str:
    """The context part of Agent 2's input: the sample LOAD-000 opens (Q14), and per FUNC test its output
    folder and its context."""
    if not setups:
        return ""
    lines = []
    load = next((s for s in setups if load_sample and s.sample == load_sample), None)
    if load and load.context:
        lines.append(f"LOAD-000 context: open this copy of the sample '{load.sample}' through the host's UI (not a "
                     f"new empty document): {load.context}. The other LOAD tests and the FUNC tests that name this "
                     "sample then work in this open context.")
    elif load:
        lines.append(f"LOAD-000 context: the sample '{load.sample}' is not available ({load.problem}); record "
                     "LOAD-000 with executed: false and that reason.")
    lines.append("FUNC tests (after the LOAD tests, before UNIN; follow the host-interaction skill):")
    for s in setups:
        if s.context and s.sample == load_sample:
            context = (f"the copy of the sample '{s.sample}' that LOAD-000 opened (open it again if it was "
                       f"closed): {s.context}")
        elif s.context:
            context = f"open this copy of the sample '{s.sample}' through the host's UI: {s.context}"
        elif s.sample:
            context = (f"the sample '{s.sample}' is not available ({s.problem}); record this test with "
                       "executed: false and that reason")
        else:
            context = "no sample; prepare only what the test needs through the host's UI"
        lines += [f"- {s.test_id}:", f"    context: {context}",
                  f"    output folder (save everything the app produces in this test here): {s.output}"]
    return "\n".join(lines)
