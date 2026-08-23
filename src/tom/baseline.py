"""The workshop answer, built explicitly so it can be beaten or not beaten.

`naive_baseline` is what a target operating model looks like when it arrives as
four columns on a slide: pick the cheapest place, move everything that can
move, keep the approvals. It prices no coordination at all, which is the
assumption the whole study is testing.

It is built without the constraints by default — a workshop does not run a
segregation-of-duties check — and the constraints it breaks are reported rather
than repaired. `single_city_optimum` is the fair comparison alongside it: the
best assignment that is still forced to concentrate, so the reader can tell a
control failure apart from a mispriced handoff.
"""

from __future__ import annotations

from typing import Iterable

from tom.solve import Infeasible, Scenario, _labour_cents, solve
from tom.types import Assignment, Instance, Unit


def _city_units(instance: Instance, model: str) -> dict[str, Unit]:
    return {
        u.location: u
        for u in instance.units
        if u.model == model and u.location and instance.locations[u.location].is_city
    }


def rank_cities(instance: Instance, scenario: Scenario | None = None) -> list[tuple[str, float]]:
    """Cities by what it would cost to run all movable work there, cheapest first.

    Ranked on the actual activity mix rather than on a blended headline wage,
    because the mix is what decides which ISCO line dominates the bill.
    """
    scenario = scenario or Scenario(handoff_price=0.0)
    settings = instance.settings
    movable = [a for a in instance.assignable
               if a.name not in set(settings.baseline["keep_retained"])]
    out = []
    for key, unit in _city_units(instance, settings.baseline["delivery_model"]).items():
        total = sum(_labour_cents(a, unit, instance, scenario) for a in movable) / 100.0
        out.append((key, total))
    # Deterministic tie-break. India has no city-level wage in any reachable
    # source, so its five cities tie exactly and the ordering below decides
    # between them on employer depth. That tie is a limitation carried in from
    # upstream and it is reported, not hidden behind a stable sort.
    return sorted(
        out,
        key=lambda kv: (
            round(kv[1], 2),
            -(instance.locations[kv[0]].employers or 0),
            kv[0],
        ),
    )


def cost_ties(instance: Instance, ranked: list[tuple[str, float]]) -> list[list[str]]:
    """Groups of cities the cost model cannot separate.

    Compared against the group's own first member rather than against its
    predecessor, so a long chain of near-equal cities cannot drift into one
    group a half-cent at a time.
    """
    groups: list[list[str]] = []
    anchors: list[float] = []
    for key, total in ranked:
        if groups and abs(total - anchors[-1]) < 0.005:
            groups[-1].append(key)
        else:
            groups.append([key])
            anchors.append(total)
    return [g for g in groups if len(g) > 1]


def naive_baseline(
    instance: Instance,
    *,
    respect: Iterable[str] = (),
    scenario: Scenario | None = None,
) -> Assignment:
    """Cheapest city, everything that can move moves, approvals stay.

    `respect` names constraints the baseline is required to honour. Empty by
    default: the point of the baseline is that it honours none of them.
    """
    scenario = scenario or Scenario(handoff_price=instance.settings.objective["handoff_cost_usd"])
    settings = instance.settings
    respect = frozenset(respect)

    retained = next(u for u in instance.units if u.model == "retained")
    city_units = _city_units(instance, settings.baseline["delivery_model"])

    ranked = rank_cities(instance, scenario)
    if "contact_coverage" in respect:
        contact = settings.constraints["contact_coverage"]
        ranked = [
            (key, total) for key, total in ranked
            if instance.locations[key].overlap_hours >= contact["min_overlap_hours"]
            and instance.locations[key].language_share >= contact["min_language_share"]
        ]
    if not ranked:
        raise Infeasible("no city clears the constraints the baseline was asked to respect")

    target = city_units[ranked[0][0]]
    keep = set(settings.baseline["keep_retained"])

    units = {
        a.name: (retained if a.name in keep else target)
        for a in instance.assignable
    }

    labour = sum(
        _labour_cents(instance.by_name(name), unit, instance, scenario)
        for name, unit in units.items()
    ) / 100.0
    crossings = sum(
        e.cases for e in instance.edges
        if e.src in units and e.dst in units and units[e.src] != units[e.dst]
    )

    return Assignment(
        units=units,
        labour_cost=labour,
        handoff_cost=crossings * scenario.handoff_price,
        overhead_cost=(
            len({unit.key for unit in units.values()})
            * settings.objective.get("unit_overhead_usd_per_year", 0.0)
        ),
        crossings=crossings,
        status="BASELINE",
        handoff_price=scenario.handoff_price,
        open_sites=(target.key,),
    )


def single_city_optimum(
    instance: Instance, city: str, *, scenario: Scenario | None = None, **kw
) -> Assignment:
    """The best fully-constrained assignment that still concentrates in one city.

    Isolates the two reasons the workshop answer and the optimum differ: this one
    obeys every control, so whatever still separates it from the optimum is
    coordination cost and nothing else.
    """
    restricted = Instance(
        activities=instance.activities,
        locations=instance.locations,
        edges=instance.edges,
        units=[
            u for u in instance.units
            if u.location is None
            or not instance.locations[u.location].is_city
            or u.location == city
        ],
        families=instance.families,
        settings=instance.settings,
        bands=instance.bands,
    )
    return solve(restricted, scenario=scenario, **kw)


def difference_share(a: Assignment, b: Assignment) -> tuple[float, tuple[str, ...]]:
    """The pre-registered headline: share of activities assigned differently."""
    names = sorted(set(a.units) | set(b.units))
    differing = tuple(n for n in names if a.units.get(n) != b.units.get(n))
    return (len(differing) / len(names) if names else 0.0), differing
