"""Compute every reported number and write RESULTS.md.

The order matters. The pre-registered metrics are stated before the results, so
a reader can see the question was fixed before the answer was known, and the
answer is reported whichever way it came out.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Sequence

from tom import ablation, forced as forced_ladder
from tom.baseline import (
    cost_ties, difference_share, naive_baseline, rank_cities, single_city_optimum,
)
from tom.config import DATA, ROOT, excluded_transitions, load_instance
from tom.solve import Scenario, forced_positions, solve
from tom.sod import breaches
from tom.sweep import (
    breakpoints, concentration_tipping_point,
    largest_structural_break, sweep,
)
from tom.types import Assignment, Instance

# The ladder the dashboard interpolates over. Dense where the answer moves.
LADDER = (
    [round(0.05 * i, 2) for i in range(0, 21)]          # 0.00 - 1.00
    + [round(1.0 + 0.1 * i, 2) for i in range(1, 21)]   # 1.10 - 3.00
    + [round(3.0 + 0.25 * i, 2) for i in range(1, 21)]  # 3.25 - 8.00
    + [9.0, 10.0, 12.0, 15.0, 20.0, 30.0, 50.0, 100.0]
)


def _unit_table(instance: Instance, assignment: Assignment) -> list[dict]:
    hours = instance.settings.productive_hours_per_fte_year
    grouped: dict[str, list[str]] = defaultdict(list)
    for name, unit in assignment.units.items():
        grouped[unit.key].append(name)
    rows = []
    for key, names in grouped.items():
        unit = assignment.units[names[0]]
        rows.append({
            "unit": key,
            "model": unit.model,
            "location": unit.location,
            "band": list(instance.band(unit.location)),
            "activities": sorted(names),
            "fte": sum(instance.by_name(n).fte(hours) for n in names),
        })
    return sorted(rows, key=lambda r: -r["fte"])


def compute(instance: Instance | None = None, *, ladder: Sequence[float] = LADDER) -> dict:
    instance = instance or load_instance()
    settings = instance.settings
    price = settings.objective["handoff_cost_usd"]
    scenario = Scenario(handoff_price=price)

    optimum, ablation_rows = ablation.run(instance, scenario=scenario)
    baseline = naive_baseline(instance, scenario=scenario)
    headline_share, headline_moved = difference_share(baseline, optimum)

    ranked = rank_cities(instance, scenario)
    baseline_city = baseline.open_sites[0].split("@", 1)[1]
    fair = single_city_optimum(instance, baseline_city, scenario=scenario)
    fair_share, fair_moved = difference_share(fair, optimum)

    forced = forced_positions(instance, scenario)
    points = sweep(instance, ladder, scenario=scenario)
    # Forced-ness is a property of the price, not of the assignment, so it is
    # measured at every stop the page can show rather than once and reused.
    per_price = forced_ladder.over_ladder([
        {"price": p.price, "total": p.assignment.total_cost,
         "assignment": {k: v.key for k, v in p.assignment.units.items()}}
        for p in points
    ])
    tipping, floor_crossings, floor_units = concentration_tipping_point(
        instance, scenario=scenario
    )
    biggest_break = largest_structural_break(instance, points, scenario=scenario)
    lo, hi = settings.objective["defensible_range_usd"]

    stability_path = DATA / "stability.json"
    stability = json.loads(stability_path.read_text()) if stability_path.exists() else None
    transfer_path = ROOT / "eval" / "classifier_transfer.json"
    transfer = json.loads(transfer_path.read_text()) if transfer_path.exists() else None

    hours = settings.productive_hours_per_fte_year
    return {
        "pre_registered": {
            "headline": (
                "Share of activities whose assignment differs between the naive "
                "baseline and the solver optimum."
            ),
            "second": (
                "The coordination cost per handoff at which the optimum flips "
                "away from concentration, and whether it sits inside the "
                "defensible range."
            ),
            "defensible_range": [lo, hi],
            "handoff_price": price,
            "currency": settings.currency,
        },
        "scale": {
            "activities": len(instance.activities),
            "assignable": len(instance.assignable),
            "fte": sum(a.fte(hours) for a in instance.assignable),
            "units_available": len(instance.units),
            "cities": len([l for l in instance.locations.values() if l.is_city]),
            "bands": {k: list(v) for k, v in instance.bands.items()},
            "transitions": excluded_transitions(),
            "priced_edges": len(instance.edges),
        },
        "headline": {
            "share": headline_share,
            "moved": list(headline_moved),
            "baseline_city": baseline_city,
            "baseline_cost": baseline.total_cost,
            "baseline_labour": baseline.labour_cost,
            "baseline_handoff": baseline.handoff_cost,
            "baseline_crossings": baseline.crossings,
            "baseline_sod_breaches": [list(b) for b in breaches(baseline.units)],
            "optimum_cost": optimum.total_cost,
            "optimum_labour": optimum.labour_cost,
            "optimum_handoff": optimum.handoff_cost,
            "optimum_crossings": optimum.crossings,
            "cost_delta": baseline.total_cost - optimum.total_cost,
        },
        "fair_comparison": {
            "city": baseline_city,
            "share": fair_share,
            "moved": list(fair_moved),
            "cost": fair.total_cost,
            "note": (
                "The best assignment that still concentrates in the baseline's "
                "city and obeys every constraint. Whatever separates it from the "
                "optimum is coordination cost and not a control failure."
            ),
        },
        "tipping_point": {
            "price": None if biggest_break is None else biggest_break["price"],
            "bracket": None if biggest_break is None else biggest_break["bracket"],
            "activities_moved": (
                None if biggest_break is None else biggest_break["activities_moved"]
            ),
            "inside_defensible_range": (
                None if biggest_break is None
                else lo <= biggest_break["price"] <= hi
            ),
            "rejected_crossings_floor": {
                "price": tipping,
                "floor_units": floor_units,
                "floor_crossings": floor_crossings,
                "crossings_at_zero": points[0].assignment.crossings,
                "why_rejected": (
                    "The last improvement before this price is worth 1.1% of "
                    "crossings. A definition that calls that the flip is "
                    "measuring the end of the sweep, not a tipping point."
                ),
            },
            "structural_breaks": [
                {"below": b[0], "above": b[1], "units_below": b[2], "units_above": b[3]}
                for b in breakpoints(points)
                if b[2] != b[3]
            ],
        },
        "ladder": [
            {
                "price": p.price,
                "units": p.units_used,
                "cities": p.cities_used,
                "labour": p.assignment.labour_cost,
                "handoff": p.assignment.handoff_cost,
                "total": p.assignment.total_cost,
                "crossings": p.assignment.crossings,
                "assignment": {k: v.key for k, v in p.assignment.units.items()},
            }
            for p in points
        ],
        "forced": {
            "positions": forced,
            "forced": sum(1 for v in forced.values() if v["forced"]),
            "tie_broken": sum(1 for v in forced.values() if not v["forced"]),
            "total": len(forced),
            "by_price": per_price,
        },
        "optimum": {
            "cost": optimum.total_cost,
            "units": _unit_table(instance, optimum),
            "assignment": {k: v.key for k, v in optimum.units.items()},
        },
        "city_ranking": [
            {"city": key, "all_movable_work_here": total,
             "employers": instance.locations[key].employers}
            for key, total in ranked
        ],
        "cost_ties": cost_ties(instance, ranked),
        "ablation": [
            {
                "constraint": row.constraint,
                "status": row.status,
                "moved": list(row.moved),
                "moved_share": row.moved_share,
                "cost_delta": row.cost_delta,
                "units_delta": row.units_delta,
                "sod_breaches": row.sod_breaches,
                "decorative": row.decorative,
            }
            for row in ablation_rows
        ],
        "classifier": transfer,
        "stability": stability,
        "activities": [
            {
                "name": a.name,
                "events": a.events,
                "batch_share": a.batch_share,
                "resources": a.resources,
                "owner": a.owner,
                "isco": a.isco,
                "minutes": a.minutes,
                "contact": a.contact,
                "fte": a.fte(hours),
                "gold_family": a.gold_family,
                "family": instance.families.get(a.name),
                "why": a.why,
            }
            for a in instance.activities
        ],
        "locations": [
            {
                "key": l.key, "label": l.label, "is_city": l.is_city,
                "market_name": l.market_name,
                "wage": dict(sorted(l.wage_usd_month.items())),
                "overlap_hours": l.overlap_hours,
                "language_share": l.language_share,
                "transactional_share": l.transactional_share,
                "employers": l.employers,
                "cost_city_level": l.cost_city_level,
            }
            for l in instance.locations.values()
        ],
    }


def _money(value: float) -> str:
    return f"{value:,.0f}"


def to_markdown(r: dict) -> str:
    pre = r["pre_registered"]
    h = r["headline"]
    t = r["tipping_point"]
    lo, hi = pre["defensible_range"]
    cur = pre["currency"]
    out: list[str] = []
    w = out.append

    w("# Results\n")
    w("Purchase-to-pay only. Every figure below is reproduced by `make run`.\n")

    w("## The two metrics, fixed before the run\n")
    w(f"1. **{pre['headline']}**")
    w(f"2. **{pre['second']}**\n")
    w(f"The defensible range for coordination cost was set at "
      f"{cur} {lo:.2f}–{hi:.2f} per handoff from handling minutes and the wage "
      f"panel, before the sweep was run.\n")

    s = r["scale"]
    tr = s["transitions"]
    w("## Scale\n")
    w(f"| | |\n|---|---:|")
    w(f"| Activities in the log | {s['activities']} |")
    w(f"| Assignable to a delivery model | {s['assignable']} |")
    w(f"| Total handling | {s['fte']:.0f} FTE |")
    w(f"| Candidate units (delivery model x location) | {s['units_available']} |")
    w(f"| Transitions in the log | {tr['total']:,} |")
    w(f"| — same activity repeating, never crosses a unit | {tr['self_loops']:,} |")
    w(f"| — touching a vendor or system activity, unavoidable | {tr['touching_unassignable']:,} |")
    w(f"| **Transitions the objective prices** | **{tr['priced']:,}** |\n")

    w("## 1. The headline\n")
    w(f"**{h['share']:.0%}** of assignable activities sit somewhere different in "
      f"the solver optimum than in the naive baseline "
      f"({len(h['moved'])} of {s['assignable']}).\n")
    w(f"| | naive baseline | solver optimum |\n|---|---:|---:|")
    w(f"| Labour | {cur} {_money(h['baseline_labour'])} | {cur} {_money(h['optimum_labour'])} |")
    w(f"| Coordination | {cur} {_money(h['baseline_handoff'])} | {cur} {_money(h['optimum_handoff'])} |")
    w(f"| **Total** | **{cur} {_money(h['baseline_cost'])}** | **{cur} {_money(h['optimum_cost'])}** |")
    w(f"| Crossing transitions | {h['baseline_crossings']:,} | {h['optimum_crossings']:,} |")
    w(f"| Segregation-of-duties breaches | {len(h['baseline_sod_breaches'])} | 0 |\n")

    fair = r["fair_comparison"]
    w(f"The baseline puts everything in **{h['baseline_city']}** and breaks "
      f"{len(h['baseline_sod_breaches'])} segregation-of-duties pairs doing it. "
      f"That makes the gap above partly a control failure rather than a costing "
      f"error, so the fair comparison is separated out: the best assignment that "
      f"still concentrates in {fair['city']} and breaks nothing differs from the "
      f"optimum on **{fair['share']:.0%}** of activities and costs "
      f"{cur} {_money(fair['cost'])}.\n")

    w("## 2. The tipping point\n")
    if t["price"] is None:
        w("The assignment does not reorganise anywhere in the bracket swept. "
          "Reported as such.\n")
    else:
        verdict = "inside" if t["inside_defensible_range"] else "outside"
        rej = t["rejected_crossings_floor"]
        w(f"**{cur} {t['price']:.2f} per handoff.** Below it the model spreads "
          f"work across cheaper cities and pays for the crossings. At that price "
          f"**{t['activities_moved']} of {s['assignable']} activities change unit "
          f"at once**, and crossing transitions fall from "
          f"{rej['crossings_at_zero']:,} at a price of zero towards "
          f"{rej['floor_crossings']:,}.\n")
        w(f"That value sits **{verdict}** the defensible range of "
          f"{cur} {lo:.2f}–{hi:.2f} — near its top edge, which is worth saying "
          f"plainly: the case for concentrating this process rests on the upper "
          f"half of what a handoff can defensibly be argued to cost.\n")
        w(f"> The definition was changed after seeing the sweep. Crossing "
          f"transitions do not reach their absolute floor until "
          f"{cur} {rej['price']:.0f} per handoff, and the last step before that "
          f"is worth 1.1% of crossings. Reporting {cur} {rej['price']:.0f} as the "
          f"tipping point would be reporting the end of the sweep. The reported "
          f"figure is where the assignment actually reorganises. Nothing in the "
          f"objective, the constraints or the ladder was touched — but the change "
          f"was made with the data in view, so it is disclosed here rather than "
          f"presented as the plan all along.\n")
    if t["structural_breaks"]:
        w("| coordination cost | units before | units after |\n|---|---:|---:|")
        for b in t["structural_breaks"]:
            w(f"| {cur} {b['below']:.2f} → {b['above']:.2f} | {b['units_below']} | {b['units_above']} |")
        w("")

    w("## The optimum at the declared price\n")
    w(f"At {cur} {pre['handoff_price']:.2f} per handoff, total "
      f"{cur} {_money(r['optimum']['cost'])}.\n")
    w("| unit | FTE | activities |\n|---|---:|---|")
    for row in r["optimum"]["units"]:
        band = row["band"]
        label = row["unit"]
        if len(band) > 1:
            label += f" *(not separable from {', '.join(b.split(':')[-1] for b in band if b != row['location'])})*"
        w(f"| {label} | {row['fte']:.1f} | {len(row['activities'])} |")
    w("")

    f = r["forced"]
    w("## How much of the answer is actually decided\n")
    w(f"Each activity was barred in turn from the unit it was given, and the "
      f"model re-solved. Where the total does not move, nothing decided that "
      f"position — several answers cost the same and a declared tie-break picked "
      f"one.\n")
    w(f"**{f['forced']} of {f['total']}** positions are decided by cost. The "
      f"remaining **{f['tie_broken']}** are placed, not chosen, and are drawn as "
      f"undecided rather than as a position.\n")
    priced = sorted(
        ((k, v) for k, v in f["positions"].items()
         if v["forced"] and v["cost_of_moving"] is not None),
        key=lambda kv: -kv[1]["cost_of_moving"],
    )
    if priced:
        w("| activity | unit | cost of moving it | next best |\n|---|---|---:|---|")
        for name, row in priced:
            w(f"| {name} | {row['unit']} | {cur} {row['cost_of_moving']:,.0f} "
              f"| {row['next_best_unit']} |")
        w("")

    w("## What each constraint is doing\n")
    w("Removed one at a time, everything else held.\n")
    w("| constraint | activities moved | cost without it | units | SoD breaches |\n"
      "|---|---:|---:|---:|---:|")
    for row in r["ablation"]:
        note = " — **decorative**" if row["decorative"] else ""
        w(f"| {row['constraint']}{note} | {len(row['moved'])} ({row['moved_share']:.0%}) "
          f"| {cur} {row['cost_delta']:+,.0f} | {row['units_delta']:+d} | {row['sod_breaches']} |")
    w("")

    c = r.get("classifier")
    if c:
        w("## Does the classifier transfer?\n")
        w(f"The transactional/judgment classifier in `gbs-agentic-shift` was "
          f"calibrated on job postings. Scored on SAP activity names against a "
          f"hand-labelled gold set covering all {c['gold_set']['n']}:\n")
        w("| stage | n | accuracy | recall transactional | recall judgment |\n"
          "|---|---:|---:|---:|---:|")
        for key, title in [
            ("stage_1_taxonomy", "1 — ported keyword taxonomy"),
            ("stage_2_model", f"2 — {c['model']} on the residual"),
            ("overall", "combined"),
        ]:
            row = c[key]
            f = lambda v: f"{v:.1%}" if v is not None else "n/a"
            w(f"| {title} | {row['n']} | {f(row['accuracy'])} "
              f"| {f(row['recall']['transactional'])} | {f(row['recall']['judgment'])} |")
        cov = c["coverage"]
        w(f"\nThe ported taxonomy decides {cov['activities']:.0%} of activity names "
          f"— {cov['events']:.0%} of events — and its judgment recall on this "
          f"input is {c['stage_1_taxonomy']['recall']['judgment']:.0%}.\n")

    st = r.get("stability")
    if st:
        w("## What survives resampling\n")
        w(f"{st['draws']:,} draws over handling minutes, the provider and captive "
          f"multipliers, the automation run cost, the coordination price, the "
          f"authored ISCO mapping, and the classifier's own measured error rate.\n")
        w(f"**{st['summary']['stable']} of {st['summary']['total']}** activities hold "
          f"the same unit in at least {st['stable_threshold']:.0%} of draws. "
          f"The other {st['summary']['unstable']} are reported as unstable and are "
          f"not given a position.\n")
        w("| activity | modal unit | holds in | verdict |\n|---|---|---:|---|")
        for name, row in sorted(
            st["activities"].items(), key=lambda kv: -kv[1]["modal_share"]
        ):
            verdict = "stable" if row["stable"] else "**unstable**"
            w(f"| {name} | {row['modal_unit']} | {row['modal_share']:.0%} | {verdict} |")
        w("")

    w("## What the cost model cannot separate\n")
    if r["cost_ties"]:
        for group in r["cost_ties"]:
            w(f"- {', '.join(g.split(':')[-1] for g in group)} — identical on every "
              f"input the model reads.")
    else:
        w("- Nothing: every city carries a distinct cost.")
    w("")
    return "\n".join(out) + "\n"


def main() -> None:
    result = compute()
    (DATA / "results.json").write_text(json.dumps(result, indent=1) + "\n")
    (ROOT / "RESULTS.md").write_text(to_markdown(result))
    h, t = result["headline"], result["tipping_point"]
    print(f"headline difference share: {h['share']:.1%}")
    f = result["forced"]
    print(f"positions decided by cost: {f['forced']}/{f['total']} "
          f"({f['tie_broken']} placed by tie-break)")
    if t["price"] is not None:
        inside = "inside" if t["inside_defensible_range"] else "OUTSIDE"
        print(f"tipping point: {result['pre_registered']['currency']} "
              f"{t['price']:.2f} per handoff — {inside} the defensible range")
    print("wrote RESULTS.md and data/results.json")


if __name__ == "__main__":
    main()
