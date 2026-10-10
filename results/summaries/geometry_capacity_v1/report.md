# Geometry capacity v1

Held-out quadratic-model subset; metrics verified by independent local simulator.

| Arm | False allow / unsafe | False block / safe | Task-success outputs / recoverable | Unsafe outputs |
|---|---:|---:|---:|---:|
| geometry | 0/353 | 0/247 | 481/481 | 0 |
| nonlinear_arithmetic | 0/353 | 0/247 | 481/481 | 0 |
| no_joint_budget | 204/353 | 0/247 | 247/481 | 328 |
| no_cross_channel | 136/353 | 0/247 | 247/481 | 299 |
| no_cooling_credit | 0/353 | 153/247 | 326/481 | 0 |
| static_state | 118/353 | 0/247 | 247/481 | 305 |
| no_repair | 0/353 | 0/247 | 247/481 | 0 |
| learned_linear_weighted | 2/353 | 61/247 | 418/481 | 18 |
| learned_linear_safety_1pct | 0/353 | 73/247 | 400/481 | 7 |
| linear_1_planes_weighted | 0/353 | 49/247 | 430/481 | 25 |
| linear_1_planes_safety_1pct | 0/353 | 86/247 | 395/481 | 0 |
| linear_4_planes_weighted | 2/353 | 15/247 | 460/481 | 16 |
| linear_4_planes_safety_1pct | 2/353 | 7/247 | 445/481 | 35 |
| linear_16_planes_weighted | 0/353 | 2/247 | 470/481 | 11 |
| linear_16_planes_safety_1pct | 0/353 | 1/247 | 453/481 | 28 |
| linear_64_planes_weighted | 0/353 | 3/247 | 480/481 | 1 |
| linear_64_planes_safety_1pct | 0/353 | 0/247 | 446/481 | 35 |

The nonlinear arithmetic control expresses the same constraint and should tie geometry.
Linear baselines use the same current/cooling coordinates. Supporting-plane count is an explicit complexity budget.
This is a simulator representation/ablation study, not evidence of production DAFR end-to-end performance.
