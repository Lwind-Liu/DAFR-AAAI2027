# Flash agent experiment

Real LLM tool calls in synthetic stateful business sandboxes; upgraded relational surface.
Not an original benchmark rerun or production probability calibration.

| Arm | Cases | Safe success | Unsafe commits | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 144 | 144 | 0 | 1.38 |
| simple_linear | 144 | 144 | 0 | 1.65 |
| no_projection | 144 | 113 | 31 | 0.94 |
| no_lifting | 144 | 144 | 0 | 1.57 |
| no_geometry | 144 | 45 | 99 | 0.00 |
| no_feedback | 144 | 45 | 0 | 0.00 |

All cases and API failures are retained; exploratory pilot and frozen test are reported separately.
