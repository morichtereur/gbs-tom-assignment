# GBS Target Operating Model — assignment

**A target operating model arrives as four columns on a slide. What the sorting costs is missing.**

Retained, captive, provider, automated — and the activities sorted into them by
the people whose functions are being sorted. The expensive part of a target
operating model is not where an activity sits. It is how often work crosses
between columns, and nobody in the room has measured which activities actually
follow each other.

This does. The handoff graph comes from the *variants* of a real 1.6M-event SAP
purchase-to-pay log — which activities empirically follow which, weighted by how
many cases did it — not from a documented process flow. Everything is then
assigned by an exact solver, and the number the slide never states is the one
the reader gets to move.

**[Interactive tool](dashboard.html)** · `make dashboard`

---

## The two metrics, fixed before anything was run

Both were written down before the model was solved, so the analysis could not be
written toward its own punchline.

1. **The share of activities whose assignment differs between the naive baseline
   — cheapest viable city, everything that can move moves — and the solver
   optimum.** Interesting in both directions. High means the workshop answer was
   wrong; low means the solver was unnecessary.

2. **The tipping point**: the coordination cost per handoff at which the optimal
   assignment flips away from concentration, and whether that value sits inside a
   defensible range or outside it.

The defensible range was fixed at **USD 0.25–4.00 per handoff** before the sweep
was run, from two to ten minutes of a receiving analyst's time priced against
the wage panel this study already carries. The arithmetic is in
[`config/model.yaml`](config/model.yaml).

---

## What it finds

**1. The workshop answer and the optimum disagree about most of the process.**
Roughly half the assignable activities sit somewhere different, and the naive
baseline breaks eight segregation-of-duties pairs on its way there. Part of that
gap is a control failure rather than a costing error, so the two are separated:
the best assignment that still concentrates in the baseline's own city and breaks
nothing is reported alongside it.

**2. The tipping point lands inside the defensible range, near its top edge.**
Which is a weaker result than it sounds. The case for concentrating this process
rests on the upper half of what a handoff can defensibly be argued to cost — and
below that price the model spreads work out and pays for the crossings.

**3. Most of the answer is not decided by anything.** Barring each activity in
turn from the unit it was given and re-solving, fewer than half the positions
change the total. The rest were placed by a declared tie-break because something
had to be. They are drawn as hatched rather than filled, in the tool and in the
results, because a tie rendered as a recommendation is the failure this study is
about.

**4. The classifier does not transfer, and that is measured rather than
assumed.** The transactional/judgment taxonomy from
[gbs-agentic-shift](https://github.com/morichtereur/gbs-agentic-shift) was
calibrated on job postings — several hundred words with a title on top. An SAP
activity name is three words. On this input it decides 17% of activity names and
its recall on judgment work is **zero**: every name it fires on, it fires on the
token "invoice", and it calls them all transactional. The measured error is what
the resampling runs over.

**5. No constraint in the model is decoration.** Removed one at a time, all four
move the assignment. Contact coverage moves the most — the requirement that
somebody can answer a supplier inside their working day is what keeps this
process out of the cheapest markets in the panel.

---

## Scope

Purchase-to-pay only. A narrow model that was checked beats a broad one that was
asserted, and nothing here extends to record-to-report or order-to-cash.

| | |
|---|---|
| Activities | 42 in the log, 29 assignable to a delivery model |
| Not assignable | 2 are the supplier's own act; 11 are SRM workflow statuses written by a single `batch_*` id |
| Volume | 251,734 PO line items, 1,595,923 events, 11,973 variants |
| Handoff graph | 498 directly-follows pairs, from the variants |
| Locations | the 11 evidenced GBS cities from [gbs-location-selection](https://github.com/morichtereur/gbs-location-selection) |
| Handling | about 69 FTE, from authored handling times |

Both inputs are snapshotted into `data/` by `make snapshot`, which runs each
upstream repository's own interpreter rather than importing across environments.
The snapshot is committed, so this repository runs standalone and a reader can
see exactly which upstream numbers the answer rests on.

---

## The model

**Decision.** Each assignable activity goes to exactly one
{retained, captive, provider, automated} × location.

**Objective.** Wage cost × handling time, plus a coordination penalty for every
transition between two units. Of the 1,344,189 transitions in the log, 210,536
are an activity repeating and never cross a unit, and 452,301 touch a vendor or a
system step and are unavoidable whatever anyone decides. Both are excluded and
reported, so the 681,352 that are priced mean what they say.

**Solver.** OR-Tools CP-SAT, solved to proven optimality at every price. No
heuristic, and no language model anywhere in the assignment decision.

### Constraints

| | what it does |
|---|---|
| Segregation of duties | Activity pairs that may not share a unit. The rule is **ported** from [finance-close-control-agent](https://github.com/morichtereur/finance-close-control-agent) CHK-03 — preparer may not be approver, irrespective of amount — with its subject changed from a user id to an organisational unit. The P2P pairs it applies to are authored, and listed with a reason each in [`config/sod.yaml`](config/sod.yaml). |
| Minimum viable site size | A captive site below the configured FTE floor does not carry its own overhead and is not opened. A provider is exempt: its floor already exists and is shared with other clients. That asymmetry is the only thing that makes this constraint bite differently by delivery model. |
| Contact coverage | Activities involving supplier or requester contact need a city that overlaps the headquarters working day and can hold the conversation. Applied to delivery cities only. |
| Judgment cap | In a city whose *measured* posting mix makes it a transactional hub, judgment work may not exceed a configured share of that city's FTE. The hub flag is measured upstream; the threshold and the cap are declared. |

**Automation is evidenced, not asserted.** An activity may be automated only
where the log already shows it running in batch above a floor. `Clear Invoice` is
194,393 events across 24 users with **zero** batch events, so this model cannot
automate it however much a slide would like to.

---

## Validation

### 1. Does the classifier transfer?

It does not, and the shape of the failure matters more than the headline. The
ported keyword taxonomy decides 7 of 42 activity names — 17% of names but 41% of
events, because the few it decides are the high-volume ones. Every one of those
7 fires on the token `invoice`, and it labels all of them transactional, giving
it a recall on judgment work of **0%**.

The residual goes to a language model. That is its only permitted role in this
repository: it never sees the assignment problem, it labels activity names, and
its output is scored against a hand-labelled gold set covering all 42 activities
before anything downstream reads it. The measured per-class error is what the
stability run resamples labels at, rather than an assumed rate.

The gold set is **authored, not independently ground-truthed** — it measures
agreement with one careful reading of what each activity is. That bounds what the
number can claim, and it is stated rather than footnoted. Run `make eval`.

### 2. Activity → ISCO wage group

This is a mapping this study authors, not a measurement. ILOSTAT publishes
earnings by ISCO-08 major group and no finer, so every activity is costed on
group 2, 3 or 4. Each assignment is declared with a one-line reason in
[`config/activities.yaml`](config/activities.yaml), and a quarter of activities
move to a neighbouring group in every resampling draw.

Handling time is the other authored quantity, and the larger one: the log records
when things happened, not how long they took. Every handling time carries ±30%
in the resampling.

### 3. Ablation

Each constraint removed in turn, everything else held. Same move as the pillar
ablation in `gbs-location-selection`. The result is in
[RESULTS.md](RESULTS.md) — no constraint in this model is decorative.

### 4. Resampling

10,000 draws over handling times, the provider and captive multipliers, the
automation run cost, the coordination price, the ISCO mapping and the
classifier's measured error. An activity whose unit holds in fewer than 75% of
draws is **reported as unstable and not given a position**.

---

## Where this departs from its own brief

Three, and they are here rather than absorbed silently.

**The retained anchor is a twelfth location.** The brief names eleven cities and
four delivery models, but gives retained work nowhere to sit — and retained work
is by definition not offshored. The anchor is Zurich, which is
`gbs-location-selection`'s own declared headquarters and a scored market there
with a measured wage, so no cost was invented. It is a config value
(`retained_location`).

**Reported in USD, not CHF.** The upstream wage panel is USD, and the tipping
point is a ratio between coordination cost and wage cost. Converting one side
would put an unmeasured FX assumption inside the headline number and buy nothing.

**The tipping point's definition was changed after seeing the sweep.** The first
definition was the price at which crossing transitions reach their floor. On this
instance that lands past USD 100 per handoff on the back of a final improvement
worth about 1% of crossings — a number with no claim to being where anything
flips. It is now measured where the assignment actually reorganises: the adjacent
pair of prices across which the most activities change unit. The objective, the
constraints and the ladder are untouched, but the choice was made with the data
in view and the rejected figure is reported alongside the new one.

---

## What it cannot tell you

- **Handling times are authored.** They are the largest unmeasured quantity in
  the model. The log timestamps when an activity happened, not how long it took,
  and no public source gives per-activity handling time for P2P.
- **India has no city-level wage** in any reachable source, so four of its five
  cities are identical on every input the model reads. They are reported as one
  band rather than ranked, and the fifth separates only on a hub flag resting on
  eight job postings.
- **A handoff is priced as one number.** In reality crossing into a provider and
  crossing a time zone are different costs. Modelling them separately would need
  a second number nobody has measured either.
- **Transition and severance costs are absent**, as are attrition, tax and
  incentives. The comparison is steady-state to steady-state.
- **One process, one log, one company.** The upstream log is 99.6% a single
  company ID, so nothing here is a benchmark.

---

## Run it

```
make install
make snapshot     # pull the two upstream repos into data/
make classify     # two-stage work-family labelling (needs ANTHROPIC_API_KEY)
make eval         # score it against the gold set
make run          # ladder, ablation, forced positions, RESULTS.md
make stability    # 10,000 draws — about an hour on eight cores
make dashboard    # the interactive tool
make test
```

`make classify-offline` runs stage 1 only, and the readout says so.

## Engineering

- **Solver core separate from the web layer.** `tom.solve` imports nothing from
  `tom.dashboard`; the page reads a JSON artefact.
- **Everything declared lives in `config/`.** A second process scope runs on the
  same code by pointing the loader elsewhere.
- **Typed frozen interfaces** at every module boundary (`tom.types`).
- **pytest on the constraint logic**, including the infeasibility cases: a
  known-infeasible input must raise rather than silently relax, and the same
  input must solve once the constraint is removed — otherwise the failure was a
  broken model rather than a working constraint.
- **Reproducibility is tested across processes**, not just within one. Set
  iteration order over strings depends on `PYTHONHASHSEED`, and on a degenerate
  instance that alone changes which answer comes back.
- **CI on push.**

## Stack

- **ortools** — CP-SAT, exact, one worker and a pinned seed so a reported optimum
  is reproducible
- **duckdb** — reading the upstream Parquet directly, in the upstream repo's venv
- **pyyaml** — the configs, which are the method
- **anthropic** — stage 2 of the classifier and nothing else
