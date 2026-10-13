"""observations.json: one raw Observation per test, written as soon as it's known (ARCHITECTURE.md D30).

Used by the preflight (ENV-000) and by Agent 2's record_observation tool. A later entry for the same test
replaces the earlier one.
"""

import json
from pathlib import Path

from mpagent.models import Observation

OBSERVATIONS_FILE = "observations.json"


def load_observations(run_dir: Path) -> list[Observation]:
    path = run_dir / OBSERVATIONS_FILE
    if not path.exists():
        return []
    return [Observation.model_validate(o) for o in json.loads(path.read_text(encoding="utf-8"))]


def save_observation(run_dir: Path, obs: Observation) -> None:
    items = [o for o in load_observations(run_dir) if o.test_id != obs.test_id] + [obs]
    (run_dir / OBSERVATIONS_FILE).write_text(
        json.dumps([o.model_dump(mode="json") for o in items], indent=2, ensure_ascii=False), encoding="utf-8")
