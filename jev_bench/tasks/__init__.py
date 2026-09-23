"""Task interface. Every task module in this package exposes:

    NAME: str                      # e.g. "license"
    QUESTION: dict                 # Jev/Laya question map with exactly one key, e.g. {"family": {"type": "choice", ...}}
    QKEY: str                      # that key
    def build(n: int, seed: int) -> list[Item]   # deterministic; may download/cache public data under data/<NAME>/

Item.state is the JSON object sent verbatim as the Jev/Laya `state` and as the Claude user message.
Item.label is the ground truth: a str option name for choice, a bool for noul.
Item.meta holds anything useful for slicing results (variant, source, difficulty, token bucket...).
"""
from dataclasses import dataclass, field
import importlib, os, json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

@dataclass
class Item:
    task: str
    id: str
    state: dict
    label: object
    meta: dict = field(default_factory=dict)

TASK_NAMES = ["license", "typosquat", "curation", "reachability", "quarantine"]

def load_task(name: str):
    return importlib.import_module(f"jev_bench.tasks.{name}")

def cache_path(task: str, filename: str) -> str:
    d = os.path.join(DATA_DIR, task); os.makedirs(d, exist_ok=True); return os.path.join(d, filename)

def write_items(task: str, items: list[Item]) -> str:
    p = cache_path(task, "items.jsonl")
    with open(p, "w") as f:
        for it in items: f.write(json.dumps(it.__dict__) + "\n")
    return p

def read_items(task: str) -> list[Item]:
    with open(cache_path(task, "items.jsonl")) as f:
        return [Item(**json.loads(l)) for l in f]
