# Independent follow-up boundary stress results

96 new tasks; 75% oracle-boundary cases and 25% broad cases. The previous 144-task main result is unchanged.

| Configuration | Safe success | Unsafe commits | Initial false blocks | Mean verification |
|---|---:|---:|---:|---:|
| full_surface | 100.0% | 0 | 0 | 1.146 |
| simple_linear | 95.8% | 4 | 38 | 1.854 |
| no_projection | 83.3% | 16 | 0 | 0.812 |
| no_lifting | 100.0% | 0 | 36 | 1.896 |
| no_geometry | 42.7% | 55 | 0 | 0.000 |
| no_feedback | 42.7% | 0 | 0 | 0.000 |

Full-minus-linear safe-success gain: 4.17 percentage points; paired 95% CI [1.04, 8.33].

All strata and split composition are reported in stress_analysis.json; no sample was selected by an affine prediction or method outcome.
This is an exploratory synthetic boundary stress distribution, not an estimate of production frequencies or a replacement main result.
