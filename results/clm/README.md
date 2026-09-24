# CLM notes

- `embedder-send-ids.patch`: an experimental switch that makes clm-serve tokenize like the training script. It was
  written on the theory that served and training embeddings differed; an A/B test showed they are identical
  (cosine 1.0000), so the patch is unnecessary and is kept only as a record.
- The real cause of the gap between CLM's own evaluation and our served numbers was our export
  (`jev_bench/finetune/export_clm.py`): prose states were stored JSON-quoted, and CLM's loader keeps a JSON string
  literal as text. Fixed 2026-09-24; runs `fair2-s{1,2,3}` are on the corrected data. Rows from the affected runs are
  under `results/fair/ablations/clm-ft-jsonquoted-states/`.
