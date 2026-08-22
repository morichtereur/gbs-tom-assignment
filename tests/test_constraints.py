"""Every constraint the model claims to enforce is enforced in its output.

Checked against the finished assignment rather than inside the solver, so the
test would still catch a constraint that was built but never bound.
"""

from __future__ import annotations

from collections import defaultdict

from tom.solve import Scenario, solve
from tom.sod import breaches, incompatible_pairs


def test_segregation_of_duties_holds_in_the_optimum(optimum):
    assert breaches(optimum.units) == ()


def test_removing_segregation_of_duties_produces_breaches(instance):
    # The constraint is not decorative: switch it off and the optimum takes the
    # shortcut it was forbidding. If this ever passes trivially, the constraint
    # was never binding and the ablation result is meaningless.
    relaxed = solve(instance, scenario=Scenario(
        handoff_price=instance.settings.objective["handoff_cost_usd"],
        disabled=frozenset({"sod"}),
    ))
    assert len(breaches(relaxed.units)) > 0


def test_contact_activities_reach_their_counterparty(instance, optimum):
    rule = instance.settings.constraints["contact_coverage"]
    for activity in instance.assignable:
        if not activity.contact:
            continue
        unit = optimum.units[activity.name]
        if unit.location is None:
            continue
        location = instance.locations[unit.location]
        if not location.is_city:
            continue
        assert location.overlap_hours >= rule["min_overlap_hours"]
        assert location.language_share >= rule["min_language_share"]


def test_open_captive_sites_clear_the_minimum(instance, optimum):
    floor = instance.settings.constraints["min_site_size"]["fte"]
    hours = instance.settings.productive_hours_per_fte_year
    per_unit = defaultdict(float)
    for name, unit in optimum.units.items():
        per_unit[unit.key] += instance.by_name(name).fte(hours)
    for key, fte in per_unit.items():
        if key.startswith("captive@"):
            assert fte >= floor, f"{key} opened with {fte:.1f} FTE"


def test_providers_are_exempt_from_the_site_minimum(instance):
    # The asymmetry is deliberate — a provider's floor already exists — so it is
    # asserted rather than left as a comment.
    spec = instance.settings.delivery_models
    assert spec["captive"]["site_overhead"] is True
    assert spec["provider"]["site_overhead"] is False


def test_judgment_does_not_pile_into_a_transactional_hub(instance, optimum):
    rule = instance.settings.constraints["judgment_cap"]
    hours = instance.settings.productive_hours_per_fte_year
    judgment, total = defaultdict(float), defaultdict(float)
    for name, unit in optimum.units.items():
        if unit.location is None:
            continue
        location = instance.locations[unit.location]
        if not location.is_city:
            continue
        if (location.transactional_share or 0.0) < rule["hub_transactional_threshold"]:
            continue
        fte = instance.by_name(name).fte(hours)
        total[unit.location] += fte
        if instance.families.get(name) == "judgment":
            judgment[unit.location] += fte
    for city, hub_total in total.items():
        if hub_total > 0:
            share = judgment[city] / hub_total
            assert share <= rule["max_judgment_share"] + 1e-9, f"{city} at {share:.1%}"


def test_automation_is_evidenced_not_asserted(instance, optimum):
    floor = instance.settings.automation["evidence_floor"]
    for name, unit in optimum.units.items():
        if unit.model == "automated":
            assert instance.by_name(name).batch_share >= floor


def test_clear_invoice_cannot_be_automated(instance):
    # The concrete case the evidence floor exists for: 194,393 events, 24 users,
    # zero batch. A slide would automate it; the log says nobody ever has.
    activity = instance.by_name("Clear Invoice")
    assert activity.batch_share == 0.0
    assert activity.batch_share < instance.settings.automation["evidence_floor"]
