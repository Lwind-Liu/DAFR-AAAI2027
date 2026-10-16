# Flash agent experiment

Real LLM tool calls in synthetic stateful business sandboxes; upgraded relational surface.
Not an original benchmark rerun or production probability calibration.

| Arm | Cases | Safe success | Unsafe commits | Mean verification queries |
|---|---:|---:|---:|---:|
| full_surface | 96 | 96 | 0 | 1.15 |
| simple_linear | 96 | 92 | 4 | 1.85 |
| no_projection | 96 | 80 | 16 | 0.81 |
| no_lifting | 96 | 96 | 0 | 1.90 |
| no_geometry | 96 | 41 | 55 | 0.00 |
| no_feedback | 96 | 41 | 0 | 0.00 |

All cases and API failures are retained; exploratory pilot and frozen test are reported separately.
