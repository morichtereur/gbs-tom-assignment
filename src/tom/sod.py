"""Segregation of duties.

The rule is ported from `finance-close-control-agent`, control CHK-03: where
one party both prepares and approves, that is a control failure irrespective of
amount. This module does not re-derive that rule. It changes its subject from a
user id to an organisational unit, which is the only translation a target
operating model needs, and applies it to the pairs declared in
`config/sod.yaml`.

    upstream  src/fcca/controls/journal_checks.py::check_segregation_of_duties
              policies/journal_entry_policy.md, section 2
"""

from __future__ import annotations

from functools import lru_cache
from typing import Mapping, Sequence

import yaml

from tom.config import CONFIG
from tom.types import Unit


@lru_cache(maxsize=1)
def incompatible_pairs() -> tuple[tuple[str, str], ...]:
    """The declared activity pairs that may not share a unit."""
    raw = yaml.safe_load((CONFIG / "sod.yaml").read_text())
    return tuple(tuple(pair) for pair in raw["pairs"])


def breaches(units: Mapping[str, Unit]) -> tuple[tuple[str, str, str], ...]:
    """Pairs sharing a unit in a finished assignment.

    The same check the upstream control runs, applied to the output rather than
    inside the solver — so a breach is caught even if the constraint was
    switched off, which is the point of the ablation.
    """
    found = []
    for first, second in incompatible_pairs():
        if first in units and second in units and units[first] == units[second]:
            found.append((first, second, units[first].key))
    return tuple(found)


def pairs_touching(activity: str) -> Sequence[str]:
    """Every activity that cannot share a unit with this one."""
    out = []
    for first, second in incompatible_pairs():
        if first == activity:
            out.append(second)
        elif second == activity:
            out.append(first)
    return tuple(out)
