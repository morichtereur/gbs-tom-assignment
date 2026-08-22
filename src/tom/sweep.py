"""Sweep the coordination price and find where the answer changes shape.

At a coordination price of zero every activity goes to its own cheapest
feasible unit and the model scatters. As the price rises, keeping work together
starts to pay and the model concentrates. The price at which that flip happens
is the second pre-registered metric, and it is the thing the reader drags on
the page.

The sweep is also what the web layer runs on: a ladder of pre-solved points, so
the control interpolates over real optima rather than re-solving in a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from tom.solve import Scenario, solve
from tom.types import Assignment, Instance


@dataclass(frozen=True)
class SweepPoint:
    price: float
    assignment: Assignment

    @property
    def units_used(self) -> int:
        return len({u.key for u in self.assignment.units.values()})

    @property
    def cities_used(self) -> int:
        return len({
            u.location for u in self.assignment.units.values()
            if u.location is not None
        })

    @property
    def signature(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((k, v.key) for k, v in self.assignment.units.items()))


def sweep(
    instance: Instance,
    prices: Sequence[float],
    *,
    scenario: Scenario | None = None,
    **kw,
) -> list[SweepPoint]:
    """Solve to optimality at each price. Exact, not interpolated."""
    base = scenario or Scenario(handoff_price=0.0)
    out = []
    for price in prices:
        sc = Scenario(**{**base.__dict__, "handoff_price": float(price)})
        out.append(SweepPoint(float(price), solve(instance, scenario=sc, **kw)))
    return out


def breakpoints(points: Sequence[SweepPoint]) -> list[tuple[float, float, int, int]]:
    """Adjacent sweep points whose assignment differs.

    Returned as (price_below, price_above, units_below, units_above). The true
    breakpoint is somewhere in the bracket; `bisect` narrows it.
    """
    out = []
    for lo, hi in zip(points, points[1:]):
        if lo.signature != hi.signature:
            out.append((lo.price, hi.price, lo.units_used, hi.units_used))
    return out


def bisect(
    instance: Instance,
    predicate: Callable[[Assignment], bool],
    lo: float,
    hi: float,
    *,
    tolerance: float = 0.005,
    scenario: Scenario | None = None,
    **kw,
) -> float | None:
    """Narrow the price at which `predicate` starts holding.

    Assumes the predicate is monotone in price over [lo, hi] — true for
    "concentrates into at most N units", since raising the price only ever makes
    crossing a boundary more expensive. Returns None where it does not flip
    inside the bracket, which is itself a reportable answer.
    """
    base = scenario or Scenario(handoff_price=0.0)

    def at(price: float) -> Assignment:
        return solve(
            instance,
            scenario=Scenario(**{**base.__dict__, "handoff_price": float(price)}),
            **kw,
        )

    if predicate(at(lo)) or not predicate(at(hi)):
        return None

    while hi - lo > tolerance:
        mid = (lo + hi) / 2.0
        if predicate(at(mid)):
            hi = mid
        else:
            lo = mid
    return hi


def concentration_tipping_point(
    instance: Instance,
    *,
    lo: float = 0.0,
    hi: float = 200.0,
    scenario: Scenario | None = None,
    **kw,
) -> tuple[float | None, int, int]:
    """The price at which the optimum stops spreading work out.

    Measured on crossing transitions rather than on the number of units. Unit
    count is the intuitive reading but it is not monotone in price — the solver
    will happily use one more unit if that particular split isolates a
    high-volume pair — so bisecting on it is not valid. Crossings are monotone
    by construction (raising the price only ever makes a crossing dearer), which
    `tests/test_objective.py` asserts, so the bisection rests on something true.

    Returns (price, crossings_at_the_floor, units_at_the_floor). A None price
    means the optimum never reaches its floor inside the bracket, which is a
    reportable answer rather than an error.
    """
    base = scenario or Scenario(handoff_price=0.0)
    top = solve(
        instance,
        scenario=Scenario(**{**base.__dict__, "handoff_price": float(hi)}),
        **kw,
    )
    floor_crossings = top.crossings

    price = bisect(
        instance,
        lambda a: a.crossings <= floor_crossings,
        lo,
        hi,
        scenario=base,
        **kw,
    )
    return price, floor_crossings, len({u.key for u in top.units.values()})


def largest_structural_break(
    instance: Instance,
    points: Sequence[SweepPoint],
    *,
    scenario: Scenario | None = None,
    tolerance: float = 0.005,
    **kw,
) -> dict | None:
    """The price at which the assignment reorganises most, narrowed by bisection.

    This is the reported tipping point, and the definition was changed after
    seeing the sweep. The first definition was the price at which crossing
    transitions reach their floor. On this instance that lands at USD 111 per
    handoff, on the back of a final improvement worth 1.1% of crossings — a
    number with no claim to being the point where anything flips.

    "Flips away from concentration" is a statement about the assignment
    changing, so it is measured on the assignment: the adjacent pair of prices
    across which the most activities change unit. Nothing is tuned by this — the
    objective, the constraints and the ladder are untouched — but it is a
    definition chosen with the data in view, and it is disclosed as such rather
    than presented as the plan all along. The rejected number is reported
    alongside it.
    """
    best = None
    for lower, upper in zip(points, points[1:]):
        above = dict(upper.signature)
        moved = sum(1 for activity, unit in lower.signature if above.get(activity) != unit)
        if moved and (best is None or moved > best[2]):
            best = (lower.price, upper.price, moved)
    if best is None:
        return None

    low, high, moved = best
    # Crossings are monotone in price, so the breakpoint inside the bracket can
    # be narrowed exactly.
    target = next(p for p in points if p.price == high).assignment.crossings
    price = bisect(
        instance,
        lambda a: a.crossings <= target,
        low,
        high,
        tolerance=tolerance,
        scenario=scenario,
        **kw,
    )
    return {
        "price": price if price is not None else high,
        "bracket": [low, high],
        "activities_moved": moved,
    }
