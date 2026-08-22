"""The same input gives the same answer, in this process and in another one.

This instance is degenerate: several locations carry an identical wage upstream
and a dozen activities are too small for their position to change the bill. That
makes a tied optimum the normal case rather than the exception, and without a
declared order the solver returns a different member of the tie each run. A
reader watching the assignment move for no reason has been shown noise as
though it were a finding.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tom import load_instance, solve

ROOT = Path(__file__).resolve().parent.parent

PROBE = """
import json, sys
sys.path.insert(0, "src")
from tom import load_instance, solve
result = solve(load_instance())
print(json.dumps(sorted((k, v.key) for k, v in result.units.items())))
"""


def _signature(assignment) -> list:
    return sorted((k, v.key) for k, v in assignment.units.items())


def test_repeated_solves_agree(instance):
    assert len({json.dumps(_signature(solve(instance))) for _ in range(3)}) == 1


def test_separate_processes_agree():
    # The one that actually bites. Set iteration order over strings depends on
    # PYTHONHASHSEED, which is randomised per process, so a set anywhere in the
    # model-building path makes the answer differ between runs of the same code.
    runs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", PROBE],
            cwd=ROOT, capture_output=True, text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stderr
        runs.add(proc.stdout.strip())
    assert len(runs) == 1


def test_the_tie_break_never_outranks_a_real_difference(instance):
    # The three objectives are packed into one integer. If the scales were wrong
    # the unit-count preference could buy itself a more expensive assignment.
    from tom.solve import PRIMARY_SCALE, UNIT_SCALE

    assert PRIMARY_SCALE > UNIT_SCALE * len(instance.units)
    assert UNIT_SCALE > len(instance.assignable) * len(instance.units)


def test_the_tie_break_does_not_change_the_optimal_cost(instance):
    # Turning the preference off must leave the cost exactly where it was. Only
    # which of the tied answers comes back may change.
    from tom.types import Settings

    without = Settings(**{
        **instance.settings.__dict__,
        "objective": {**instance.settings.objective, "tie_break": "none"},
    })
    plain = type(instance)(
        activities=instance.activities, locations=instance.locations,
        edges=instance.edges, units=instance.units, families=instance.families,
        settings=without, bands=instance.bands,
    )
    assert round(solve(plain).total_cost, 2) == round(solve(instance).total_cost, 2)
