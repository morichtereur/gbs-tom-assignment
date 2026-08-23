"""The objective is what the report says it is.

Every number here is recomputed from the assignment by hand and compared with
what the solver charged. The point is that the reported cost cannot drift from
the model without a test failing.
"""

from __future__ import annotations

import pytest

from tom.solve import Scenario, _labour_cents, solve


def test_labour_cost_recomputes_from_the_assignment(instance, optimum):
    scenario = Scenario(handoff_price=optimum.handoff_price)
    by_hand = sum(
        _labour_cents(instance.by_name(name), unit, instance, scenario)
        for name, unit in optimum.units.items()
    ) / 100.0
    assert by_hand == pytest.approx(optimum.labour_cost, rel=1e-9)


def test_crossings_recompute_from_the_assignment(instance, optimum):
    by_hand = sum(
        edge.cases
        for edge in instance.edges
        if optimum.units[edge.src] != optimum.units[edge.dst]
    )
    assert by_hand == optimum.crossings
    assert optimum.handoff_cost == pytest.approx(
        optimum.crossings * optimum.handoff_price
    )


def test_a_wage_is_a_monthly_figure_turned_into_an_hourly_one(instance):
    location = instance.locations["ch"]
    settings = instance.settings
    assert location.hourly(4, settings.paid_hours_per_month) == pytest.approx(
        location.wage_usd_month[4] / settings.paid_hours_per_month
    )


def test_automation_is_priced_per_event_plus_residual_at_the_retained_anchor(instance):
    # Exceptions automation does not absorb come back to the business, not to
    # the cheapest city. Asserted because it is easy to lose in a refactor.
    activity = instance.by_name("Record Goods Receipt")
    automated = next(u for u in instance.units if u.model == "automated")
    scenario = Scenario(handoff_price=0.0)
    auto = instance.settings.automation
    anchor = instance.locations[instance.settings.retained_location]

    expected = (
        activity.events / 1000.0 * auto["cost_per_1k_events_usd"]
        + activity.hours()
        * auto["residual_labour_share"]
        * anchor.hourly(activity.isco, instance.settings.paid_hours_per_month)
    )
    assert _labour_cents(activity, automated, instance, scenario) == round(expected * 100)


def test_raising_the_price_never_increases_crossings(instance):
    # The model's one monotonicity property, and the assumption the tipping-point
    # bisection rests on. If this fails, the bisection is not valid.
    crossings = [
        solve(instance, price).crossings for price in (0.0, 0.5, 2.0, 8.0, 32.0)
    ]
    assert crossings == sorted(crossings, reverse=True)


def test_a_zero_price_makes_the_handoff_term_vanish(instance):
    free = solve(instance, 0.0)
    assert free.handoff_cost == 0.0
    assert free.total_cost == free.labour_cost + free.overhead_cost


def test_the_reported_total_is_the_thing_the_solver_minimised(instance, optimum):
    # The objective charges per-unit overhead, so a total that quietly left it
    # out would not be the number being minimised.
    per_unit = instance.settings.objective["unit_overhead_usd_per_year"]
    units = len({u.key for u in optimum.units.values()})
    assert optimum.overhead_cost == pytest.approx(units * per_unit)
    assert optimum.total_cost == pytest.approx(
        optimum.labour_cost + optimum.handoff_cost + optimum.overhead_cost
    )


def test_the_solver_never_returns_a_non_optimal_status(optimum):
    assert optimum.status == "OPTIMAL"


def test_the_fast_forced_probe_agrees_with_the_slow_one(instance, optimum):
    """The page asks 'is this position decided' a few thousand times.

    Asked as an optimisation — bar the unit, re-solve, compare totals — it needs
    an optimality proof each time. Asked as a feasibility question — bar the
    unit, is anything still this cheap — it does not. The two must give the same
    answer, or the fast one is not a shortcut but a different question.
    """
    from tom.solve import Scenario, forced_positions, position_is_forced

    scenario = Scenario(handoff_price=optimum.handoff_price)
    slow = forced_positions(instance, scenario)
    for activity in instance.assignable:
        fast = position_is_forced(
            instance, activity.name, optimum.units[activity.name].key,
            optimum.total_cost, scenario,
        )
        assert fast == slow[activity.name]["forced"], activity.name
