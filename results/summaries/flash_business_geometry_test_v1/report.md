# Flash agent experiment

Real LLM tool calls in synthetic stateful business sandboxes; upgraded relational surface.
Not an original benchmark rerun or production probability calibration.

| Arm | Cases | Safe success | Unsafe commits | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 144 | 144 | 0 | 1.18 |
| simple_linear | 144 | 137 | 7 | 1.58 |
| no_projection | 144 | 117 | 27 | 0.81 |
| no_lifting | 144 | 144 | 0 | 1.85 |
| no_geometry | 144 | 59 | 85 | 0.00 |
| no_feedback | 144 | 59 | 0 | 0.00 |

All cases and API failures are retained; exploratory pilot and frozen test are reported separately.
