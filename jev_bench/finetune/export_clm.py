"""Export jev-bench items in the typed-decisions parquet layout that CLM's train/finetune.py --task choice reads:
<out>/<workflow>/train.parquet and test.parquet with columns id, state, questions, gold (JSON strings), workflow.
Train rows = our train split; test rows = our test split (CLM evaluates on it but never trains on it)."""
import argparse, json, os
import pyarrow as pa, pyarrow.parquet as pq
from ..tasks import TASK_NAMES, load_task, read_items
from ..state import prepare_state

def rows_for(task, split, cap=None):
    mod = load_task(task); q = mod.QUESTION; qk = mod.QKEY
    out = []
    for it in read_items(task, split):
        label = it.label
        if isinstance(label, bool): label = "true" if label else "false"
        st = prepare_state(task, it.state, cap)[0] if cap else it.state
        # A dict state is stored as JSON (CLM's loader parses it back). A prose string must be stored RAW:
        # json.dumps would keep the quotes and \n escapes as literal text, and the head would train on a
        # different string than the server embeds at inference (found the hard way: 15-point served gap).
        out.append({"id": it.id, "workflow": task, "state": st if isinstance(st, str) else json.dumps(st), "questions": json.dumps(q),
                    "gold": json.dumps({qk: {"label": label}})})
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="data/clm-typed"); ap.add_argument("--tasks", nargs="+", default=TASK_NAMES); ap.add_argument("--state-cap", type=int, default=None); a = ap.parse_args()
    d = os.path.join(a.out, "all"); os.makedirs(d, exist_ok=True)
    for split in ("train", "test"):
        rows = [r for t in a.tasks for r in rows_for(t, split, a.state_cap)]
        pq.write_table(pa.Table.from_pylist(rows), os.path.join(d, f"{split}.parquet"))
        print(split, len(rows), "rows ->", os.path.join(d, f"{split}.parquet"))
    for t in a.tasks:  # per-task dirs too, so single-task heads are possible
        dt = os.path.join(a.out, t); os.makedirs(dt, exist_ok=True)
        for split in ("train", "test"): pq.write_table(pa.Table.from_pylist(rows_for(t, split, a.state_cap)), os.path.join(dt, f"{split}.parquet"))

if __name__ == "__main__":
    main()
