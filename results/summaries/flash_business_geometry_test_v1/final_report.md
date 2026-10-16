# Final Flash business tool-agent results

Frozen test: 144 tasks, 864 paired method runs, six business domains.

| Configuration | Safe task success | Unsafe commits | First-preflight false blocks | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 100.0% | 0 | 0 | 1.181 |
| simple_linear | 95.1% | 7 | 36 | 1.583 |
| no_projection | 81.2% | 27 | 0 | 0.806 |
| no_lifting | 100.0% | 0 | 48 | 1.847 |
| no_geometry | 41.0% | 85 | 0 | 0.000 |
| no_feedback | 41.0% | 0 | 0 | 0.000 |

Safe-success gain over linear: 4.86 percentage points; paired 95% CI [2.08, 9.03].
Verification queries saved: 0.403 per task (25.4%); paired 95% CI [0.236, 0.569].

Lifting removal can preserve final success through extra verification. Its contribution is measured by false blocks and query burden, rather than asserting that every ablation lowers success.

Real LLM calls in synthetic stateful environments with declared uncertainty and causal paths. This does not validate production probability estimation, real service execution, or the original benchmark NLP encoder. Historical benchmark numbers are unchanged.

The simpler first test and all pilots are retained separately; they are not pooled with this frozen test.
