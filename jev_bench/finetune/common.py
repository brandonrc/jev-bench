"""Shared helpers for prepare.py / train_ddp.py."""
import json, os
from huggingface_hub import snapshot_download
from laya.agent import _fix_tokenizer_config, _load_tokenizer


def resolve_base(base: str, subfolder: str | None) -> str:
    """Local dir or hub id (+subfolder) -> directory holding rl_agent_config.json."""
    if os.path.isdir(base):
        d = base
    else:
        prefix = f"{subfolder}/" if subfolder else ""
        d = snapshot_download(base, allow_patterns=[prefix + n for n in
                              ("rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*")])
    if subfolder:
        d = os.path.join(d, subfolder)
    if not os.path.exists(os.path.join(d, "rl_agent_config.json")):
        raise FileNotFoundError(f"no rl_agent_config.json under {d}")
    _fix_tokenizer_config(d)
    return d


def load_cfg_tok(model_dir: str):
    with open(os.path.join(model_dir, "rl_agent_config.json")) as f:
        cfg = json.load(f)
    tok = _load_tokenizer(os.path.join(model_dir, "tokenizer"), cfg)
    return cfg, tok
