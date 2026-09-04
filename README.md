# GBS target operating model — purchase-to-pay

[![Tests](https://github.com/morichtereur/gbs-tom-assignment/actions/workflows/test.yml/badge.svg)](https://github.com/morichtereur/gbs-tom-assignment/actions/workflows/test.yml)

A target operating model arrives as four columns on a slide: retained, captive,
provider, automated, with the activities sorted into them by the people whose
functions are being sorted. The expensive part of that model is not where an
activity sits. It is how often work crosses between columns — and nobody in the
room has measured which activities actually follow each other.

This measures it, from the *variants* of a real 1.6M-event SAP purchase-to-pay
log, and prices the crossings.

**[Interactive tool](dashboard.html)** · `make dashboard`

---

## The question, fixed before anything was run

Both metrics were written down before the model was solved, so the analysis
could not be written toward its own punchline.

1. **The share of activities assigned differently** by the naive baseline —
   cheapest viable city, everything that can move moves — and by the solver
   optimum. Interesting either way: high means the workshop answer was wrong,
   low means the solver was unnecessary.
2. **The tipping point**: the coordination cost per handoff at which the optimum
   flips away from concentration, and whether it falls inside a defensible range.

The defensible range was fixed at **USD 0.25–4.00 per handoff** before the sweep
ran, from two to ten minutes of a receiving analyst's time priced against the
wage panel. The arithmetic is in [`config/model.yaml`](config/model.yaml).

---

## The answer

**Concentrating purchase-to-pay pays only above USD 3.38 per handoff — the top
half of the defensible range, not the middle of it.** Below that price the model
spreads work across cheaper cities and pays for the crossings. At it, 22 of 29
activities change unit at once.

**On the positions the model actually decides, the workshop answer is wrong every
time.** Cost decides 13 of 29 positions, and the naive baseline puts all 13
somewhere else. The raw pre-registered figure is 90%, but that number is inflated
by ties; the restricted one is 13 of 13 and it is the one worth quoting.

**And the model decides less than half of its own answer.** The other 16
positions are ties — several units cost exactly the same — so the tool leaves
them blank rather than filling them in. The deliverable here is a price and a set
of bands, not a target operating model.

---

## What follows

**1. Coordination is not a rounding error on this process.** At the declared
price, crossing transitions cost 1.85x the wage bill they are coordinating.
The slide that sorts activities into four columns is silently taking a position
on a number larger than the one it is optimising.

**2. Contact coverage, not cost, keeps this process out of the cheapest markets.**
Remove it and 28 of 29 activities move and the bill falls by roughly half a
million dollars — far more than any other constraint. The requirement is only that somebody can answer
a supplier inside their working day, and it is worth more than the entire
labour-arbitrage argument.

**3. One of the four columns is empty at every price.** Nothing is ever assigned
to *retained*. None of the four constraints says that authority over company
spend has to sit inside the company, and the brief specified none that does. The
empty column is the model reporting that faithfully — not a recommendation to
abolish the retained organisation, but a statement that wanting one is not the
same as having written it down.

**4. The work-family classifier does not transfer, and the failure is total on
judgment work.** The taxonomy from
[gbs-agentic-shift](https://github.com/morichtereur/gbs-agentic-shift) was
calibrated on job postings — several hundred words with a title on top. An SAP
activity name is three words. It decides 17% of activity names, every one of
those on the token `invoice`, and its recall on judgment work is **0%**. That
error is measured against a hand-labelled gold set and then resampled over,
rather than inherited.

**5. The count of activities a constraint moves is not what it costs.**
Segregation of duties moves only three activities and costs about USD 409k — the
cheapest constraint to state and among the most expensive to obey. Contact
coverage moves 28 and costs about half a million. A constraint that touches
little can still be the one paying for the model, and none of the four here is
decoration, which is a weaker claim than it sounds and worth making anyway: the
usual outcome of this test is that two of them do nothing.

---

## How the answer was reached

**Decision.** Each assignable activity goes to exactly one
{retained, captive, provider, automated} × location.

**Objective.** Wage cost × handling time, plus a coordination penalty for every
transition between two units, plus a small annual overhead per open unit. Of the
1,344,189 transitions in the log, 210,536 are an activity repeating and never
cross a unit, and 452,301 touch a vendor or a system step and are unavoidable
whatever anyone decides. Both are excluded and reported, so the 681,352 that are
priced mean what they say.

**Solver.** OR-Tools CP-SAT, proven optimality at every price. No heuristic, and
no language model anywhere in the assignment decision.

### Constraints

| | what it does |
|---|---|
| Segregation of duties | Activity pairs that may not share a unit. The rule is **ported** from [finance-close-control-agent](https://github.com/morichtereur/finance-close-control-agent) CHK-03 — preparer may not be approver, irrespective of amount — with its subject changed from a user id to an organisational unit. The P2P pairs it applies to are authored, and listed with a reason each in [`config/sod.yaml`](config/sod.yaml). |
| Minimum viable site size | A captive site below the FTE floor does not carry its own overhead and is not opened. A provider is exempt: its floor already exists and is shared with other clients. That asymmetry is the only thing making this constraint bite differently by delivery model. |
| Contact coverage | Activities involving supplier or requester contact need a city that overlaps the headquarters working day and can hold the conversation. Delivery cities only. |
| Judgment cap | In a city whose *measured* posting mix makes it a transactional hub, judgment work may not exceed a share of that city's FTE. The hub flag is measured upstream; the threshold and cap are declared. |

**Automation is evidenced, not asserted.** An activity may be automated only
where the log already shows it running in batch above a floor. `Clear Invoice` is
194,393 events across 24 users with **zero** batch events, so this model cannot
automate it however much a slide would like to.

---

## What the answer rests on

**One input is measured. The four that decide the cost are declared.**

| | |
|---|---|
| **Measured** | Which activities follow each other — 498 directly-follows pairs from 11,973 variants. Activity volumes, distinct users, and the share already running in batch. |
| **Declared** | Handling time per activity; the activity → ISCO wage-group mapping; the provider margin; the coordination price itself. All resampled 10,000 times. |
| **Measured, and it failed** | The transactional/judgment classifier: 79% accurate combined, against a gold set covering all 42 activities. Its per-class error is what the resampling runs over. |
| **Not separable** | India has no city-level wage in any reachable source, so four of its five cities are identical on every input the model reads. Reported as one band, not ranked. |

The gold set is **authored, not independently ground-truthed** — it measures
agreement with one careful reading of what each activity is. That bounds what the
number can claim, and it is stated rather than footnoted.

An activity whose unit holds in fewer than 75% of draws is **reported as unstable
and not given a position**. Most of them are.

---

## What this cannot tell you

- **Handling times are authored.** The largest unmeasured quantity in the model.
  The log records when an activity happened, not how long it took, and no public
  source gives per-activity handling time for P2P.
- **A handoff is priced as one number.** Crossing into a provider and crossing a
  time zone are different costs in reality. Splitting them would need a second
  number nobody has measured either.
- **Transition and severance costs are absent**, as are attrition, tax and
  incentives. The comparison is steady state to steady state.
- **One process, one log, one company.** The upstream log is 99.6% a single
  company ID, so nothing here is a benchmark.
- **Purchase-to-pay only.** Nothing extends to record-to-report or order-to-cash
  until P2P is validated.

---

## Where this departs from its own brief

Three, stated here rather than absorbed silently.

**The retained anchor is a twelfth location.** The brief names eleven cities and
four delivery models but gives retained work nowhere to sit, and retained work is
by definition not offshored. The anchor is Zurich — `gbs-location-selection`'s own
declared headquarters and a scored market there with a measured wage, so no cost
was invented. It is a config value.

**Reported in USD, not CHF.** The upstream wage panel is USD and the tipping
point is a ratio between coordination cost and wage cost. Converting one side
would put an unmeasured FX assumption inside the headline number and buy nothing.

**The tipping point's definition changed after seeing the sweep.** The first
definition was the price at which crossing transitions reach their floor. On this
instance that lands past USD 100 per handoff on the back of a final improvement
worth about 1% of crossings — the end of the sweep, not a flip. It is now measured
where the assignment actually reorganises. The objective, constraints and ladder
are untouched, but the choice was made with the data in view, and the rejected
figure is reported beside the new one.

A fourth thing was added rather than departed from: a small annual overhead per
open unit. It is a real cost the first version omitted, and it was noticed because
of a presentation problem rather than an audit. Both halves are in the config.

---

## Run it

```
make install
make snapshot     # pull the two upstream repos into data/
make classify     # two-stage work-family labelling (needs ANTHROPIC_API_KEY)
make eval         # score it against the gold set
make run          # ladder, ablation, forced positions, RESULTS.md — a few minutes
make stability    # 10,000 draws — 1.5 to 2 hours on eight cores
make dashboard    # the interactive tool
make test
```

`make classify-stage1` runs the ported taxonomy alone and reports how little of
the activity set it decides. It deliberately writes nothing: handing the solver 35
defaulted labels would let it run without complaining, and a defaulted label is
not a classification.

## Engineering

- **Solver core separate from the web layer.** `tom.solve` imports nothing from
  `tom.dashboard`; the page reads a JSON artefact.
- **Everything declared lives in `config/`.** A second process scope runs on the
  same code by pointing the loader elsewhere.
- **Typed frozen interfaces** at every module boundary (`tom.types`).
- **pytest on the constraint logic**, including infeasibility: a known-infeasible
  input must raise rather than silently relax, and the same input must solve once
  the constraint is removed — otherwise the failure was a broken model rather than
  a working constraint.
- **The expensive question is asked the cheap way.** "Is this position decided by
  cost" is asked a few thousand times to draw the tool. As an optimisation — bar
  the unit, re-solve, compare totals — each needs an optimality proof. As a
  feasibility question — bar the unit, is anything still this cheap — it does not,
  and runs about four times faster. A test asserts the two agree on every
  activity, because otherwise the fast one is a different question.
- **Reproducibility is tested across processes**, not just within one. Set
  iteration order over strings depends on `PYTHONHASHSEED`, and on a degenerate
  instance that alone changes which answer comes back.
- **CI on push.**

## Stack

- **ortools** — CP-SAT, exact, pinned seed and worker count so a reported optimum
  is reproducible
- **duckdb** — reading the upstream Parquet directly, in the upstream repo's venv
- **pyyaml** — the configs, which are the method
- **anthropic** — stage 2 of the classifier and nothing else

---

Built by [Moritz Richter](https://www.linkedin.com/in/moritz-richter-28297119a/) · Finance & Strategy Consultant · Zürich · [Portfolio](https://morichtereur.github.io/)
