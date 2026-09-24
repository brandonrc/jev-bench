"""One rendering of an item's state for every engine, capped to a fixed token budget.

Fairness rule: every model receives exactly the same string. Objects render as `key: value` lines
(nested values as JSON), reachability trees are pruned to paths that reach the finding's package
(same as the fine-tune compaction), and the text is cut at STATE_TOKENS reference tokens, counted
with the ModernBERT tokenizer that Laya uses (the tightest window in the comparison)."""
import json, functools

STATE_TOKENS_DEFAULT = 768   # + up to 256 for question/options = the 1,024 budget

@functools.lru_cache(maxsize=1)
def _tok():
    from transformers import AutoTokenizer
    from huggingface_hub import snapshot_download
    import os
    d = snapshot_download("convaiinnovations/laya", allow_patterns=["tokenizer/*", "typed-decisions/tokenizer/*"])
    p = os.path.join(d, "typed-decisions", "tokenizer")
    return AutoTokenizer.from_pretrained(p if os.path.isdir(p) else os.path.join(d, "tokenizer"))

def render(state) -> str:
    if isinstance(state, str): return state
    lines = []
    for k, v in state.items():
        if isinstance(v, (dict, list)): v = json.dumps(v, ensure_ascii=False)
        lines.append(f"{k}: {v}")
    return "\n".join(lines)

def cap(text: str, n_tokens: int) -> tuple[str, int, bool]:
    """Return (capped_text, token_count_before, truncated?)."""
    ids = _tok()(text, add_special_tokens=False)["input_ids"]
    if len(ids) <= n_tokens: return text, len(ids), False
    return _tok().decode(ids[:n_tokens]), len(ids), True

def prepare_state(task: str, state, n_tokens: int = STATE_TOKENS_DEFAULT):
    if task == "reachability":
        from .finetune.compact import compact_reachability
        state = compact_reachability(state)
    return cap(render(state), n_tokens)
