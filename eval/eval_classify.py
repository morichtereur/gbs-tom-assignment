"""Score the classifier against the hand-labelled gold set.

The gold labels are the `family` field in `config/activities.yaml`, one per
activity, covering all 42 rather than a sample — the population is small enough
that sampling would only add noise. They are authored, not independently
ground-truthed, which is stated plainly because it bounds what this measurement
can claim: it measures agreement with one careful reading of what each activity
is, not with an external truth.

What comes out of here is used twice. Once as a reported number, and once as
the confusion matrix the stability run resamples labels over — so a classifier
that is 80% right does not silently enter the model as one that is 100% right.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from tom.config import CONFIG, DATA  # noqa: E402

CLASSES = ("transactional", "judgment")


def gold() -> dict[str, str]:
    raw = yaml.safe_load((CONFIG / "activities.yaml").read_text())
    return {a["name"]: a["family"] for a in raw["activities"]}


def score(labels: dict, truth: dict[str, str], subset: set[str] | None = None) -> dict:
    names = sorted(set(labels) & set(truth) & (subset if subset is not None else set(truth)))
    confusion = Counter(
        (truth[n], labels[n]["label"]) for n in names
    )
    correct = sum(v for (t, p), v in confusion.items() if t == p)
    recall, precision = {}, {}
    for cls in CLASSES:
        actual = sum(v for (t, _), v in confusion.items() if t == cls)
        predicted = sum(v for (_, p), v in confusion.items() if p == cls)
        hit = confusion.get((cls, cls), 0)
        recall[cls] = hit / actual if actual else None
        precision[cls] = hit / predicted if predicted else None
    return {
        "n": len(names),
        "accuracy": correct / len(names) if names else None,
        "recall": recall,
        "precision": precision,
        # Row-normalised: P(predicted | actual). This is what the stability run
        # samples from, so it is stored rather than recomputed there.
        "confusion": {
            f"{t}->{p}": v for (t, p), v in sorted(confusion.items())
        },
        "error_rate": {
            cls: (
                1 - recall[cls] if recall[cls] is not None else None
            )
            for cls in CLASSES
        },
    }


def main() -> None:
    payload = json.loads((DATA / "labels.json").read_text())
    labels = payload["labels"]
    truth = gold()

    by_stage = {
        "taxonomy": {n for n, l in labels.items() if l["source"] == "taxonomy"},
        "model": {n for n, l in labels.items() if l["source"] == "model"},
    }

    report = {
        "model": payload["model"],
        "gold_set": {
            "n": len(truth),
            "authored": True,
            "note": (
                "Hand-labelled by the author across all 42 activities. Agreement "
                "with one careful reading, not with an external ground truth."
            ),
        },
        "coverage": payload["coverage"],
        "overall": score(labels, truth),
        "stage_1_taxonomy": score(labels, truth, by_stage["taxonomy"]),
        "stage_2_model": score(labels, truth, by_stage["model"]),
        "disagreements": [
            {
                "activity": n,
                "gold": truth[n],
                "predicted": labels[n]["label"],
                "source": labels[n]["source"],
                "reason": labels[n]["reason"],
            }
            for n in sorted(labels)
            if n in truth and labels[n]["label"] != truth[n]
        ],
    }
    out = ROOT / "eval" / "classifier_transfer.json"
    out.write_text(json.dumps(report, indent=1) + "\n")

    cov = payload["coverage"]
    print(f"gold set: {report['gold_set']['n']} activities, hand-labelled, authored\n")
    print(f"{'stage':<24s} {'n':>4s} {'accuracy':>9s} "
          f"{'recall(trans)':>14s} {'recall(judg)':>13s}")
    for key, title in [
        ("stage_1_taxonomy", "1 ported taxonomy"),
        ("stage_2_model", f"2 {payload['model']}"),
        ("overall", "combined"),
    ]:
        r = report[key]
        fmt = lambda v: f"{v:.1%}" if v is not None else "     n/a"
        print(f"{title:<24s} {r['n']:>4d} {fmt(r['accuracy']):>9s} "
              f"{fmt(r['recall']['transactional']):>14s} {fmt(r['recall']['judgment']):>13s}")
    print(f"\ntaxonomy coverage: {cov['activities']:.0%} of names, {cov['events']:.0%} of events")
    print(f"disagreements with gold: {len(report['disagreements'])}")
    for d in report["disagreements"]:
        print(f"  {d['activity']:<40s} gold={d['gold']:<14s} "
              f"got={d['predicted']:<14s} ({d['source']}) {d['reason']}")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
