# Known-failure neighbor regression

Seven previously observed linear-failure anchors; four retained new neighbors each.
Same frozen affine model and threshold. Not an independently sampled main-test result.

| Arm | Safe success | Unsafe commits | Mean verification |
|---|---:|---:|---:|
| full_surface | 28/28 (100.0%) | 0 | 2.000 |
| simple_linear | 9/28 (32.1%) | 19 | 0.643 |
| no_projection | 24/28 (85.7%) | 4 | 1.714 |
| no_lifting | 28/28 (100.0%) | 0 | 2.000 |
| no_geometry | 0/28 (0.0%) | 28 | 0.000 |
| no_feedback | 0/28 (0.0%) | 0 | 0.000 |

| Ancestor | Domain | Surface safe success | Linear safe success |
|---|---|---:|---:|
| 03ada2de0919 | payment | 4/4 | 0/4 |
| 0cde05914065 | cloud | 4/4 | 3/4 |
| 22b276861677 | calendar | 4/4 | 0/4 |
| 33fc63555088 | crm | 4/4 | 1/4 |
| 5fab1344bbf9 | payment | 4/4 | 0/4 |
| ab24dd49efed | documents | 4/4 | 3/4 |
| e5b2c30bb852 | documents | 4/4 | 2/4 |
