"""What each FUNC test starts from (FUNC_TESTS_PLAN.md F2, F5, Q13): its output folder and, if its feature card
names a sample or an input file, a copy of it. Done by code before Agent 2 starts.

  runs/<run>/evidence/<test_id>/   empty; everything the app under test produces in this test goes here
  runs/<run>/context/<sample>/     a copy of the sample from the samples folder; Agent 2 opens the copy, never
                                   the original (one copy per sample, shared by the tests that name it)
  runs/<run>/context/inputs/<name>  a copy of the input file (INPUT_FILES); the app loads the copy through its
                                   own UI, in whatever document the test works in
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
    input_file: str | None = None  # the input file its feature card names, if any
    input_copy: Path | None = None  # the copy of that input file; None if none is named or it couldn't be copied
    input_problem: str | None = None  # why a named input file has no copy


def prepare_func_tests(plan: TestPlan, run_dir: Path, samples_dir: Path | None,
                       input_files: Path | None = None) -> list[FuncSetup]:
    """Create each FUNC test's output folder and copy the samples and input files their feature cards name."""
    testable = [c for c in plan.summary.features if c.testable and c.test_id]
    sample_of = {c.test_id: c.sample for c in testable}
    input_of = {c.test_id: c.input_file for c in testable}
    copies: dict[str, tuple[Path | None, str | None]] = {}
    input_copies: dict[str, tuple[Path | None, str | None]] = {}
    out: list[FuncSetup] = []
    for t in (t for t in plan.testcases if t.category is Category.FUNC):
        folder = output_dir(run_dir, t.id)
        folder.mkdir(parents=True, exist_ok=True)
        sample = sample_of.get(t.id)
        if sample and sample not in copies:
            copies[sample] = _copy_sample(sample, samples_dir, run_dir)
        context, problem = copies.get(sample, (None, None)) if sample else (None, None)
        name = input_of.get(t.id)
        if name and name not in input_copies:
            input_copies[name] = _copy_sample(name, input_files, run_dir, "input file", "INPUT_FILES", "inputs")
        copy, input_problem = input_copies.get(name, (None, None)) if name else (None, None)
        out.append(FuncSetup(t.id, folder, sample, context, problem, name, copy, input_problem))
    return out


def _copy_sample(name: str, samples_dir: Path | None, run_dir: Path, what: str = "sample",
                 setting: str = "SAMPLES_DIR", subfolder: str = "") -> tuple[Path | None, str | None]:
    source = next((s.path for s in list_samples(samples_dir) if s.name == name), None)
    if source is None:
        problem = f"{what} '{name}' not found ({f'{setting} is not set' if samples_dir is None else samples_dir})"
        log.warning("FUNC: %s", problem)
        return None, problem
    target = run_dir / CONTEXT_DIR / subfolder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    except OSError as e:
        problem = f"{what} '{name}' could not be copied: {type(e).__name__}: {e}"
        log.warning("FUNC: %s", problem)
        return None, problem
    log.info("FUNC: copied %s '%s' to %s", what, name, target)
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
        lines += [f"- {s.test_id}:", f"    context: {context}"]
        if s.input_copy:
            lines.append(f"    input file (when the steps load a file through the app's UI, load this copy by its full "
                         f"path; never the original): {s.input_copy}")
        elif s.input_file:
            lines.append(f"    input file: '{s.input_file}' is not available ({s.input_problem}); record this test "
                         "with executed: false and that reason")
        lines.append(f"    output folder (save everything the app produces in this test here): {s.output}")
    return "\n".join(lines)
