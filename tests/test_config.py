"""The loader refuses the inputs it should refuse."""

from __future__ import annotations

import pytest
import yaml

from tom.config import CONFIG, equivalence_classes, load_settings, _constraints


def test_every_activity_in_the_log_has_a_declared_mapping(instance):
    # A missing entry must be an error rather than a default. A default here is
    # an unstated judgement, which is the exact failure mode this study is about.
    assert len(instance.activities) == 42
    assert all(a.why for a in instance.activities)
    assert all(a.isco in (2, 3, 4) for a in instance.activities)


def test_constraints_must_declare_enabled():
    with pytest.raises(ValueError, match="enabled"):
        _constraints([{"id": "sod"}])


def test_yaml_bare_on_key_is_a_boolean():
    # The reason the flag is called `enabled`. Kept as a test so nobody renames
    # it back without meeting the reason.
    assert yaml.safe_load("on: true") == {True: True}


def test_only_buyer_activities_are_assignable(instance):
    assert {a.owner for a in instance.activities} == {"buyer", "vendor", "system"}
    assert all(a.assignable for a in instance.assignable)
    assert len(instance.assignable) == 29
    # Vendor-side activities carry no handling time — they are not the buyer's work.
    assert all(a.minutes == 0 for a in instance.activities if a.owner == "vendor")


def test_bands_group_only_genuinely_identical_locations(instance):
    settings = load_settings()
    for representative, members in instance.bands.items():
        assert representative in members
        for member in members:
            a, b = instance.locations[representative], instance.locations[member]
            assert a.wage_usd_month == b.wage_usd_month
            assert a.overlap_hours == b.overlap_hours


def test_bands_cover_every_city_exactly_once(instance):
    cities = {k for k, loc in instance.locations.items() if loc.is_city}
    banded = [m for members in instance.bands.values() for m in members]
    assert sorted(banded) == sorted(cities)
    assert len(banded) == len(set(banded))


def test_priced_edges_exclude_self_loops_and_unassignable(instance):
    assignable = {a.name for a in instance.assignable}
    assert all(e.src != e.dst for e in instance.edges)
    assert all(e.src in assignable and e.dst in assignable for e in instance.edges)


def test_sod_pairs_name_real_activities(instance):
    from tom.sod import incompatible_pairs

    names = {a.name for a in instance.activities}
    for first, second in incompatible_pairs():
        assert first in names and second in names
        assert first != second
