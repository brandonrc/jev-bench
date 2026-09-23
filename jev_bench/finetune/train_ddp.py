"""RLCD fine-tune of a Laya checkpoint on sequences from prepare.py (adapted from Laya's Kaggle notebook).

  torchrun --standalone --nproc_per_node=2 -m jev_bench.finetune.train_ddp --run smoke-quarantine --epochs 2

Reads data/checkpoints/<run>/{train_items.pt, calib_items.pt, prep_meta.json}; writes the fine-tuned
checkpoint to data/checkpoints/<run>/model (loadable with laya.load(path)). Loss = GRPO-style policy
gradient over noisy logits with a strictly proper scoring reward + soft cross-entropy, as in the notebook.
"""
import argparse, json, os, sys, time, random, shutil
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from safetensors.torch import load_file, save_file
from laya.common import build_model, proper_reward, QTYPES, TEMP_MIN, TEMP_MAX
from .common import resolve_base, load_cfg_tok

CKPT_ROOT = os.path.join("data", "checkpoints")


def collate(items, pad_id):
    n, L = len(items), max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    ids = torch.full((n, L), pad_id, dtype=torch.long); att = torch.zeros((n, L), dtype=torch.long)
    mpos = torch.zeros((n, kmax), dtype=torch.long); mmask = torch.zeros((n, kmax), dtype=torch.bool)
    target = torch.zeros((n, kmax), dtype=torch.float32)
    for i, it in enumerate(items):
        ids[i, :len(it["ids"])] = torch.tensor(it["ids"]); att[i, :len(it["ids"])] = 1
        k = len(it["markers"]); mpos[i, :k] = torch.tensor(it["markers"]); mmask[i, :k] = True
        target[i, :len(it["target"])] = torch.tensor(it["target"], dtype=torch.float32)
    return {"input_ids": ids, "attention_mask": att, "marker_pos": mpos, "marker_mask": mmask, "target": target,
            "qtype": torch.tensor([it["qtype"] for it in items]), "label": torch.tensor([it["label"] for it in items])}


def token_batches(items, micro_batch, max_tokens):
    """Greedy micro-batches under both a sequence count and a padded-token budget (n * longest)."""
    out, cur, cur_max = [], [], 0
    for it in items:
        L = len(it["ids"])
        if cur and (len(cur) >= micro_batch or max(cur_max, L) * (len(cur) + 1) > max_tokens):
            out.append(cur); cur, cur_max = [], 0
        cur.append(it); cur_max = max(cur_max, L)
    if cur: out.append(cur)
    return out


def fit_one_temp(sel):
    if len(sel) < 10: return 1.0
    kmax = max(len(z) for z, _ in sel)
    Z = torch.full((len(sel), kmax), -1e4); T = torch.zeros((len(sel), kmax))
    for i, (z, t) in enumerate(sel):
        Z[i, :len(z)] = torch.tensor(z); T[i, :len(t)] = torch.tensor(t, dtype=torch.float32)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)
    def closure():
        opt.zero_grad(); loss = -(T * torch.log_softmax(Z / log_t.exp(), -1)).sum(-1).mean(); loss.backward(); return loss
    opt.step(closure)
    return float(torch.clamp(log_t.exp(), TEMP_MIN, TEMP_MAX).item())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--output", default=None, help="default data/checkpoints/<run>/model")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--micro-batch", type=int, default=8)
    ap.add_argument("--max-tokens-per-batch", type=int, default=16384, help="padded tokens per micro-batch per GPU")
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--group-size", type=int, default=4)
    ap.add_argument("--lr-encoder", type=float, default=2.5e-5)
    ap.add_argument("--lr-head", type=float, default=1.0e-4)
    ap.add_argument("--sigma-start", type=float, default=0.4)
    ap.add_argument("--sigma-end", type=float, default=0.1)
    ap.add_argument("--max-len", type=int, default=None, help="override; default from prep_meta.json")
    ap.add_argument("--head-max-len", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    from datetime import timedelta
    dist.init_process_group("nccl", timeout=timedelta(minutes=3))
    rank, world = dist.get_rank(), dist.get_world_size()
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    torch.cuda.set_device(local_rank); device = torch.device("cuda", local_rank)

    run_dir = os.path.join(CKPT_ROOT, a.run)
    meta = json.load(open(os.path.join(run_dir, "prep_meta.json")))
    output = a.output or os.path.join(run_dir, "model")
    model_dir = resolve_base(meta["base"], meta["subfolder"])
    cfg, tok = load_cfg_tok(model_dir)
    max_len = a.max_len or meta["max_len"]; head_max_len = a.head_max_len or meta["head_max_len"]
    cfg.update({"max_len": max_len, "head_max_len": head_max_len, "gradient_checkpointing": True,
                "max_tokens_per_batch": a.max_tokens_per_batch})

    model = build_model(cfg, encoder_dir=os.path.join(model_dir, "encoder"))
    model.load_state_dict(load_file(os.path.join(model_dir, "model.safetensors")), strict=True)
    # ModernBERT's reference_compile defaults to "auto" and torch.compiles the encoder on CUDA; with
    # variable-length batches that recompiles per shape and is several times slower (Laya's own
    # fine-tune guide flags this). Keep the eager path, as laya.Agent does at inference.
    try:
        model.encoder.config.reference_compile = False
    except Exception:
        pass
    model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.head_checkpointing = True
    model.to(device).train()
    ddp = DDP(model, device_ids=[local_rank], find_unused_parameters=True)

    train_items = torch.load(os.path.join(run_dir, "train_items.pt"), weights_only=False)
    calib_items = torch.load(os.path.join(run_dir, "calib_items.pt"), weights_only=False)
    my_items = train_items[rank::world]

    enc_p = [p for n, p in ddp.named_parameters() if "encoder." in n]
    head_p = [p for n, p in ddp.named_parameters() if "encoder." not in n]
    opt = torch.optim.AdamW([{"params": enc_p, "lr": a.lr_encoder}, {"params": head_p, "lr": a.lr_head}], weight_decay=0.01)
    steps_per_epoch = max(1, len(token_batches(my_items, a.micro_batch, a.max_tokens_per_batch)) // a.grad_accum)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, steps_per_epoch * a.epochs), eta_min=1e-6)
    scaler = torch.amp.GradScaler("cuda", enabled=True)
    if rank == 0:
        print(f"train={len(train_items)} calib={len(calib_items)} per-rank={len(my_items)} epochs={a.epochs} "
              f"max_len={max_len} head_max_len={head_max_len} micro={a.micro_batch} tok/batch={a.max_tokens_per_batch} "
              f"accum={a.grad_accum} world={world}", flush=True)
    t0 = time.time(); history = []
    for epoch in range(a.epochs):
        random.seed(a.seed + epoch + rank); random.shuffle(my_items)
        batches = token_batches(my_items, a.micro_batch, a.max_tokens_per_batch)
        # Every rank must run the same number of forward/backward passes or DDP's gradient
        # all-reduce on one rank meets the epoch-end barrier on the other and NCCL deadlocks
        # (token-budget batching and uneven sharding both make counts differ). Trim to the minimum.
        n_common = torch.tensor([len(batches)], device=device); dist.all_reduce(n_common, op=dist.ReduceOp.MIN)
        batches = batches[: int(n_common.item())]
        sigma = a.sigma_start + (a.sigma_end - a.sigma_start) * (epoch / max(1, a.epochs - 1))
        opt.zero_grad(set_to_none=True); ep_loss = ep_rew = 0.0; n_b = 0; step_t = time.time()
        for bi, chunk in enumerate(batches):
            b = collate(chunk, tok.pad_token_id)
            with torch.autocast("cuda", dtype=torch.float16):
                logits, act = ddp(b["input_ids"].to(device), b["attention_mask"].to(device), b["marker_pos"].to(device),
                                  b["marker_mask"].to(device), b["qtype"].to(device))
            logits = logits.float(); mask = b["marker_mask"].to(device); k = mask.sum(-1, keepdim=True).float()
            target = b["target"].to(device)
            eps = torch.randn((a.group_size,) + logits.shape, device=device) * sigma * mask
            eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
            z = logits.detach().unsqueeze(0) + eps
            q = torch.softmax(z.masked_fill(~mask, -1e4), -1)
            with torch.no_grad():
                r = proper_reward(q, target.unsqueeze(0), b["qtype"].to(device), mask, w_sph=0.75, w_rps=1.0)
                adv = (r - r.mean(0, keepdim=True)); adv = adv / (adv.std() + 1e-6)
            logp = -(((z - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma ** 2)
            loss_rl = -(adv * logp).mean()
            loss_ce = -(target * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
            loss = (loss_rl + loss_ce) / a.grad_accum + 0.0 * act.sum()
            scaler.scale(loss).backward()
            if (bi + 1) % a.grad_accum == 0 or bi + 1 == len(batches):
                scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(ddp.parameters(), 1.0)
                scaler.step(opt); scaler.update(); sched.step(); opt.zero_grad(set_to_none=True)
            ep_loss += loss.item() * a.grad_accum; ep_rew += r.mean().item(); n_b += 1
            if rank == 0 and n_b % 20 == 0:
                print(f"  ep {epoch+1} step {n_b}/{len(batches)} loss {loss.item()*a.grad_accum:.4f} reward {r.mean().item():.3f} "
                      f"{(time.time()-step_t)/20*1000:.0f} ms/step lr {sched.get_last_lr()[0]:.2e}", flush=True); step_t = time.time()
        rec = {"epoch": epoch + 1, "avg_loss": ep_loss / max(1, n_b), "avg_reward": ep_rew / max(1, n_b), "elapsed_s": time.time() - t0,
               "steps": n_b, "peak_mem_gb": round(torch.cuda.max_memory_allocated(device) / 1e9, 2)}
        history.append(rec)
        if rank == 0: print(f"=== epoch {epoch+1}/{a.epochs} loss {rec['avg_loss']:.4f} reward {rec['avg_reward']:.3f} {rec['elapsed_s']:.0f}s "
                            f"{rec['steps']} micro-steps peak_mem {rec['peak_mem_gb']} GB", flush=True)
        dist.barrier()

    if rank == 0:
        del opt, scaler, sched; torch.cuda.empty_cache(); model.eval()
        preds = []
        with torch.no_grad():
            for c in range(0, len(calib_items), 16):
                chunk = calib_items[c:c + 16]; cb = collate(chunk, tok.pad_token_id)
                with torch.autocast("cuda", dtype=torch.float16):
                    l, _ = model(cb["input_ids"].to(device), cb["attention_mask"].to(device), cb["marker_pos"].to(device),
                                 cb["marker_mask"].to(device), cb["qtype"].to(device))
                l = l.float().cpu().numpy()
                for i, it in enumerate(chunk): preds.append((it["qtype"], l[i, :len(it["markers"])], it["target"]))
        temps = [1.0, 1.0, 1.0]
        for qt in range(3):
            sel = [(z, t) for q_t, z, t in preds if q_t == qt]
            if sel: temps[qt] = fit_one_temp(sel)
        calib_acc = sum(int(z.argmax()) == int(max(range(len(t)), key=t.__getitem__)) for _, z, t in preds) / max(1, len(preds))
        print(f"calibration: n={len(preds)} acc={calib_acc:.3f} temps(choice,score,noul)={[round(t,3) for t in temps]}", flush=True)
        os.makedirs(output, exist_ok=True)
        save_file({k: v.half().contiguous().cpu() for k, v in model.state_dict().items()}, os.path.join(output, "model.safetensors"))
        model.encoder.config.save_pretrained(os.path.join(output, "encoder"))
        shutil.copytree(os.path.join(model_dir, "tokenizer"), os.path.join(output, "tokenizer"), dirs_exist_ok=True)
        cfg.update({"fine_tuned": True, "model_name": f"laya-ft-{a.run}", "temperature": temps,
                    "jev_bench": {"run": a.run, "tasks": meta["tasks"], "state_chars": meta["state_chars"], "compact": meta["compact"],
                                  "distill": meta["distill"], "base": meta["base"], "subfolder": meta["subfolder"]},
                    "training": {"epochs": a.epochs, "world_size": world, "n_train": len(train_items), "n_calib": len(calib_items),
                                 "seconds": round(time.time() - t0), "history": history, "calib_acc": calib_acc,
                                 "micro_batch": a.micro_batch, "max_tokens_per_batch": a.max_tokens_per_batch, "grad_accum": a.grad_accum}})
        cfg.pop("temperature_by_options", None)
        json.dump(cfg, open(os.path.join(output, "rl_agent_config.json"), "w"), indent=2)
        print(f"saved {output} ({time.time()-t0:.0f}s total)", flush=True)
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
