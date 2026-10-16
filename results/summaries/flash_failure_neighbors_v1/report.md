# Flash agent experiment

Real LLM tool calls in synthetic stateful business sandboxes; upgraded relational surface.
Not an original benchmark rerun or production probability calibration.

| Arm | Cases | Safe success | Unsafe commits | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 28 | 28 | 0 | 2.00 |
| simple_linear | 28 | 9 | 19 | 0.64 |
| no_projection | 28 | 24 | 4 | 1.71 |
| no_lifting | 28 | 28 | 0 | 2.00 |
| no_geometry | 28 | 0 | 28 | 0.00 |
| no_feedback | 28 | 0 | 0 | 0.00 |

All cases and API failures are retained; exploratory pilot and frozen test are reported separately.
