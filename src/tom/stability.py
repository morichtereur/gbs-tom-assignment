"""Resample everything this study declared, 10,000 times.

Five quantities carry the answer and none of them is a measurement:

  handling minutes      authored per activity, +/- 30%
  provider multiplier   the whole difference between a wage and a billed rate
  captive multiplier    employer cost on top of a wage
  automation run cost   licence and support per thousand events
  coordination price    the control the reader drags

and two mappings this study authored on top of somebody else's measurement:

  activity -> ISCO group     validation item 2 of the brief
  activity -> work family    resampled at the classifier's *measured* error
                             rate, not at an assumed one

An activity whose unit holds in fewer than the configured share of draws is
reported as unstable. It is not given a position, because the honest answer to
"where does this go" is that the evidence does not say.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from dataclasses import dataclass
from random import Random
from typing import Mapping

from tom.config import DATA, ROOT, load_instance
from tom.solve import Infeasible, Scenario, solve
from tom.types import Instance

_WORKER: dict[str, Instance] = {}


@dataclass(frozen=True)
class Draw:
    index: int
    scenario: Scenario


def _classifier_error() -> dict[str, float]:
    """Per-class error rates, read from the eval rather than assumed."""
    path = ROOT / "eval" / "classifier_transfer.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Run `make eval` first — the stability run "
            "resamples labels at the classifier's measured error rate, and "
            "without the measurement there is no rate to resample at."
        )
    report = json.loads(path.read_text())
    rates = report["overall"]["error_rate"]
    return {k: (v if v is not None else 0.0) for k, v in rates.items()}


def draw(instance: Instance, rng: Random, error_rates: Mapping[str, float]) -> Scenario:
    s = instance.settings
    jitter = s.stability["jitter"]
    base_price = s.objective["handoff_cost_usd"]

    def wobble(value: float, span: float) -> float:
        return value * (1.0 + rng.uniform(-span, span))

    minutes = {
        a.name: wobble(a.minutes, jitter["handling_minutes"])
        for a in instance.assignable
        if a.minutes > 0
    }

    # The ISCO mapping is authored, so it is resampled across the neighbouring
    # group rather than held fixed. Groups 2 and 4 can only move inward; group 3
    # can move either way. A quarter of activities move in a draw.
    isco = {}
    for a in instance.assignable:
        if rng.random() >= 0.25:
            continue
        options = {2: [3], 3: [2, 4], 4: [3]}[a.isco]
        isco[a.name] = rng.choice(options)

    # Labels flip at the rate the gold set measured for their class, which is
    # the difference between modelling the classifier's error and asserting it
    # away.
    families = {}
    for name, label in instance.families.items():
        if rng.random() < error_rates.get(label, 0.0):
            families[name] = "judgment" if label == "transactional" else "transactional"

    return Scenario(
        handoff_price=max(0.0, wobble(base_price, jitter["handoff_cost"])),
        minutes=minutes,
        wage_multiplier={
            "provider": wobble(
                s.delivery_models["provider"]["wage_multiplier"],
                jitter["provider_multiplier"],
            ),
            "captive": wobble(
                s.delivery_models["captive"]["wage_multiplier"],
                jitter["captive_multiplier"],
            ),
        },
        automation_cost_per_1k=max(
            0.0,
            wobble(s.automation["cost_per_1k_events_usd"], jitter["automation_cost"]),
        ),
        isco=isco,
        families=families,
    )


def _init_worker() -> None:
    _WORKER["instance"] = load_instance()


def _run_draw(payload: tuple[int, int]) -> dict[str, str] | None:
    index, seed = payload
    instance = _WORKER["instance"]
    rng = Random(seed)
    scenario = draw(instance, rng, _WORKER["error_rates"])
    try:
        result = solve(instance, scenario=scenario, time_limit_s=20.0)
    except Infeasible:
        return None
    return {name: unit.key for name, unit in result.units.items()}


def _init_worker_with(error_rates: dict[str, float]) -> None:
    _WORKER["instance"] = load_instance()
    _WORKER["error_rates"] = error_rates


def run(
    draws: int | None = None,
    *,
    workers: int | None = None,
    progress: bool = True,
) -> dict:
    instance = load_instance()
    settings = instance.settings
    draws = draws or settings.stability["draws"]
    seed = settings.stability["seed"]
    workers = workers or max(1, (os.cpu_count() or 4) - 1)
    error_rates = _classifier_error()

    rng = Random(seed)
    seeds = [(i, rng.getrandbits(32)) for i in range(draws)]

    tally: dict[str, Counter] = defaultdict(Counter)
    infeasible = 0
    done = 0
    try:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker_with, initargs=(error_rates,)
        ) as pool:
            for outcome in pool.map(_run_draw, seeds, chunksize=16):
                done += 1
                if outcome is None:
                    infeasible += 1
                else:
                    for name, unit in outcome.items():
                        tally[name][unit] += 1
                if progress and done % max(1, draws // 20) == 0:
                    print(f"  {done:>6,}/{draws:,}", flush=True)
    except BrokenExecutor as exc:
        # A worker pool that dies mid-run leaves the parent waiting on results
        # that will never arrive, and the run looks like it is still going. Fail
        # loudly and say how far it got, rather than writing a file that claims
        # a draw count it did not reach.
        raise RuntimeError(
            f"the worker pool died after {done:,} of {draws:,} draws ({exc}). "
            f"No stability file was written. Re-run, or lower `workers`."
        ) from exc

    threshold = settings.stability["stable_threshold"]
    activities = {}
    for name, counts in sorted(tally.items()):
        total = sum(counts.values())
        top, hits = counts.most_common(1)[0]
        activities[name] = {
            "modal_unit": top,
            "modal_share": hits / total,
            "stable": (hits / total) >= threshold,
            "distribution": {k: v / total for k, v in counts.most_common()},
            "draws": total,
        }

    payload = {
        "draws": draws,
        "seed": seed,
        "infeasible_draws": infeasible,
        "stable_threshold": threshold,
        "classifier_error_rate": error_rates,
        "bands": {k: list(v) for k, v in instance.bands.items()},
        "activities": activities,
        "summary": {
            "stable": sum(1 for a in activities.values() if a["stable"]),
            "unstable": sum(1 for a in activities.values() if not a["stable"]),
            "total": len(activities),
        },
    }
    (DATA / "stability.json").write_text(json.dumps(payload, indent=1) + "\n")
    return payload


def main() -> None:
    import sys

    draws = int(sys.argv[1]) if len(sys.argv) > 1 else None
    payload = run(draws)
    s = payload["summary"]
    print(
        f"\n{payload['draws']:,} draws — {s['stable']} of {s['total']} activities "
        f"stable at {payload['stable_threshold']:.0%}, {s['unstable']} unstable, "
        f"{payload['infeasible_draws']} infeasible"
    )
    print("wrote data/stability.json")


if __name__ == "__main__":
    main()
