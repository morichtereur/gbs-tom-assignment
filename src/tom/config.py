"""Load the configs and the input snapshot into one typed `Instance`.

Nothing in this module decides anything. It reads `config/*.yaml` and
`data/*.json` and hands the solver a fully-resolved instance, so that swapping
in a second process scope is a matter of pointing `PATHS` somewhere else rather
than editing the solver.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from tom.types import Activity, Edge, Family, Instance, Location, Settings, Unit

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"

ISCO_KEYS = {"OCU_ISCO08_2": 2, "OCU_ISCO08_3": 3, "OCU_ISCO08_4": 4}


def _yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text())


def _json(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Run `make snapshot` to pull it from the "
            f"upstream repositories."
        )
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    raw = _yaml("model.yaml")
    return Settings(
        currency=raw["currency"],
        period_months=raw["scope"]["period_months"],
        productive_hours_per_fte_year=raw["scope"]["productive_hours_per_fte_year"],
        paid_hours_per_month=raw["scope"]["paid_hours_per_month"],
        delivery_models=raw["delivery_models"],
        retained_location=raw["retained_location"],
        automation=raw["automation"],
        constraints=_constraints(raw["constraints"]),
        objective=raw["objective"],
        baseline=raw["baseline"],
        stability=raw["stability"],
    )


def _constraints(rows: list[dict]) -> dict[str, dict]:
    """Index the constraints, refusing any that does not declare `enabled`.

    A missing flag used to default to off, which meant a typo switched a
    control constraint off and the model still returned a confident answer.
    """
    out = {}
    for row in rows:
        if "enabled" not in row:
            raise ValueError(
                f"constraint {row.get('id')!r} declares no `enabled` flag. "
                f"Note that YAML reads a bare `on:` key as the boolean True."
            )
        out[row["id"]] = row
    return out


def _activities(settings: Settings) -> list[Activity]:
    declared = {a["name"]: a for a in _yaml("activities.yaml")["activities"]}
    process = _json("process.json")

    measured = {a["name"] for a in process["activities"]}
    missing = measured - set(declared)
    extra = set(declared) - measured
    if missing or extra:
        raise ValueError(
            "config/activities.yaml does not match the log. "
            f"Missing: {sorted(missing)}. Not in the log: {sorted(extra)}. "
            "Every activity needs a declared mapping — a silent default here "
            "would be exactly the kind of unstated judgement this study exists "
            "to expose."
        )

    out = []
    for row in process["activities"]:
        d = declared[row["name"]]
        out.append(Activity(
            name=row["name"],
            events=row["events"],
            cases=row["cases"],
            batch_share=row["batch_share"],
            resources=row["resources"],
            owner=d["owner"],
            isco=int(d["isco"]),
            minutes=float(d["minutes"]),
            contact=bool(d["contact"]),
            why=d["why"],
            gold_family=d["family"],
        ))
    return out


def _locations() -> dict[str, Location]:
    raw = _json("locations.json")
    out = {}
    for row in raw["locations"]:
        wages = {
            ISCO_KEYS[k]: v
            for k, v in (row["wage_components_usd"] or {}).items()
            if k in ISCO_KEYS
        }
        if len(wages) != 3:
            # A location without all three ISCO lines cannot be costed for an
            # arbitrary activity mix, and filling the gap is the failure mode
            # the upstream study documents. Dropped rather than imputed.
            continue
        out[row["key"]] = Location(
            key=row["key"],
            city=row["city"],
            market=row["market"],
            market_name=row["market_name"],
            market_type=row["market_type"],
            is_city=row["is_city"],
            wage_usd_month=wages,
            cost_city_level=bool(row["cost_city_level"]),
            overlap_hours=float(row["timezone_overlap_hours"] or 0.0),
            governance=row["governance"],
            employers=row["employers"],
            language_share=float(row["language_share"] or 0.0),
            transactional_share=row["transactional_share"],
        )
    return out


def equivalence_classes(
    locations: Mapping[str, Location], settings: Settings
) -> dict[str, tuple[str, ...]]:
    """Group cities the model reads identically.

    The model reads a location through exactly four things: its three ISCO wage
    lines, its overlap with the headquarters, whether it clears the contact
    constraint, and whether its measured posting mix makes it a transactional
    hub. Two cities equal on all four are interchangeable — not approximately,
    exactly — and the upstream panel produces several, because India has no
    city-level wage in any reachable source.

    Solving over one representative per class is therefore lossless. What it
    buys is that the answer stops depending on which member CP-SAT happened to
    pick, and the tie gets reported as a band instead of as a position.

    The classes depend on the thresholds, so they are recomputed rather than
    hard-coded: switch the contact constraint off in the ablation and the
    classes change with it.
    """
    contact = settings.constraints["contact_coverage"]
    hub_at = settings.constraints["judgment_cap"]["hub_transactional_threshold"]

    def signature(loc: Location) -> tuple:
        return (
            tuple(sorted(loc.wage_usd_month.items())),
            loc.overlap_hours,
            loc.overlap_hours >= contact["min_overlap_hours"]
            and loc.language_share >= contact["min_language_share"],
            (loc.transactional_share or 0.0) >= hub_at,
        )

    grouped: dict[tuple, list[str]] = {}
    for key, loc in locations.items():
        if loc.is_city:
            grouped.setdefault(signature(loc), []).append(key)

    classes = {}
    for members in grouped.values():
        # The representative is the member with the most distinct employers —
        # the only field left that separates them, and the one a programme would
        # actually pick on. Recorded as a tie-break, not as a ranking.
        rep = sorted(members, key=lambda k: (-(locations[k].employers or 0), k))[0]
        classes[rep] = tuple(sorted(members))
    return classes


def _units(
    locations: Mapping[str, Location],
    settings: Settings,
    cities: Sequence[str] | None = None,
) -> list[Unit]:
    """Every (delivery model, location) pair the configuration permits."""
    if cities is None:
        cities = [k for k, loc in locations.items() if loc.is_city]
    units: list[Unit] = []
    for name, spec in settings.delivery_models.items():
        scope = spec["locations"]
        if scope == "none":
            units.append(Unit(name, None))
        elif scope == "hq":
            anchor = settings.retained_location
            if anchor not in locations:
                raise ValueError(
                    f"retained_location {anchor!r} is not in the location panel."
                )
            units.append(Unit(name, anchor))
        elif scope == "city":
            units.extend(Unit(name, c) for c in sorted(cities))
        else:
            raise ValueError(f"delivery model {name!r} has unknown scope {scope!r}")
    return units


def load_families(fallback_to_gold: bool = True) -> dict[str, Family]:
    """The classifier's labels — what the model actually runs on.

    `data/labels.json` is written by `tom.classify`. Where it has not been run,
    the gold labels stand in so the solver is still usable, and every entry
    point that reports a headline says which of the two it used.
    """
    path = DATA / "labels.json"
    if path.exists():
        return {k: v["label"] for k, v in json.loads(path.read_text())["labels"].items()}
    if not fallback_to_gold:
        raise FileNotFoundError(f"{path} is missing. Run `make classify`.")
    return {a["name"]: a["family"] for a in _yaml("activities.yaml")["activities"]}


def load_instance(
    families: Mapping[str, Family] | None = None, *, collapse: bool = True
) -> Instance:
    settings = load_settings()
    activities = _activities(settings)
    locations = _locations()
    process = _json("process.json")

    assignable = {a.name for a in activities if a.assignable}
    obj = settings.objective
    edges = [
        Edge(e["from"], e["to"], e["cases"])
        for e in process["edges"]
        if not (obj["exclude_self_loops"] and e["from"] == e["to"])
        and not (
            obj["exclude_unassignable"]
            and (e["from"] not in assignable or e["to"] not in assignable)
        )
    ]

    bands = equivalence_classes(locations, settings) if collapse else {
        k: (k,) for k, loc in locations.items() if loc.is_city
    }

    return Instance(
        activities=activities,
        locations=locations,
        edges=edges,
        units=_units(locations, settings, sorted(bands)),
        families=dict(families or load_families()),
        settings=settings,
        bands=bands,
    )


def excluded_transitions() -> dict[str, int]:
    """What the objective drops, so the reported total means what it says."""
    process = _json("process.json")
    settings = load_settings()
    assignable = {a.name for a in _activities(settings) if a.assignable}
    self_loops = sum(e["cases"] for e in process["edges"] if e["from"] == e["to"])
    unassignable = sum(
        e["cases"] for e in process["edges"]
        if e["from"] != e["to"]
        and (e["from"] not in assignable or e["to"] not in assignable)
    )
    total = process["transitions"]
    return {
        "total": total,
        "self_loops": self_loops,
        "touching_unassignable": unassignable,
        "priced": total - self_loops - unassignable,
    }
