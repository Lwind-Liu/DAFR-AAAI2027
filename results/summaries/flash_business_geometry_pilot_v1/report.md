# Flash agent experiment

Real LLM tool calls in synthetic stateful business sandboxes; upgraded relational surface.
Not an original benchmark rerun or production probability calibration.

| Arm | Cases | Safe success | Unsafe commits | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 24 | 24 | 0 | 1.50 |
| simple_linear | 24 | 23 | 1 | 1.75 |
| no_projection | 24 | 19 | 5 | 1.08 |
| no_lifting | 24 | 24 | 0 | 1.83 |
| no_geometry | 24 | 6 | 18 | 0.00 |
| no_feedback | 24 | 6 | 0 | 0.00 |

All cases and API failures are retained; exploratory pilot and frozen test are reported separately.
