# Flash agent experiment

Real LLM tool calls in synthetic stateful business sandboxes; upgraded relational surface.
Not an original benchmark rerun or production probability calibration.

| Arm | Cases | Safe success | Unsafe commits | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 18 | 18 | 0 | 1.56 |
| simple_linear | 18 | 15 | 0 | 1.78 |
| no_projection | 18 | 13 | 5 | 1.00 |
| no_lifting | 18 | 18 | 0 | 1.56 |
| no_geometry | 18 | 4 | 14 | 0.00 |
| no_feedback | 18 | 4 | 0 | 0.00 |

All cases and API failures are retained; exploratory pilot and frozen test are reported separately.
