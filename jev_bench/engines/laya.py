import httpx
from . import Answer, decode

class Laya:
    def __init__(self, checkpoint="base", device="cuda:0"):
        import laya
        sub = None if checkpoint in ("base", "english") else checkpoint
        self.name = f"laya-{checkpoint}"
        self.agent = laya.load("convaiinnovations/laya", subfolder=sub, device=device)
        self.max_len = self.agent.cfg.get("max_len")
    def answer(self, state, question, qkey):
        return decode(self.agent.predict(state, question)["answers"], qkey)
    def answer_batch(self, states, question, qkey, batch_size=64):
        return [decode(r["answers"], qkey) for r in self.agent.predict_batch(states, question, batch_size=batch_size)]

class LayaHTTP:
    """laya-serve (POST /v1/systemone). Configure the server with LAYA_PORT/LAYA_DEVICE/LAYA_MODELS env vars; CLI flags are ignored."""
    def __init__(self, url="http://localhost:8000", model="typed-decisions"):
        self.name = f"laya-http-{model}"; self.model = model
        self.client = httpx.Client(base_url=url, timeout=60)
    def answer(self, state, question, qkey):
        r = self.client.post("/v1/systemone", json={"state": state, "questions": question, "model": self.model}); r.raise_for_status()
        return decode(r.json()["answers"], qkey)
