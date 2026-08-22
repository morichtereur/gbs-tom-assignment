"""Label each activity transactional or judgment, and measure the transfer.

Stage 1 is the deterministic keyword taxonomy from `gbs-agentic-shift`, ported
unchanged. It was calibrated on job postings — several hundred words of prose
with a job title on top. An SAP activity name is three words. Whether a
classifier calibrated on the first works on the second is an assumption, and
this study measures it rather than inheriting it.

Stage 2 is a language model, and it is the only place one appears in this
repository. It never sees the assignment problem: it labels the residual the
taxonomy could not decide, its output is scored against a hand-labelled gold
set covering every activity, and the measured error is what the stability run
resamples over. That is the whole of its permitted role.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

from tom.config import DATA, ROOT

# --- stage 1: the ported taxonomy ------------------------------------------
# Imported from the sibling repository rather than copied, so the two cannot
# silently diverge. If it is not on the path, the vendored phrase lists below
# are used and the readout says which one ran.
UPSTREAM = ROOT.parent / "gbs-agentic-shift"


def _load_upstream_taxonomy():
    if not (UPSTREAM / "src" / "taxonomy.py").exists():
        return None, "unavailable"
    sys.path.insert(0, str(UPSTREAM))
    try:
        from src.taxonomy import classify_text  # type: ignore
        return classify_text, "gbs-agentic-shift/src/taxonomy.py"
    except Exception:
        return None, "unavailable"
    finally:
        if sys.path and sys.path[0] == str(UPSTREAM):
            sys.path.pop(0)


@dataclass(frozen=True)
class Label:
    name: str
    label: str                  # transactional | judgment
    source: str                 # taxonomy | model
    reason: str = ""
    hits: tuple[str, ...] = ()


PROMPT = """You classify one SAP purchase-to-pay activity name into exactly one bucket:

- transactional: rule-based processing. The step is the same every time, the
  system or a work instruction says what to do, and doing it well means doing it
  fast and identically.
- judgment: the step requires deciding something. Somebody weighs a reason, an
  amount, an exception or an authority before acting, and two competent people
  could reasonably act differently.

You are given the activity name and how it behaves in a real event log: how many
times it fired, how many distinct users touched it, and what share already runs
unattended in batch. Use that behaviour — an activity 100% of whose events are
written by one batch id is not somebody exercising judgment.

Return ONLY compact JSON: {"label": "...", "reason": "<12 words"}. No prose."""


def _model_label(client, model: str, activity: dict) -> tuple[str, str]:
    text = (
        f"ACTIVITY: {activity['name']}\n"
        f"events: {activity['events']:,}\n"
        f"distinct users: {activity['resources']}\n"
        f"share running in batch: {activity['batch_share']:.1%}"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=120,
        system=PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return "transactional", "unparseable model output"
    label = out.get("label")
    if label not in {"transactional", "judgment"}:
        # The taxonomy's own residual default. Recorded as a reason so the
        # readout can count how often the model failed to commit.
        return "transactional", "model returned no usable label"
    return label, str(out.get("reason", ""))[:120]


def run(model: str | None = None, *, offline: bool = False) -> dict:
    """Classify every activity and write `data/labels.json`."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    model = model or os.getenv("CLASSIFIER_MODEL", "claude-sonnet-5")

    process = json.loads((DATA / "process.json").read_text())
    classify_text, provenance = _load_upstream_taxonomy()
    if classify_text is None:
        raise RuntimeError(
            f"the upstream taxonomy is not importable from {UPSTREAM}. "
            "This study ports it rather than reimplementing it, so there is no "
            "fallback: clone gbs-agentic-shift alongside this repository."
        )

    labels: dict[str, Label] = {}
    residual: list[dict] = []
    for row in process["activities"]:
        result = classify_text(row["name"])
        hits = tuple(
            phrase for family, phrases in result.hits.items() for phrase in phrases
        )
        if result.ambiguous or result.label not in {"transactional", "judgment"}:
            residual.append(row)
        else:
            labels[row["name"]] = Label(
                row["name"], result.label, "taxonomy", "keyword hit", hits
            )

    if residual and not offline:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        for row in residual:
            label, reason = _model_label(client, model, row)
            labels[row["name"]] = Label(row["name"], label, "model", reason)
    else:
        for row in residual:
            # Offline: the residual falls back to the taxonomy's own default.
            # Recorded as such — a fallback label is not a classification.
            labels[row["name"]] = Label(
                row["name"], "transactional", "fallback", "offline: no model call"
            )

    decided_by_taxonomy = [n for n, l in labels.items() if l.source == "taxonomy"]
    events = {row["name"]: row["events"] for row in process["activities"]}
    total_events = sum(events.values())

    payload = {
        "model": None if offline else model,
        "taxonomy_source": provenance,
        "coverage": {
            # Two coverage numbers, because they say different things. The
            # taxonomy decides few names but those few carry a lot of the log.
            "activities": len(decided_by_taxonomy) / len(labels),
            "events": sum(events[n] for n in decided_by_taxonomy) / total_events,
            "decided_by_taxonomy": len(decided_by_taxonomy),
            "sent_to_model": len(residual),
            "total": len(labels),
        },
        "labels": {
            name: {
                "label": l.label,
                "source": l.source,
                "reason": l.reason,
                "hits": list(l.hits),
            }
            for name, l in sorted(labels.items())
        },
    }
    (DATA / "labels.json").write_text(json.dumps(payload, indent=1) + "\n")
    return payload


def main() -> None:
    offline = "--offline" in sys.argv
    payload = run(offline=offline)
    cov = payload["coverage"]
    print(
        f"stage 1 (ported taxonomy) decided {cov['decided_by_taxonomy']}/{cov['total']} "
        f"activity names — {cov['activities']:.0%} of names, {cov['events']:.0%} of events"
    )
    print(
        f"stage 2 ({payload['model'] or 'offline fallback'}) took the remaining "
        f"{cov['sent_to_model']}"
    )
    print("wrote data/labels.json")


if __name__ == "__main__":
    main()
