import os, time, httpx
from . import Answer, decode

class Jev:
    name = "jev"
    def __init__(self, model="jev-latest"):
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key: raise SystemExit("TYPESAFE_API_KEY not set")
        self.model = model
        self.client = httpx.Client(base_url="https://api.typesafe.ai", headers={"Authorization": f"Bearer {key}"}, timeout=120)
    def _post(self, body):
        for attempt in range(5):
            r = self.client.post("/v1/systemone", json=body)
            if r.status_code in (429, 529): time.sleep(min(2 ** attempt, 20)); continue
            r.raise_for_status(); return r.json()
        raise RuntimeError(f"jev {r.status_code}: {r.text[:200]}")
    def answer(self, state, question, qkey):
        j = self._post({"model": self.model, "state": state, "questions": question})
        a = decode(j["answers"], qkey); a.usage = j.get("usage", {}); a.raw["model"] = j.get("model"); return a
    def answer_multi(self, state, questions):
        """Several questions on one state in one call (fan-out)."""
        j = self._post({"model": self.model, "state": state, "questions": questions})
        return {k: decode(j["answers"], k) for k in questions}, j.get("usage", {})
