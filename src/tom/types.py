"""Typed interfaces at the module boundaries.

Everything that crosses between the loader, the solver, the sweep and the web
layer is one of these. They are frozen, so a stage cannot quietly mutate an
input another stage already read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

Owner = Literal["buyer", "vendor", "system"]
Family = Literal["transactional", "judgment"]
ModelName = Literal["retained", "captive", "provider", "automated"]


@dataclass(frozen=True)
class Activity:
    """One P2P activity: what the log measured, and what this study declared."""

    # measured — data/process.json, from the 1.6M-event log
    name: str
    events: int
    cases: int
    batch_share: float
    resources: int

    # declared — config/activities.yaml
    owner: Owner
    isco: int
    minutes: float
    contact: bool
    why: str

    # the hand label, held for scoring the classifier and never read by the model
    gold_family: Family

    @property
    def assignable(self) -> bool:
        return self.owner == "buyer"

    def hours(self, minutes: float | None = None) -> float:
        """Annual handling hours. `minutes` overrides the declared time."""
        return self.events * (self.minutes if minutes is None else minutes) / 60.0

    def fte(self, productive_hours: float, minutes: float | None = None) -> float:
        return self.hours(minutes) / productive_hours


@dataclass(frozen=True)
class Location:
    """A candidate location, carried through from gbs-location-selection."""

    key: str
    city: str | None
    market: str
    market_name: str
    market_type: str
    is_city: bool
    wage_usd_month: Mapping[int, float]      # ISCO major group -> monthly USD
    cost_city_level: bool
    overlap_hours: float
    governance: float | None
    employers: int | None
    language_share: float
    transactional_share: float | None

    @property
    def label(self) -> str:
        return self.city or self.market_name

    def hourly(self, isco: int, paid_hours_per_month: float) -> float:
        return self.wage_usd_month[isco] / paid_hours_per_month


@dataclass(frozen=True)
class Unit:
    """A delivery model in a place. The thing an activity is assigned to."""

    model: ModelName
    location: str | None          # Location.key, or None for `automated`

    @property
    def key(self) -> str:
        return self.model if self.location is None else f"{self.model}@{self.location}"


@dataclass(frozen=True)
class Edge:
    """A directly-follows pair and how many cases took it."""

    src: str
    dst: str
    cases: int


@dataclass(frozen=True)
class Assignment:
    """A solved target operating model."""

    units: Mapping[str, Unit]           # activity name -> unit
    labour_cost: float
    handoff_cost: float
    crossings: int                      # transitions that cross a unit boundary
    status: str
    handoff_price: float
    open_sites: Sequence[str] = field(default_factory=tuple)

    @property
    def total_cost(self) -> float:
        return self.labour_cost + self.handoff_cost

    def unit_of(self, activity: str) -> Unit:
        return self.units[activity]

    def differs_from(self, other: "Assignment") -> tuple[str, ...]:
        """Activities assigned to a different unit than in `other`."""
        return tuple(
            name for name, unit in sorted(self.units.items())
            if other.units.get(name) != unit
        )


@dataclass(frozen=True)
class Instance:
    """Everything the solver needs, assembled once."""

    activities: Sequence[Activity]
    locations: Mapping[str, Location]
    edges: Sequence[Edge]
    units: Sequence[Unit]
    families: Mapping[str, Family]       # the *classifier's* labels, not gold
    settings: "Settings"
    # Representative location key -> every location the model cannot tell apart
    # from it. Solving over representatives removes a degeneracy that would
    # otherwise make the reported optimum arbitrary; the band is what gets
    # reported in its place.
    bands: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # Activity -> unit keys it may not occupy. Used to ask what the best
    # answer would be if one activity could not sit where it was put, which
    # is how a forced position is told apart from a tie-broken one.
    barred: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def assignable(self) -> Sequence[Activity]:
        return [a for a in self.activities if a.assignable]

    def band(self, location: str | None) -> tuple[str, ...]:
        """Locations indistinguishable from this one under the current config."""
        return self.bands.get(location, (location,)) if location else ()

    def by_name(self, name: str) -> Activity:
        for a in self.activities:
            if a.name == name:
                return a
        raise KeyError(name)


@dataclass(frozen=True)
class Settings:
    """config/model.yaml, resolved and typed."""

    currency: str
    period_months: int
    productive_hours_per_fte_year: float
    paid_hours_per_month: float
    delivery_models: Mapping[str, dict]
    retained_location: str
    automation: dict
    constraints: Mapping[str, dict]
    objective: dict
    baseline: dict
    stability: dict

    def enabled(self, constraint_id: str) -> bool:
        return bool(self.constraints[constraint_id]["enabled"])
