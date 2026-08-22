"""Snapshot the two upstream repositories into versioned JSON under `data/`.

Two inputs are measurements somebody else already made, and this study does not
re-derive them:

  p2p-process-mining      the activity set and the directly-follows graph, read
                          off 1,595,923 SAP events across 251,734 PO line items
  gbs-location-selection  the eleven evidenced GBS cities and their wage panel

Each upstream repo carries its own virtualenv and dependency set, so this runs
their interpreter on a probe script rather than importing across environments.
The snapshot it writes is committed, which is what lets this repository run
standalone and what lets a reader see exactly which upstream numbers the answer
rests on.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = {
    "process": (ROOT.parent / "p2p-process-mining", "_probe_process.py"),
    "locations": (ROOT.parent / "gbs-location-selection", "_probe_locations.py"),
}


def _run(repo: Path, probe: str) -> dict:
    interpreter = repo / ".venv" / "bin" / "python"
    if not interpreter.exists():
        sys.exit(f"{repo.name}: no virtualenv at {interpreter}. Set that repo up first.")
    proc = subprocess.run(
        [str(interpreter), str(Path(__file__).resolve().parent / probe)],
        cwd=repo,
        capture_output=True,
        text=True,
        # The probe imports the upstream repo's own `src` package, and running a
        # script from outside the tree does not put the cwd on sys.path.
        env={**os.environ, "PYTHONPATH": str(repo)},
    )
    if proc.returncode != 0:
        sys.exit(f"{repo.name} probe failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


def main() -> None:
    (ROOT / "data").mkdir(exist_ok=True)

    repo, probe = UPSTREAM["process"]
    process = _run(repo, probe)
    (ROOT / "data" / "process.json").write_text(json.dumps(process, indent=1) + "\n")
    print(
        f"data/process.json    {len(process['activities'])} activities, "
        f"{len(process['edges'])} directly-follows pairs, "
        f"{process['transitions']:,} transitions over {process['cases']:,} cases"
    )

    repo, probe = UPSTREAM["locations"]
    loc = _run(repo, probe)
    (ROOT / "data" / "locations.json").write_text(json.dumps(loc, indent=1) + "\n")
    cities = [entry for entry in loc["locations"] if entry["is_city"]]
    print(
        f"data/locations.json  {len(cities)} cities, "
        f"{len(loc['locations']) - len(cities)} country-level markets, HQ {loc['hq_label']}"
    )


if __name__ == "__main__":
    main()
