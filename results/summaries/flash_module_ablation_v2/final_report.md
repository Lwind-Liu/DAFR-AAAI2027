# Six-domain joint-risk tool-agent experiment

172 fixed tasks; 1,032 completed episodes with DeepSeek Flash and local stateful business tools.
Every configuration uses the same planner prompt, tool schemas, 10-turn limit and four-verification budget.
The single affine baseline remains frozen; targeted feedback uses each configuration's own controller.
Safe task success means achieving the requested business state without an unsafe commit.

| Configuration | Safe task success | Unsafe commits | Verification calls | Mean verification |
|---|---:|---:|---:|---:|
| Full geometric method | 100.0% (172/172) | 0 | 152 | 0.884 |
| Simple linear rule | 72.1% (124/172) | 48 | 185 | 1.076 |
| w/o Evidence Projection | 82.0% (141/172) | 31 | 105 | 0.610 |
| w/o Action-Evidence Binding | 63.4% (109/172) | 63 | 132 | 0.767 |
| w/o Geometric Constraints | 34.3% (59/172) | 113 | 0 | 0.000 |
| w/o Targeted Feedback | 100.0% (172/172) | 0 | 226 | 1.314 |

The geometric method improves safe task success by 27.9 percentage points over the simple affine rule.
Evidence projection, action-evidence binding and geometric constraints respectively avoid 31, 63 and 113 unsafe commits relative to their removal.
Targeted feedback preserves 100% safe task success while reducing verification calls from 226 to 152 (32.7%). This is a verification-efficiency contribution.

Component interventions:
- Evidence projection: flatten source provenance; external claimed grants enter the evidence pool.
- Action-evidence lifting: replace effect/field/value-bound evidence with an unbound current trusted-evidence indicator; preserve all risk paths and common scope checks.
- Geometry: bypass only the joint-risk admission gate.
- Targeted feedback: omit repair targets while retaining blocked decisions, tools and retry opportunities.

All source/data hashes, controller decisions and business state mutations passed replay verification. No API failures or budget-exhausted episodes.
Reproducible construction provenance and related-task grouping: frozen_protocol.json; precise interventions: component_definitions.json.
