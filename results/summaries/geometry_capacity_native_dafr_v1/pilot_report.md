# Native DAFR capacity replay

Unmodified production executor module-factorial replay on frozen proposals; no new LLM planner or post-feedback replanning.

| Configuration | Unsafe forwarded | Safe blocked | Task success | Changed allocations |
|---|---:|---:|---:|---:|
| full | 3/3 | 0/7 | 7/10 | 0 |
| off_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_3 | 3/3 | 0/7 | 7/10 | 0 |
| off_3_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_2 | 3/3 | 0/7 | 7/10 | 0 |
| off_2_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_2_3 | 3/3 | 0/7 | 7/10 | 0 |
| off_2_3_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_1 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_3 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_3_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_2 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_2_4 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_2_3 | 3/3 | 0/7 | 7/10 | 0 |
| off_1_2_3_4 | 3/3 | 0/7 | 7/10 | 0 |
| halfspace_only | 3/3 | 0/7 | 7/10 | 0 |
| cone_only | 3/3 | 0/7 | 7/10 | 0 |

off_1=evidence projection; off_2=action-evidence lifting; off_3=dynamic geometry; off_4=decision/repair. Combinations disable the listed production switches.

Unsafe forwarded calls are rejected by simulator, not unsafe environment commits. No native capacity cone or numerical scaling repair is added. Failed domain coverage cannot substantiate full-method superiority.
