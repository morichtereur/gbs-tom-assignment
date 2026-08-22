"""A known-infeasible input must fail, not silently relax.

This is the test the whole constraint layer exists for. A solver that quietly
drops a segregation-of-duties constraint in order to return something still
returns an assignment, and that assignment looks exactly like a feasible one.
The failure has to be loud.
"""

from __future__ import annotations

import pytest

from tom.solve import Infeasible, Scenario, solve
from tom.sod import breaches, incompatible_pairs
from tom.types import Instance, Unit


def _with_units(instance: Instance, units: list[Unit]) -> Instance:
    return Instance(
        activities=instance.activities,
        locations=instance.locations,
        edges=instance.edges,
        units=units,
        families=instance.families,
        settings=instance.settings,
        bands=instance.bands,
    )


def test_one_unit_and_a_segregation_pair_is_infeasible(instance):
    # Every activity must go somewhere and two of them may not go to the same
    # place. With one place available that is a contradiction, and CP-SAT has to
    # say so rather than pick a winner.
    single = _with_units(
        instance, [u for u in instance.units if u.key == "retained@ch"]
    )
    with pytest.raises(Infeasible):
        solve(single)


def test_the_same_input_solves_once_the_constraint_is_removed(instance):
    # The other half of the test. Without this, the failure above could be a
    # broken model rather than a working constraint.
    single = _with_units(
        instance, [u for u in instance.units if u.key == "retained@ch"]
    )
    result = solve(single, scenario=Scenario(handoff_price=1.5, disabled=frozenset({"sod"})))
    assert result.status == "OPTIMAL"
    assert len({u.key for u in result.units.values()}) == 1
    # And the thing the constraint was preventing is now present, which is what
    # makes the infeasibility above meaningful rather than incidental.
    assert len(breaches(result.units)) == len(
        [p for p in incompatible_pairs() if all(n in result.units for n in p)]
    )


def test_an_activity_with_no_feasible_unit_is_infeasible(instance):
    # Contact activities need a city inside the working day. Remove the retained
    # anchor and the automated unit, raise the bar past every city, and there is
    # nowhere left — which must raise rather than quietly place the work.
    cities_only = _with_units(
        instance, [u for u in instance.units if u.model in ("captive", "provider")]
    )
    impossible = dict(instance.settings.constraints)
    impossible["contact_coverage"] = {
        **impossible["contact_coverage"],
        "min_overlap_hours": 99.0,
    }
    tightened = Instance(
        activities=cities_only.activities,
        locations=cities_only.locations,
        edges=cities_only.edges,
        units=cities_only.units,
        families=cities_only.families,
        settings=type(instance.settings)(
            **{**instance.settings.__dict__, "constraints": impossible}
        ),
        bands=cities_only.bands,
    )
    with pytest.raises(Infeasible, match="no feasible unit"):
        solve(tightened)


def test_a_site_minimum_above_the_whole_process_closes_every_captive(instance):
    # 69 FTE of work cannot open a 500-FTE site. The model must not open one
    # anyway, and it must not fail either: retained, provider and automated are
    # all still available, so the right answer is a captive-free assignment.
    hours = instance.settings.productive_hours_per_fte_year
    total = sum(a.fte(hours) for a in instance.assignable)
    assert total < 500

    raised = dict(instance.settings.constraints)
    raised["min_site_size"] = {**raised["min_site_size"], "fte": 500}
    tightened = Instance(
        activities=instance.activities,
        locations=instance.locations,
        edges=instance.edges,
        units=instance.units,
        families=instance.families,
        settings=type(instance.settings)(
            **{**instance.settings.__dict__, "constraints": raised}
        ),
        bands=instance.bands,
    )
    result = solve(tightened)
    assert result.status == "OPTIMAL"
    assert not any(u.model == "captive" for u in result.units.values())


def test_infeasibility_names_what_was_switched_off(instance):
    single = _with_units(
        instance, [u for u in instance.units if u.key == "retained@ch"]
    )
    with pytest.raises(Infeasible) as caught:
        solve(single, scenario=Scenario(handoff_price=1.5, disabled=frozenset({"judgment_cap"})))
    assert "judgment_cap" in str(caught.value)
