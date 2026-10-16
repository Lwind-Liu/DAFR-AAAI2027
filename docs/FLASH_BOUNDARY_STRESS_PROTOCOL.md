# Separately reported joint-risk boundary stress test

The original 144-task business test remains unchanged and must still be
reported. This new stress test is exploratory follow-up after observing that
performance depends on causal topology and verification. It is not evidence
that the original operational distribution has changed.

The fixed mixture is 75% boundary cases and 25% broad cases. For a boundary
case, sample ordinary event probabilities and causal paths, independently draw
a ratio in [0.9, 1.1], and set the budget to the independently enumerated
expected loss divided by that ratio. Broad cases retain their original budget.
No affine prediction, learned coefficient, method decision, or outcome is used
to retain, discard or assign any case. Every generated case is kept.

All four causal families remain equally represented in the 96-task test:
six broad and eighteen boundary cases in each family. Six business domains
contain sixteen tasks each. Train and development use the same 75/25 mixture,
with original held-out domains and graph families unchanged. The affine rule
is refit and recalibrated on these training/development states, rather than
being exposed only at test time to the harder mixture.

The model, tool schemas, registry semantics, four-query budget, ten-turn limit,
shared fully-verified-path rule, six comparison arms, and independent executor
remain unchanged. Report broad and boundary strata separately, the actual
aggregate 75/25 mixture, and the unchanged previous main results. Do not claim
the new aggregate is representative of production frequencies.

The 75/25 match is global, not conditional on training topology. Under the
fixed row rotation, broad training/development cases are shared-source cases;
test broad cases span all four topologies. Exact joint counts are retained in
stress_analysis.json. This association limits interpretation of transfer.

Reproduce with scripts/run_flash_boundary_geometry.py using per-domain 16,
seed 20261023, budget-cny 9, and output
results/summaries/flash_boundary_geometry_test_v1. Data and protocol are frozen
before paid calls. All traces and failures are retained. No paper replacement
is generated for this follow-up.
