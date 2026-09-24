"""Turn jev-bench TRAIN items into Laya training sequences.

  python -m jev_bench.finetune.prepare --run smoke-quarantine --tasks quarantine
  python -m jev_bench.finetune.prepare --run all-distill --tasks quarantine reachability license \
      --distill --max-len 2048 --head-max-len 256

Writes data/checkpoints/<run>/{train_items.pt, calib_items.pt, prep_meta.json}.
Test-split items (jev_bench.tasks.split_of) are never included.
"""
import argparse, json, os, random, collections
import torch
from laya.agent import Agent
from laya.common import build_sequence, render_options, QTYPES
from ..state import prepare_state
from jev_bench.tasks import load_task, read_items
from .common import resolve_base, load_cfg_tok
from .compact import compact_state

CKPT_ROOT = os.path.join("data", "checkpoints")


def load_distill(task: str) -> dict:
    p = os.path.join("results", "distill", f"jev__{task}.jsonl")
    if not os.path.exists(p):
        raise FileNotFoundError(f"--distill needs {p} (run jev_bench.run with --out results/distill)")
    out = {}
    for line in open(p):
        r = json.loads(line)
        if r.get("err") is None and r.get("raw"):
            out[r["id"]] = r["raw"]
    return out


def target_for(q: dict, label, raw: dict | None, w: float):
    """Probability vector in render_options order. One-hot from label, optionally mixed with Jev's
    distribution (raw) at weight w."""
    if q["t"] == "choice":
        keys = list(q["crit"].keys())
        hard = [1.0 if k == label else 0.0 for k in keys]
        soft = [float(raw.get("probabilities", {}).get(k, 0.0)) for k in keys] if raw else None
    elif q["t"] == "noul":
        p = 1.0 if label in (True, "true", "True", 1) else 0.0
        hard = [1.0 - p, p]
        soft = [1.0 - float(raw["noul"]), float(raw["noul"])] if raw and "noul" in raw else None
    else:
        raise ValueError("score questions are not used by jev-bench tasks")
    if soft and sum(soft) > 0:
        s = sum(soft); soft = [v / s for v in soft]
        t = [w * a + (1 - w) * b for a, b in zip(soft, hard)]
    else:
        t = hard
    s = sum(t)
    return [v / s for v in t]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--tasks", nargs="+", required=True)
    ap.add_argument("--base", default="convaiinnovations/laya")
    ap.add_argument("--subfolder", default="typed-decisions", help="'none' for the root checkpoint")
    ap.add_argument("--max-len", type=int, default=None, help="override cfg max_len (ModernBERT allows up to 8192)")
    ap.add_argument("--head-max-len", type=int, default=None)
    ap.add_argument("--state-chars", type=int, default=4000, help="cap on serialized state chars before tokenizing (0 = off)")
    ap.add_argument("--no-compact", action="store_true", help="disable task-aware compaction (reachability tree pruning)")
    ap.add_argument("--state-cap", type=int, default=None, help="fair mode: render state to prose and cap at N reference tokens (jev_bench.state.prepare_state); overrides --state-chars/--no-compact")
    ap.add_argument("--distill", action="store_true", help="soft targets from results/distill/jev__<task>.jsonl")
    ap.add_argument("--distill-weight", type=float, default=1.0)
    ap.add_argument("--calib-frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=20260922)
    a = ap.parse_args()
    sub = None if a.subfolder.lower() == "none" else a.subfolder
    model_dir = resolve_base(a.base, sub)
    cfg, tok = load_cfg_tok(model_dir)
    max_len = a.max_len or cfg.get("max_len", 512)
    head_max_len = a.head_max_len or cfg.get("head_max_len", 192)

    items, stats = [], collections.OrderedDict()
    for task in a.tasks:
        mod = load_task(task)
        q = Agent._to_internal(mod.QUESTION[mod.QKEY])
        k = len(render_options(q))
        raws = load_distill(task) if a.distill else {}
        n_ok = n_drop = n_soft = 0
        lens = []
        for it in read_items(task, "train"):
            assert it.meta.get("split") == "train"
            raw = raws.get(it.id)
            n_soft += raw is not None
            state = prepare_state(task, it.state, a.state_cap)[0] if a.state_cap else compact_state(it.state, a.state_chars, not a.no_compact)
            seq, markers = build_sequence(tok, state, q, max_len, head_max_len)
            if len(markers) != k:
                n_drop += 1
                continue
            target = target_for(q, it.label, raw, a.distill_weight)
            items.append({"ids": seq, "markers": markers, "qtype": QTYPES[q["t"]], "target": target,
                          "label": int(max(range(len(target)), key=target.__getitem__)), "task": task, "id": it.id})
            n_ok += 1; lens.append(len(seq))
        lens.sort()
        stats[task] = {"train_items": n_ok, "dropped_marker_mismatch": n_drop, "soft_targets": n_soft,
                       "seq_len_p50": lens[len(lens) // 2] if lens else 0, "seq_len_max": lens[-1] if lens else 0,
                       "hit_max_len": sum(l >= max_len for l in lens)}
        print(f"{task:13s} train={n_ok} dropped={n_drop} soft={n_soft} seq p50={stats[task]['seq_len_p50']} max={stats[task]['seq_len_max']} at_cap={stats[task]['hit_max_len']}")

    order = list(range(len(items)))
    random.Random(a.seed).shuffle(order)
    n_calib = min(400, int(len(items) * a.calib_frac))
    calib = [items[i] for i in sorted(order[:n_calib])]
    train = [items[i] for i in sorted(order[n_calib:])]
    out = os.path.join(CKPT_ROOT, a.run)
    os.makedirs(out, exist_ok=True)
    torch.save(train, os.path.join(out, "train_items.pt"))
    torch.save(calib, os.path.join(out, "calib_items.pt"))
    meta = {"run": a.run, "tasks": a.tasks, "base": a.base, "subfolder": sub, "base_dir": model_dir,
            "max_len": max_len, "head_max_len": head_max_len, "state_chars": a.state_chars, "compact": not a.no_compact, "state_cap": a.state_cap,
            "distill": a.distill, "distill_weight": a.distill_weight, "n_train": len(train), "n_calib": len(calib), "per_task": stats}
    json.dump(meta, open(os.path.join(out, "prep_meta.json"), "w"), indent=1)
    print(f"wrote {out}: {len(train)} train, {len(calib)} calib  (max_len={max_len}, head_max_len={head_max_len})")


if __name__ == "__main__":
    main()
