"""The CP-SAT assignment model.

Solution hints from a previous optimum were tried and dropped: on this
instance they roughly doubled the solve time rather than shortening it,
because the search is already short and the hint mostly costs propagation.

One decision per activity: which (delivery model, location) unit it sits in.
The instance is 29 activities over 24 units, which is small enough to solve to
proven optimality in well under a second, so nothing here is a heuristic and
nothing here is handed to a language model.

Costs are carried in integer cents. CP-SAT is an integer solver, and rounding
once at the boundary is honest in a way that rounding inside the objective is
not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ortools.sat.python import cp_model

from tom.types import Activity, Assignment, Instance, Location, Unit

CENTS = 100
# Three objectives in strict priority order, packed into one integer:
#     cost (cents) >> number of units used >> a fixed unit ordering
# The scales are chosen so a lower priority can never outrank a higher one.
# Largest possible ordering term is 29 activities x 18 units = 522, so the
# unit scale clears it; largest unit term is 18 x 1000, so the cost scale
# clears that.
ORDER_SCALE = 1
UNIT_SCALE = 1_000
PRIMARY_SCALE = 100_000
# FTE is carried as hundredths so the minimum-site constraint stays integral.
FTE_SCALE = 100


class Infeasible(RuntimeError):
    """Raised when no assignment satisfies the constraints.

    Deliberately loud. A model that quietly relaxes a control constraint to
    return an answer is worse than one that refuses, because the answer looks
    exactly like a feasible one.
    """


@dataclass(frozen=True)
class Scenario:
    """One draw. Everything here is a quantity this study declared rather than
    measured, which is exactly the set that has to be resampled."""

    handoff_price: float
    minutes: Mapping[str, float] = field(default_factory=dict)
    wage_multiplier: Mapping[str, float] = field(default_factory=dict)
    automation_cost_per_1k: float | None = None
    isco: Mapping[str, int] = field(default_factory=dict)
    families: Mapping[str, str] = field(default_factory=dict)
    disabled: frozenset[str] = frozenset()

    def minutes_for(self, a: Activity) -> float:
        return self.minutes.get(a.name, a.minutes)

    def isco_for(self, a: Activity) -> int:
        return self.isco.get(a.name, a.isco)


def _labour_cents(
    activity: Activity,
    unit: Unit,
    instance: Instance,
    scenario: Scenario,
) -> int:
    """Annual labour cost of running one activity in one unit, in cents."""
    s = instance.settings
    hours = activity.hours(scenario.minutes_for(activity))
    isco = scenario.isco_for(activity)

    if unit.model == "automated":
        auto = s.automation
        per_1k = (
            auto["cost_per_1k_events_usd"]
            if scenario.automation_cost_per_1k is None
            else scenario.automation_cost_per_1k
        )
        run = activity.events / 1000.0 * per_1k
        # The exceptions automation does not absorb come back to the business,
        # not to the cheapest city, because an exception with no owner ends up
        # with whoever owns the process.
        anchor = instance.locations[s.retained_location]
        residual = (
            hours
            * auto["residual_labour_share"]
            * anchor.hourly(isco, s.paid_hours_per_month)
        )
        return round((run + residual) * CENTS)

    loc: Location = instance.locations[unit.location]
    multiplier = scenario.wage_multiplier.get(
        unit.model, s.delivery_models[unit.model]["wage_multiplier"]
    )
    return round(hours * loc.hourly(isco, s.paid_hours_per_month) * multiplier * CENTS)


def _feasible_units(
    activity: Activity, instance: Instance, scenario: Scenario
) -> list[Unit]:
    """Units this activity may occupy before any cross-activity constraint."""
    s = instance.settings
    contact = s.constraints["contact_coverage"]
    contact_on = (
        s.enabled("contact_coverage") and "contact_coverage" not in scenario.disabled
    )
    auto_on = s.automation

    barred = set(instance.barred.get(activity.name, ()))
    out = []
    for unit in instance.units:
        if unit.key in barred:
            continue
        if unit.model == "automated":
            # Evidenced, not asserted: an activity may be automated only where
            # the log already shows it running in batch. `Clear Invoice` runs
            # 0% batch across 24 users, so it cannot be automated here.
            if activity.batch_share < auto_on["evidence_floor"]:
                continue
            out.append(unit)
            continue

        loc = instance.locations[unit.location]
        if contact_on and activity.contact and loc.is_city:
            # Applied to delivery cities only. The retained anchor is where the
            # business already sits, so it speaks the business's language by
            # construction and a 5-posting language sample says nothing there.
            if loc.overlap_hours < contact["min_overlap_hours"]:
                continue
            if loc.language_share < contact["min_language_share"]:
                continue
        out.append(unit)

    return out


def build_model(
    instance: Instance, scenario: Scenario
) -> tuple[cp_model.CpModel, dict, dict, dict]:
    """Assemble the CP-SAT model. Split out so the tests can inspect it."""
    s = instance.settings
    model = cp_model.CpModel()
    activities = list(instance.assignable)
    by_name = {a.name: a for a in activities}

    # --- decision: one unit per activity ------------------------------------
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    allowed: dict[str, list[Unit]] = {}
    for a in activities:
        units = _feasible_units(a, instance, scenario)
        if not units:
            raise Infeasible(
                f"{a.name!r} has no feasible unit. Contact coverage or the "
                f"automation evidence floor has excluded every option."
            )
        allowed[a.name] = units
        for u in units:
            x[(a.name, u.key)] = model.NewBoolVar(f"x[{a.name}|{u.key}]")
        model.AddExactlyOne(x[(a.name, u.key)] for u in units)

    # --- segregation of duties ----------------------------------------------
    if s.enabled("sod") and "sod" not in scenario.disabled:
        from tom.sod import incompatible_pairs

        for first, second in incompatible_pairs():
            if first not in by_name or second not in by_name:
                continue
            shared = sorted(
                {u.key for u in allowed[first]} & {u.key for u in allowed[second]}
            )
            for key in shared:
                model.AddAtMostOne([x[(first, key)], x[(second, key)]])

    # --- minimum viable site size -------------------------------------------
    # Only models that carry their own site. A provider's floor already exists
    # and is shared with its other clients, which is the whole asymmetry.
    open_site: dict[str, cp_model.IntVar] = {}
    if s.enabled("min_site_size") and "min_site_size" not in scenario.disabled:
        floor = round(s.constraints["min_site_size"]["fte"] * FTE_SCALE)
        carriers = [
            name for name, spec in s.delivery_models.items() if spec.get("site_overhead")
        ]
        for unit in instance.units:
            if unit.model not in carriers or unit.location is None:
                continue
            members = [
                (a, x[(a.name, unit.key)])
                for a in activities
                if (a.name, unit.key) in x
            ]
            if not members:
                continue
            flag = model.NewBoolVar(f"open[{unit.key}]")
            open_site[unit.key] = flag
            fte_terms = [
                (round(a.fte(s.productive_hours_per_fte_year,
                             scenario.minutes_for(a)) * FTE_SCALE), var)
                for a, var in members
            ]
            for _, var in members:
                model.Add(var <= flag)
            model.Add(sum(w * v for w, v in fte_terms) >= floor * flag)
            model.Add(flag <= sum(v for _, v in members))

    # --- judgment cannot pile into a transactional hub ----------------------
    if s.enabled("judgment_cap") and "judgment_cap" not in scenario.disabled:
        cap = s.constraints["judgment_cap"]
        families = {**instance.families, **scenario.families}
        hubs = [
            loc for loc in instance.locations.values()
            if loc.is_city
            and (loc.transactional_share or 0.0) >= cap["hub_transactional_threshold"]
        ]
        share = cap["max_judgment_share"]
        for loc in hubs:
            terms_judgment, terms_all = [], []
            for a in activities:
                weight = round(
                    a.fte(s.productive_hours_per_fte_year, scenario.minutes_for(a))
                    * FTE_SCALE
                )
                for u in allowed[a.name]:
                    if u.location != loc.key:
                        continue
                    var = x[(a.name, u.key)]
                    terms_all.append((weight, var))
                    if families.get(a.name) == "judgment":
                        terms_judgment.append((weight, var))
            if not terms_judgment:
                continue
            # judgment <= share * total, kept integral by scaling both sides.
            model.Add(
                round(1000) * sum(w * v for w, v in terms_judgment)
                <= round(share * 1000) * sum(w * v for w, v in terms_all)
            )

    # --- objective -----------------------------------------------------------
    labour = [
        _labour_cents(a, u, instance, scenario) * x[(a.name, u.key)]
        for a in activities
        for u in allowed[a.name]
    ]

    same: dict[tuple[str, str], cp_model.IntVar] = {}
    handoff_terms = []
    price_cents = round(scenario.handoff_price * CENTS)
    for edge in instance.edges:
        if edge.src not in by_name or edge.dst not in by_name:
            continue
        # `same` is symmetric, and the log carries plenty of pairs in both
        # directions (a rework loop is A->B and B->A). Keying the flag on the
        # unordered pair halves the variables at no cost to the model.
        pair = (edge.src, edge.dst) if edge.src < edge.dst else (edge.dst, edge.src)
        if pair not in same:
            first, second = pair
            # Sorted, not a set: iteration order over a set of strings
            # depends on PYTHONHASHSEED, and that order decides which member
            # of a tied optimum CP-SAT returns. Without this the same code on
            # the same data gives a different assignment between processes.
            shared = sorted(
                {u.key for u in allowed[first]} & {u.key for u in allowed[second]}
            )
            togethers = []
            for key in shared:
                # z <= x[a,u] and z <= x[b,u] is enough to encode the AND here.
                # The objective pays for (1 - same), so the solver pushes z up on
                # its own and the lower bound would be redundant work. Linear
                # bounds rather than AddMultiplicationEquality: same optimum,
                # roughly a third of the solve time on this instance.
                both = model.NewBoolVar(f"same[{first}|{second}|{key}]")
                model.Add(both <= x[(first, key)])
                model.Add(both <= x[(second, key)])
                togethers.append(both)
            flag = model.NewBoolVar(f"same[{first}|{second}]")
            if togethers:
                model.Add(flag == sum(togethers))
            else:
                model.Add(flag == 0)
            same[pair] = flag
        # cases * price for every case that crosses a boundary
        handoff_terms.append(edge.cases * price_cents * (1 - same[pair]))

    # A `used` flag per unit, for the declared tie-break. Only an upper link is
    # needed: the tie-break pushes the flags down, so the solver cannot leave a
    # flag set on a unit it did not use.
    used: dict[str, cp_model.IntVar] = {}
    for unit in instance.units:
        members = [x[(a.name, unit.key)] for a in activities if (a.name, unit.key) in x]
        if not members:
            continue
        flag = model.NewBoolVar(f"used[{unit.key}]")
        for var in members:
            model.Add(var <= flag)
        used[unit.key] = flag

    order = {u.key: i for i, u in enumerate(instance.units)}
    tie_break = 0
    if s.objective.get("tie_break") == "fewest_units_then_fixed_order":
        tie_break = UNIT_SCALE * sum(used.values()) + ORDER_SCALE * sum(
            order[key] * var for (_, key), var in x.items()
        )
    model.Minimize(PRIMARY_SCALE * (sum(labour) + sum(handoff_terms)) + tie_break)

    return model, x, same, open_site


def solve(
    instance: Instance,
    handoff_price: float | None = None,
    *,
    scenario: Scenario | None = None,
    time_limit_s: float = 30.0,
    # One worker, not a portfolio. CP-SAT's parallel search races, so eight
    # workers return a different member of a tied optimum run to run. The
    # instance solves in well under a second either way.
    workers: int = 1,
    seed: int = 0,
) -> Assignment:
    """Solve to proven optimality and return the assignment."""
    s = instance.settings
    if scenario is None:
        price = (
            handoff_price
            if handoff_price is not None
            else s.objective["handoff_cost_usd"]
        )
        scenario = Scenario(handoff_price=price)
    elif handoff_price is not None:
        scenario = Scenario(**{**scenario.__dict__, "handoff_price": handoff_price})

    model, x, same, open_site = build_model(instance, scenario)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    # Pinned so a reported optimum is reproducible. The instance is
    # degenerate — the five Indian cities carry an identical wage upstream —
    # so without this the tie is broken differently on different runs and a
    # reader would see the assignment move for no reason.
    solver.parameters.random_seed = seed
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise Infeasible(
            f"no assignment satisfies the constraints "
            f"(CP-SAT status {solver.StatusName(status)}). "
            f"Disabled: {sorted(scenario.disabled) or 'none'}."
        )

    units_by_key = {u.key: u for u in instance.units}
    chosen: dict[str, Unit] = {}
    for (name, key), var in x.items():
        if solver.Value(var):
            chosen[name] = units_by_key[key]

    labour = sum(
        _labour_cents(instance.by_name(name), unit, instance, scenario)
        for name, unit in chosen.items()
    ) / CENTS

    crossings = sum(
        edge.cases
        for edge in instance.edges
        if edge.src in chosen and edge.dst in chosen
        and chosen[edge.src] != chosen[edge.dst]
    )

    return Assignment(
        units=chosen,
        labour_cost=labour,
        handoff_cost=crossings * scenario.handoff_price,
        crossings=crossings,
        status=solver.StatusName(status),
        handoff_price=scenario.handoff_price,
        open_sites=tuple(sorted(k for k, v in open_site.items() if solver.Value(v))),
    )


def forced_positions(
    instance: Instance,
    scenario: Scenario | None = None,
    **kw,
) -> dict[str, dict]:
    """Which activities cost decides, and which a tie-break merely placed.

    For each activity in turn, bar it from the unit it was given and solve
    again. If the total cost does not move, that position was never decided by
    anything real — several answers were equally good and the declared tie-break
    picked one. If the cost does move, the number that comes back is what the
    position is worth.

    This is the difference between an assignment and a recommendation, and it is
    measured rather than inferred: one extra solve per activity, at one price.
    """
    scenario = scenario or Scenario(
        handoff_price=instance.settings.objective["handoff_cost_usd"]
    )
    reference = solve(instance, scenario=scenario, **kw)
    baseline_cost = round(reference.total_cost, 2)

    out: dict[str, dict] = {}
    for activity in instance.assignable:
        chosen = reference.units[activity.name]
        barred = Instance(
            activities=instance.activities,
            locations=instance.locations,
            edges=instance.edges,
            units=instance.units,
            families=instance.families,
            settings=instance.settings,
            bands=instance.bands,
            barred={activity.name: (chosen.key,)},
        )
        try:
            alternative = solve(barred, scenario=scenario, **kw)
        except Infeasible:
            out[activity.name] = {
                "unit": chosen.key, "forced": True,
                "cost_of_moving": None, "next_best_unit": None,
            }
            continue
        delta = round(alternative.total_cost, 2) - baseline_cost
        out[activity.name] = {
            "unit": chosen.key,
            # Half a cent, not zero: the objective is integer cents, so anything
            # smaller is rounding rather than a difference.
            "forced": delta > 0.005,
            "cost_of_moving": delta,
            "next_best_unit": alternative.units[activity.name].key,
        }
    return out
