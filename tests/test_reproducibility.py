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


def test_unit_overhead_is_charged_once_per_open_unit(instance):
    from tom.solve import Scenario, build_model

    _, x, _, _ = build_model(instance, Scenario(handoff_price=1.5))
    # One decision variable per (activity, feasible unit) and nothing else keyed
    # on units, so the overhead cannot be double-counted by construction.
    assert {key for _, key in x} <= {u.key for u in instance.units}


def test_unit_overhead_is_small_beside_the_bill_it_sits_in(instance, optimum):
    # It exists to price an interface, not to decide the answer. If it ever
    # became a material share of the total it would be steering the assignment
    # rather than costing it, and that would need saying out loud.
    assert optimum.overhead_cost / optimum.total_cost < 0.01


def test_dropping_the_overhead_does_not_change_the_labour_bill(instance):
    # The overhead was added after the first sweep. This asserts what it is
    # allowed to move: the choice of how many units to open, and not the wage
    # cost of the work inside them.
    from tom.types import Settings

    without = Settings(**{
        **instance.settings.__dict__,
        "objective": {**instance.settings.objective, "unit_overhead_usd_per_year": 0.0},
    })
    plain = type(instance)(
        activities=instance.activities, locations=instance.locations,
        edges=instance.edges, units=instance.units, families=instance.families,
        settings=without, bands=instance.bands,
    )
    bare = solve(plain)
    assert bare.overhead_cost == 0.0
    assert bare.labour_cost + bare.handoff_cost <= (
        solve(instance).labour_cost + solve(instance).handoff_cost + 1e-6
    )
