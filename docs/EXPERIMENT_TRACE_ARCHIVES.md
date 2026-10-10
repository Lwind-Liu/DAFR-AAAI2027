# Experiment trace archives

Large experiment traces are stored as lossless `.jsonl.gz` archives to stay
within GitHub's per-file size limit. Local uncompressed traces are ignored by
Git and are retained when present. Dataset inputs, labels, evaluators, summary
reports, and paper tables remain in their original formats.

Before running a report or audit that reads these traces, restore them from
the repository root:

```powershell
python scripts/restore_experiment_traces.py
```

The script checks the SHA-256 values recorded in
`results/summaries/trace_archives.json` and refuses to overwrite a differing
local trace. Compression does not change experiment records or metrics.
