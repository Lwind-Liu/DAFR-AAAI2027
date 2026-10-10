# Native DAFR capacity replay

Historical run before the later destination-grounding/repair fixes. Those fixes do not add capacity encoding. See ../native_semantic_probe_v1/review.md for the subsequent semantic probe and current implementation status. The table below remains the recorded original run.

Unmodified production executor module-factorial replay on frozen proposals; no new LLM planner or post-feedback replanning.

| Configuration | Unsafe forwarded | Safe blocked | Task success | Changed allocations |
|---|---:|---:|---:|---:|
| full | 353/353 | 0/247 | 247/481 | 0 |
| off_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_3 | 353/353 | 0/247 | 247/481 | 0 |
| off_3_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_2 | 353/353 | 0/247 | 247/481 | 0 |
| off_2_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_2_3 | 353/353 | 0/247 | 247/481 | 0 |
| off_2_3_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_1 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_3 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_3_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_2 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_2_4 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_2_3 | 353/353 | 0/247 | 247/481 | 0 |
| off_1_2_3_4 | 353/353 | 0/247 | 247/481 | 0 |
| halfspace_only | 353/353 | 0/247 | 247/481 | 0 |
| cone_only | 353/353 | 0/247 | 247/481 | 0 |

off_1=evidence projection; off_2=action-evidence lifting; off_3=dynamic geometry; off_4=decision/repair. Combinations disable the listed production switches.

Unsafe forwarded calls are rejected by simulator, not unsafe environment commits. No native capacity cone or numerical scaling repair is added. Failed domain coverage cannot substantiate full-method superiority.
