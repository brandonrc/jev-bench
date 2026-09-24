"""Contrastive-LM CLM served by `clm-serve` (POST /v1/systemone, Jev wire format).
Server-side time comes back in the X-CLM-Latency-Ms header; we record it in usage so network
and queueing can be separated from inference."""
import httpx
from . import Answer, decode

class CLMHTTP:
    def __init__(self, url="http://localhost:8700", model="clm-latest"):
        self.name = "clm-8b" if model == "clm-latest" else model; self.model = model
        self.client = httpx.Client(base_url=url, timeout=120)
    def answer(self, state, question, qkey):
        r = self.client.post("/v1/systemone", json={"state": state, "questions": question, "model": self.model}); r.raise_for_status()
        j = r.json(); a = decode(j["answers"], qkey)
        a.usage = dict(j.get("usage", {})); a.usage["server_ms"] = float(r.headers.get("X-CLM-Latency-Ms", "nan")); a.raw["model"] = j.get("model")
        return a
