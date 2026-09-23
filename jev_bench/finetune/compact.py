"""State compaction applied identically at training (prepare.py) and inference (engines/laya.py for
fine-tuned checkpoints). Laya reads at most cfg["max_len"] tokens, so long states are cut in code.

The checkpoint's rl_agent_config.json carries {"jev_bench": {"state_chars": N, "compact": true}} so
inference reproduces exactly what training saw.
"""
import json, re
from laya.common import serialize_state


def _tree_lines(tree):
    if isinstance(tree, list):
        return [str(x) for x in tree]
    if isinstance(tree, str):
        return tree.splitlines()
    return [json.dumps(tree, ensure_ascii=False)]


def compact_reachability(state: dict) -> dict:
    """Keep only resolved_tree lines on some path from the root to the finding's package (the
    ancestor subgraph), plus every line naming the package itself. Everything the reachability rule
    needs survives; the unrelated 90% of the tree does not."""
    try:
        pkg = state["finding"]["package"]
        declared = state["declared"]
        lines = _tree_lines(declared.get("resolved_tree", []))
    except (KeyError, TypeError):
        return state
    edge = re.compile(r"^\s*(\S+)\s*->\s*(\S+?)@(\S+)\s*(\[[^\]]*\])?")
    parsed = []
    for ln in lines:
        m = edge.match(ln)
        parsed.append((m.group(1), m.group(2)) if m else (None, None))
    keep = set()
    wanted = {pkg}
    changed = True
    while changed:
        changed = False
        for i, (parent, child) in enumerate(parsed):
            if i in keep or child is None:
                continue
            if child in wanted or pkg in lines[i]:
                keep.add(i)
                if parent not in wanted and parent != "root":
                    wanted.add(parent)
                changed = True
    kept = [lines[i] for i in sorted(keep)]
    if not kept:
        kept = [f"(no resolved_tree line mentions {pkg})"]
    new_declared = dict(declared)
    new_declared["resolved_tree"] = kept
    new_declared["resolved_tree_note"] = f"{len(kept)} of {len(lines)} edges shown: only paths that reach {pkg}"
    out = dict(state)
    out["declared"] = new_declared
    return out


def compact_state(state, state_chars: int = 4000, compact: bool = True):
    """Return the state as Laya will see it: task-aware compaction, then a character cap on the
    serialized form. Returns a str when a cut was made (serialize_state passes str through)."""
    if compact and isinstance(state, dict) and "finding" in state and "declared" in state:
        state = compact_reachability(state)
    s = serialize_state(state)
    if state_chars and len(s) > state_chars:
        return s[:state_chars]
    return state
