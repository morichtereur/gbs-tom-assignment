"""Measure, at every price on the ladder, which positions the cost model decides.

`solve.forced_positions` answers this at one price. The page needs it at all of
them, because forced-ness is a property of the price and not of the assignment:
two prices can produce the same assignment while one of them has a real reason
for it and the other does not.

29 activities x ~70 prices is around two thousand solves, so it runs across
processes. Each is an independent optimality proof; nothing is shared.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Mapping, Sequence

from tom.config import load_instance
from tom.solve import Infeasible, Scenario, position_is_forced, solve
from tom.types import Instance

_WORKER: dict[str, Instance] = {}


def _init() -> None:
    _WORKER["instance"] = load_instance()


def _probe(payload: tuple[float, str, str, float]) -> tuple[float, str, bool]:
    """Bar one activity from one unit at one price and ask if the total can hold."""
    price, activity, barred_unit, reference_cost = payload
    instance = _WORKER["instance"]
    forced = position_is_forced(
        instance, activity, barred_unit, reference_cost,
        Scenario(handoff_price=price),
    )
    return price, activity, forced


def over_ladder(
    ladder: Sequence[Mapping],
    *,
    workers: int | None = None,
    progress: bool = True,
) -> dict[str, dict[str, dict]]:
    """Returns {price_as_string: {activity: {forced}}}."""
    instance = load_instance()
    assignable = [a.name for a in instance.assignable]
    workers = workers or max(1, (os.cpu_count() or 4) - 1)

    jobs = [
        (float(point["price"]), name, point["assignment"][name], round(point["total"], 2))
        for point in ladder
        for name in assignable
    ]

    out: dict[str, dict[str, dict]] = {
        f"{float(p['price']):.2f}": {} for p in ladder
    }
    done = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for price, activity, forced in pool.map(_probe, jobs, chunksize=8):
            out[f"{price:.2f}"][activity] = {"forced": forced}
            done += 1
            if progress and done % max(1, len(jobs) // 10) == 0:
                print(f"  {done:>5,}/{len(jobs):,}", flush=True)
    return out
