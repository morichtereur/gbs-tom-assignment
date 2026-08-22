"""Run inside p2p-process-mining's virtualenv, from its repo root.

Emits the activity set and the directly-follows graph as JSON on stdout.
Directly-follows pairs come from `variants.parquet` — the distinct end-to-end
paths cases actually took — not from the event table and not from any
documented process flow. That substitution is what the downstream study rests
on, so it happens here, in eleven lines a reader can check.
"""

import json
from collections import Counter

import duckdb

ACTIVITY_META = """
    select activity,
           count(*)                                                as events,
           count(distinct case_id)                                 as cases,
           sum(case when resource like 'batch%' then 1 else 0 end) as batch_events,
           count(distinct resource)                                as resources
    from 'data/events.parquet'
    group by 1
"""

con = duckdb.connect()
variants = con.execute(
    "select variant, n_cases from 'output/variants.parquet'"
).fetchall()

follows: Counter = Counter()
occurrences: Counter = Counter()
cases = 0
for variant, n in variants:
    cases += n
    seq = variant.split(" -> ")
    for act in seq:
        occurrences[act] += n
    for a, b in zip(seq, seq[1:]):
        follows[(a, b)] += n

meta = con.execute(ACTIVITY_META).fetchall()

print(json.dumps({
    "source": "p2p-process-mining",
    "cases": cases,
    "variants": len(variants),
    "transitions": sum(follows.values()),
    "activities": [
        {
            "name": name,
            "events": events,
            "cases": act_cases,
            "batch_events": int(batch),
            "batch_share": batch / events,
            "resources": resources,
            "variant_occurrences": occurrences.get(name, 0),
        }
        for name, events, act_cases, batch, resources in sorted(meta, key=lambda r: -r[1])
    ],
    "edges": [
        {"from": a, "to": b, "cases": n}
        for (a, b), n in sorted(follows.items(), key=lambda kv: (-kv[1], kv[0]))
    ],
}))
