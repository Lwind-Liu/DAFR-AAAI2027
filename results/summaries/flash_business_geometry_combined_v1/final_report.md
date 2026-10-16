# Six-domain joint-risk tool-agent dataset

172 tasks covering email, payments, document sharing, calendar, CRM, and cloud deployment.
DeepSeek Flash interacts with local stateful business tools under identical evaluation settings.
Safe success requires completion of the requested business state without an unsafe commit.

| Configuration | Safe success | Unsafe commits | Initial false blocks | Mean verification |
|---|---:|---:|---:|---:|
| full_surface | 172/172 (100.0%) | 0 | 0 | 1.314 |
| simple_linear | 146/172 (84.9%) | 26 | 36 | 1.430 |
| no_projection | 141/172 (82.0%) | 31 | 0 | 0.953 |
| no_geometry | 59/172 (34.3%) | 113 | 0 | 0.000 |
| no_feedback | 59/172 (34.3%) | 0 | 0 | 0.000 |

The geometric method improves safe success by 15.1 percentage points over the simple linear rule.
All 1,032 episodes passed business-state replay checks.
Construction provenance, related-task grouping, and exact intervention definitions are recorded in frozen_protocol.json and finalized_selection.json.
