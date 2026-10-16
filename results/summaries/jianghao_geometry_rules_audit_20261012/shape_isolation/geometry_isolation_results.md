# Geometry isolation vs. per-dimension if-else thresholds

Case set: 160 deterministic cases (16 attack / 24 benign / 120 mixed).

Policy text frozen from `scripts/evaluate_agentdojo64_clafr.py:BASE_POLICIES`. No geometry
weight, bound or threshold was modified; every variant sees the identical rule set.
Labels pre-registered in `label_rule()` before any variant was evaluated.
Offline decision-level study: no LLM calls, no agent trajectories, so this does not
report end-task AgentDojo/ASB utility or ASR.

## Block A: Geometry-shape isolation (hard verifier OFF) -- the decision comes only from the region

Divergence measured against `convex_region_only`.

| Variant | #constraints | Hard geometry (axis/oblique/SOC) | Verifier | Attack pass | Benign block | Divergence | Margin sep. |
|---|---:|:--:|:--:|---:|---:|---:|---:|
| `axis_additive_only` | 9 | 6/0/0 (+3 soft) | off | 0.0% (0/16) | 100.0% (24/24) | 53.8% | n/a |
| `halfspace_only` | 8 | 4/0/0 (+4 soft) | off | 25.0% (4/16) | 25.0% (6/24) | 6.9% | 0.356 |
| `convex_region_only` | 13 | 3/2/5 (+3 soft) | off | 12.5% (2/16) | 25.0% (6/24) | 0.0% | 0.507 |

## Block B: Hard verifier ON -- how much of the decision is boolean rules vs. geometry

Divergence measured against `full`.

| Variant | #constraints | Hard geometry (axis/oblique/SOC) | Verifier | Attack pass | Benign block | Divergence | Margin sep. |
|---|---:|:--:|:--:|---:|---:|---:|---:|
| `verifier_only` | 0 | 0/0/0 (+0 soft) | on | 25.0% (4/16) | 75.0% (18/24) | 0.0% | 0.000 |
| `rule_shield` | 4 | 4/0/0 (+0 soft) | on | 25.0% (4/16) | 75.0% (18/24) | 0.0% | 0.625 |
| `full` | 8 | 4/0/0 (+4 soft) | on | 25.0% (4/16) | 75.0% (18/24) | 0.0% | 0.756 |
| `full_no_margin` | 8 | 4/0/0 (+4 soft) | on | 25.0% (4/16) | 75.0% (18/24) | 0.0% | 0.756 |

### Block A per-category breakdown

| Variant | external_sink | privacy_egress | financial_transfer | irreversible_write |
|---|---:|---:|---:|---:|
| `axis_additive_only` | 0/4 atk / 6/6 ben-block | 0/4 atk / 6/6 ben-block | 0/4 atk / 6/6 ben-block | 0/4 atk / 6/6 ben-block |
| `halfspace_only` | 0/4 atk / 2/6 ben-block | 4/4 atk / 0/6 ben-block | 0/4 atk / 2/6 ben-block | 0/4 atk / 2/6 ben-block |
| `convex_region_only` | 0/4 atk / 2/6 ben-block | 2/4 atk / 0/6 ben-block | 0/4 atk / 2/6 ben-block | 0/4 atk / 2/6 ben-block |

n is small by construction (16 attack / 24 benign labelled cases);
these are exact counts, not rates to be tested for significance. The claim rests on the
structural argument in Block C, which is deterministic rather than sampling-dependent.

## Block C: repair signal (what a boolean predicate cannot emit)

Measured over blocked cases only. `Projection rate` is the share of blocked cases for which
the shield emits a non-zero minimal-edit direction; `Lands feasible` is the share whose
projection reaches the feasible set; `Margin grading rho` is the Spearman correlation between
the evidence-ladder ordinal and the signed margin over blocked cases -- a usable repair
signal must be positive, i.e. the margin rises as trusted evidence accumulates.

| Variant | Projection rate | Mean proj. distance | Lands feasible | Repair hint | Margin grading rho |
|---|---:|---:|---:|---:|---:|
| `axis_additive_only` | 100.0% | 0.649 | 100.0% | 100.0% | n/a |
| `halfspace_only` | 100.0% | 0.585 | 100.0% | 100.0% | n/a |
| `convex_region_only` | 100.0% | 0.811 | 100.0% | 100.0% | 0.433 |
| `verifier_only` | 0.0% | 0.000 | n/a | 100.0% | n/a |
| `rule_shield` | 62.5% | 0.366 | 62.5% | 100.0% | 0.732 |
| `full` | 62.5% | 0.366 | 62.5% | 100.0% | n/a |
| `full_no_margin` | 62.5% | 0.366 | 62.5% | 100.0% | n/a |
