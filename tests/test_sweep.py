"""The sweep, the bisection, and the assumption the bisection rests on."""

from __future__ import annotations

import pytest

from tom.solve import solve
from tom.sweep import bisect, largest_structural_break, sweep


def test_the_sweep_solves_every_price_to_optimality(instance):
    points = sweep(instance, [0.0, 1.0, 4.0])
    assert [p.price for p in points] == [0.0, 1.0, 4.0]
    assert all(p.assignment.status == "OPTIMAL" for p in points)


def test_bisection_returns_none_when_nothing_flips(instance):
    # A predicate already true at the bottom of the bracket has no flip to find,
    # and must say so rather than return the bracket's edge.
    assert bisect(instance, lambda a: True, 0.0, 4.0) is None
    assert bisect(instance, lambda a: False, 0.0, 4.0) is None


def test_bisection_narrows_a_real_flip(instance):
    ceiling = solve(instance, 30.0).crossings
    price = bisect(instance, lambda a: a.crossings <= ceiling, 0.0, 30.0, tolerance=0.05)
    assert price is not None
    assert solve(instance, price).crossings <= ceiling
    # And just below it, the property does not hold — which is what makes the
    # returned number a threshold rather than an arbitrary point above one.
    assert solve(instance, price - 0.2).crossings > ceiling


def test_the_largest_break_is_inside_its_own_bracket(instance):
    points = sweep(instance, [0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 6.0])
    found = largest_structural_break(instance, points, tolerance=0.05)
    assert found is not None
    low, high = found["bracket"]
    assert low <= found["price"] <= high
    assert found["activities_moved"] > 0
