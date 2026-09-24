"""Export jev-bench items in the typed-decisions parquet layout that CLM's train/finetune.py --task choice reads:
<out>/<workflow>/train.parquet and test.parquet with columns id, state, questions, gold (JSON strings), workflow.
Train rows = our train split; test rows = our test split (CLM evaluates on it but never trains on it)."""
import argparse, json, os
import pyarrow as pa, pyarrow.parquet as pq
from ..tasks import TASK_NAMES, load_task, read_items

def rows_for(task, split):
    mod = load_task(task); q = mod.QUESTION; qk = mod.QKEY
    out = []
    for it in read_items(task, split):
        label = it.label
        if isinstance(label, bool): label = "true" if label else "false"
        out.append({"id": it.id, "workflow": task, "state": json.dumps(it.state), "questions": json.dumps(q),
                    "gold": json.dumps({qk: {"label": label}})})
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="data/clm-typed"); ap.add_argument("--tasks", nargs="+", default=TASK_NAMES); a = ap.parse_args()
    d = os.path.join(a.out, "all"); os.makedirs(d, exist_ok=True)
    for split in ("train", "test"):
        rows = [r for t in a.tasks for r in rows_for(t, split)]
        pq.write_table(pa.Table.from_pylist(rows), os.path.join(d, f"{split}.parquet"))
        print(split, len(rows), "rows ->", os.path.join(d, f"{split}.parquet"))
    for t in a.tasks:  # per-task dirs too, so single-task heads are possible
        dt = os.path.join(a.out, t); os.makedirs(dt, exist_ok=True)
        for split in ("train", "test"): pq.write_table(pa.Table.from_pylist(rows_for(t, split)), os.path.join(dt, f"{split}.parquet"))

if __name__ == "__main__":
    main()
