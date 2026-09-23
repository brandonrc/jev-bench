"""Engine interface. Each engine exposes:

    name: str
    def answer(state: dict, question: dict, qkey: str) -> Answer   # one item, one question
    optional: def answer_batch(states: list[dict], question: dict, qkey: str) -> list[Answer]

Answer.pred is a str (choice) or bool (noul); Answer.conf is P(pred) in [0,1] where available.
"""
from dataclasses import dataclass, field

@dataclass
class Answer:
    pred: object
    conf: float
    raw: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)   # input_tokens/output_tokens/cache_read when the engine reports them

def decode(answers: dict, qkey: str) -> Answer:
    """Turn a Jev/Laya `answers` map into an Answer."""
    a = answers[qkey]
    if a.get("type") == "noul" or "noul" in a:
        p = float(a["noul"]); return Answer(pred=p >= 0.5, conf=max(p, 1 - p), raw=a)
    return Answer(pred=a["choice"], conf=float(a.get("confidence", 0.0)), raw=a)

def load_engine(spec: str):
    """spec: 'jev' | 'laya:<subfolder or base>[@cuda:N]' | 'laya-http:<url>' | 'claude:<model>'"""
    kind, _, arg = spec.partition(":")
    if kind == "jev":
        from .jev import Jev; return Jev()
    if kind == "laya":
        from .laya import Laya; ck, _, dev = arg.partition("@"); return Laya(ck or "base", dev or "cuda:0")
    if kind == "laya-http":
        from .laya import LayaHTTP; return LayaHTTP(arg or "http://localhost:8000")
    if kind == "claude":
        from .claude import Claude; return Claude(arg or "claude-haiku-4-5")
    raise ValueError(spec)
