# Results

Purchase-to-pay only. Every figure below is reproduced by `make run`.

## The two metrics, fixed before the run

1. **Share of activities whose assignment differs between the naive baseline and the solver optimum.**
2. **The coordination cost per handoff at which the optimum flips away from concentration, and whether it sits inside the defensible range.**

The defensible range for coordination cost was set at USD 0.25–4.00 per handoff from handling minutes and the wage panel, before the sweep was run.

## Scale

| | |
|---|---:|
| Activities in the log | 42 |
| Assignable to a delivery model | 29 |
| Total handling | 69 FTE |
| Candidate units (delivery model x location) | 18 |
| Transitions in the log | 1,344,189 |
| — same activity repeating, never crosses a unit | 210,536 |
| — touching a vendor or system activity, unavoidable | 452,301 |
| **Transitions the objective prices** | **681,352** |

## 1. The headline

**55%** of assignable activities sit somewhere different in the solver optimum than in the naive baseline (16 of 29).

| | naive baseline | solver optimum |
|---|---:|---:|
| Labour | USD 287,219 | USD 442,092 |
| Coordination | USD 11,976 | USD 815,878 |
| **Total** | **USD 299,195** | **USD 1,257,970** |
| Crossing transitions | 7,984 | 543,919 |
| Segregation-of-duties breaches | 8 | 0 |

The baseline puts everything in **in:Bangalore** and breaks 8 segregation-of-duties pairs doing it. That makes the gap above partly a control failure rather than a costing error, so the fair comparison is separated out: the best assignment that still concentrates in in:Bangalore and breaks nothing differs from the optimum on **38%** of activities and costs USD 1,409,104.

## 2. The tipping point

**USD 3.38 per handoff.** Below it the model spreads work across cheaper cities and pays for the crossings. At that price **20 of 29 activities change unit at once**, and crossing transitions fall from 625,718 at a price of zero towards 339,102.

That value sits **inside** the defensible range of USD 0.25–4.00 — near its top edge, which is worth saying plainly: the case for concentrating this process rests on the upper half of what a handoff can defensibly be argued to cost.

> The definition was changed after seeing the sweep. Crossing transitions do not reach their absolute floor until USD 111 per handoff, and the last step before that is worth 1.1% of crossings. Reporting USD 111 as the tipping point would be reporting the end of the sweep. The reported figure is where the assignment actually reorganises. Nothing in the objective, the constraints or the ladder was touched — but the change was made with the data in view, so it is disclosed here rather than presented as the plan all along.

| coordination cost | units before | units after |
|---|---:|---:|
| USD 3.50 → 3.75 | 5 | 3 |

## The optimum at the declared price

At USD 1.50 per handoff, total USD 1,257,970.

| unit | FTE | activities |
|---|---:|---|
| captive@in:Bangalore *(not separable from Chennai, Mumbai, Pune)* | 35.0 | 13 |
| captive@in:Hyderabad | 19.1 | 3 |
| automated | 11.8 | 5 |
| provider@pl:Wrocław | 3.2 | 6 |
| provider@pl:Poznań | 0.1 | 2 |

## How much of the answer is actually decided

Each activity was barred in turn from the unit it was given, and the model re-solved. Where the total does not move, nothing decided that position — several answers cost the same and a declared tie-break picked one.

**13 of 29** positions are decided by cost. The remaining **16** are placed, not chosen, and are drawn as undecided rather than as a position.

| activity | unit | cost of moving it | next best |
|---|---|---:|---|
| Remove Payment Block | automated | USD 170,244 | captive@pl:Wrocław |
| Create Purchase Requisition Item | automated | USD 61,969 | provider@pl:Wrocław |
| Cancel Invoice Receipt | automated | USD 17,120 | provider@pl:Poznań |
| Change Quantity | provider@pl:Wrocław | USD 15,990 | provider@pl:Kraków |
| Change Price | provider@pl:Wrocław | USD 14,976 | provider@pl:Kraków |
| Change Approval for Purchase Order | provider@pl:Wrocław | USD 11,428 | provider@pl:Kraków |
| Receive Order Confirmation | automated | USD 5,032 | provider@pl:Poznań |
| Delete Purchase Order Item | provider@pl:Wrocław | USD 4,596 | provider@pl:Kraków |
| Release Purchase Order | provider@pl:Wrocław | USD 1,265 | captive@in:Hyderabad |
| Cancel Subsequent Invoice | provider@pl:Poznań | USD 684 | provider@pl:Wrocław |
| Update Order Confirmation | automated | USD 361 | provider@pl:Wrocław |
| Change Currency | provider@pl:Wrocław | USD 24 | provider@pl:Poznań |
| Change payment term | provider@pl:Poznań | USD 1 | provider@pl:Wrocław |

## What each constraint is doing

Removed one at a time, everything else held.

| constraint | activities moved | cost without it | units | SoD breaches |
|---|---:|---:|---:|---:|
| sod | 3 (10%) | USD -408,158 | -1 | 3 |
| min_site_size | 8 (28%) | USD -26,822 | +0 | 0 |
| contact_coverage | 14 (48%) | USD -523,940 | -3 | 0 |
| judgment_cap | 6 (21%) | USD -29,875 | -1 | 0 |

## Does the classifier transfer?

The transactional/judgment classifier in `gbs-agentic-shift` was calibrated on job postings. Scored on SAP activity names against a hand-labelled gold set covering all 42:

| stage | n | accuracy | recall transactional | recall judgment |
|---|---:|---:|---:|---:|
| 1 — ported keyword taxonomy | 7 | 71.4% | 100.0% | 0.0% |
| 2 — claude-sonnet-5 on the residual | 35 | 80.0% | 73.9% | 91.7% |
| combined | 42 | 78.6% | 78.6% | 78.6% |

The ported taxonomy decides 17% of activity names — 41% of events — and its judgment recall on this input is 0%.

## What survives resampling

200 draws over handling minutes, the provider and captive multipliers, the automation run cost, the coordination price, the authored ISCO mapping, and the classifier's own measured error rate.

**8 of 29** activities hold the same unit in at least 75% of draws. The other 21 are reported as unstable and are not given a position.

| activity | modal unit | holds in | verdict |
|---|---|---:|---|
| Cancel Invoice Receipt | automated | 100% | stable |
| Create Purchase Requisition Item | automated | 100% | stable |
| Remove Payment Block | automated | 100% | stable |
| Receive Order Confirmation | automated | 90% | stable |
| Update Order Confirmation | automated | 90% | stable |
| Cancel Subsequent Invoice | provider@pl:Poznań | 88% | stable |
| Change Price | provider@pl:Wrocław | 78% | stable |
| Change Quantity | provider@pl:Wrocław | 75% | stable |
| Change Currency | provider@pl:Wrocław | 74% | **unstable** |
| Delete Purchase Order Item | provider@pl:Wrocław | 60% | **unstable** |
| Change Approval for Purchase Order | provider@pl:Wrocław | 58% | **unstable** |
| Change payment term | provider@pl:Poznań | 58% | **unstable** |
| Change Final Invoice Indicator | captive@in:Hyderabad | 55% | **unstable** |
| Change Delivery Indicator | captive@in:Hyderabad | 54% | **unstable** |
| Cancel Goods Receipt | captive@in:Hyderabad | 54% | **unstable** |
| Record Subsequent Invoice | captive@in:Hyderabad | 54% | **unstable** |
| Change Storage Location | captive@in:Hyderabad | 53% | **unstable** |
| Clear Invoice | captive@in:Hyderabad | 53% | **unstable** |
| Create Purchase Order Item | captive@in:Hyderabad | 53% | **unstable** |
| Record Goods Receipt | captive@in:Hyderabad | 53% | **unstable** |
| Record Service Entry Sheet | captive@in:Hyderabad | 53% | **unstable** |
| Release Purchase Requisition | captive@in:Hyderabad | 53% | **unstable** |
| SRM: Transfer Failed (E.Sys.) | captive@in:Hyderabad | 52% | **unstable** |
| Release Purchase Order | provider@pl:Wrocław | 52% | **unstable** |
| Block Purchase Order Item | captive@in:Hyderabad | 48% | **unstable** |
| Record Invoice Receipt | captive@in:Hyderabad | 44% | **unstable** |
| Set Payment Block | captive@in:Hyderabad | 44% | **unstable** |
| Change Rejection Indicator | captive@in:Hyderabad | 38% | **unstable** |
| Reactivate Purchase Order Item | captive@in:Hyderabad | 38% | **unstable** |

## What the cost model cannot separate

- Bangalore, Hyderabad — identical on every input the model reads.

