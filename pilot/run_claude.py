"""Claude leg of the pilot. Same items, same rubric, structured output shaped like a Jev answer.
Usage: ANTHROPIC_API_KEY=... python run_claude.py [model]   (default claude-haiku-4-5)"""
import json, os, sys, time, statistics, collections
from typing import Literal
from pydantic import BaseModel, Field
import anthropic
from data import TASKS

MODEL = sys.argv[1] if len(sys.argv) > 1 else "claude-haiku-4-5"
client = anthropic.Anthropic()

def make_model(q, qkey):
    spec = q[qkey]
    if spec["type"] == "noul":
        class Noul(BaseModel):
            answer: bool
            probability_true: float = Field(ge=0, le=1)
        return Noul
    opts = tuple(spec["criteria"].keys())
    class Choice(BaseModel):
        choice: Literal[opts]  # type: ignore[valid-type]
        confidence: float = Field(ge=0, le=1)
    return Choice

def system_prompt(q, qkey):
    spec = q[qkey]
    rubric = "\n".join(f"- {k}: {v}" for k, v in spec["criteria"].items()) if spec.get("criteria") else ""
    return (f"You are a decision function inside a package-registry curation pipeline. Answer the question about the STATE "
            f"with the structured output only.\nQuestion: {spec['instructions']}\nOptions:\n{rubric}\n"
            f"Give a calibrated probability/confidence: 0.5 means a coin flip, 0.99 means near-certain.")

def ask(state, q, qkey, Model):
    r = client.messages.parse(
        model=MODEL, max_tokens=256,
        system=[{"type": "text", "text": system_prompt(q, qkey), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "STATE:\n" + json.dumps(state, indent=1)}],
        output_format=Model,
    )
    if r.stop_reason == "refusal": raise RuntimeError("refusal")
    o = r.parsed_output
    if hasattr(o, "probability_true"):
        p = o.probability_true; return (p >= 0.5, max(p, 1 - p), r.usage)
    return (o.choice, o.confidence, r.usage)

out = open("pilot_results.jsonl", "a"); eng = MODEL
summary = collections.defaultdict(lambda: {"n": 0, "correct": 0, "lat": [], "cc": [], "cw": [], "in": 0, "out": 0, "cache": 0})
for tname, (gen, q, qkey) in TASKS.items():
    Model = make_model(q, qkey)
    for it in gen():
        t0 = time.perf_counter()
        try:
            pred, conf, usage = ask(it["state"], q, qkey, Model); err = None
        except Exception as e:
            pred, conf, usage, err = None, 0.0, None, f"{type(e).__name__}: {str(e)[:200]}"
            if isinstance(e, anthropic.AuthenticationError): print(err); sys.exit(2)
        ms = (time.perf_counter() - t0) * 1000; ok = pred == it["label"]
        s = summary[(tname, eng)]; s["n"] += 1; s["correct"] += ok; s["lat"].append(ms); (s["cc"] if ok else s["cw"]).append(conf)
        if usage: s["in"] += usage.input_tokens; s["out"] += usage.output_tokens; s["cache"] += (usage.cache_read_input_tokens or 0)
        out.write(json.dumps({"task": tname, "engine": eng, "id": it["id"], "label": it["label"], "pred": pred, "conf": conf, "ms": round(ms, 1), "variant": it.get("variant"), "err": err}) + "\n")
    print(f"{tname:10s} {eng} done", flush=True)
out.close()
print("\n| task | engine | n | acc | p50 ms | p95 ms | conf right | conf wrong | in tok | out tok | cache-read tok |")
for (t, e), s in summary.items():
    lat = sorted(s["lat"]); mc = lambda l: f"{statistics.mean(l):.2f}" if l else "-"
    print(f"| {t} | {e} | {s['n']} | {s['correct']/s['n']:.2f} | {lat[len(lat)//2]:.0f} | {lat[int(len(lat)*0.95)-1]:.0f} | {mc(s['cc'])} | {mc(s['cw'])} | {s['in']} | {s['out']} | {s['cache']} |")
