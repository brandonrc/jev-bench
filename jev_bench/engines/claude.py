"""Claude via the Messages API with structured outputs, shaped like a Jev answer.
Credential: ANTHROPIC_API_KEY, or an `ant auth login` profile (picked up automatically)."""
import json
from typing import Literal
from pydantic import BaseModel, Field
import anthropic
from . import Answer

class NoulOut(BaseModel):
    answer: bool
    probability_true: float = Field(ge=0, le=1, description="calibrated P(true); 0.5 = coin flip")

def choice_model(options):
    class ChoiceOut(BaseModel):
        choice: Literal[tuple(options)]  # type: ignore[valid-type]
        confidence: float = Field(ge=0, le=1, description="calibrated P(choice is correct)")
    return ChoiceOut

class Claude:
    def __init__(self, model="claude-haiku-4-5", effort=None):
        self.name = model; self.model = model; self.effort = effort
        self.client = anthropic.Anthropic(max_retries=4)
        self._models = {}
    def _system(self, spec):
        rubric = "\n".join(f"- {k}: {v}" for k, v in spec["criteria"].items()) if spec.get("criteria") else ""
        return (f"You are a decision function inside a package-registry curation pipeline. Answer the question about the STATE "
                f"with the structured output only.\nQuestion: {spec['instructions']}\nOptions:\n{rubric}\n"
                f"Give a calibrated probability/confidence: 0.5 means a coin flip, 0.99 means near-certain.")
    def answer(self, state, question, qkey):
        spec = question[qkey]
        if spec["type"] == "noul": Model = NoulOut
        else: Model = self._models.setdefault(qkey + str(tuple(spec["criteria"])), choice_model(list(spec["criteria"])))
        kw = {}
        if self.effort: kw["output_config"] = {"effort": self.effort}
        if self.model.startswith("claude-haiku"): kw["temperature"] = 0
        r = self.client.messages.parse(
            model=self.model, max_tokens=512,
            system=[{"type": "text", "text": self._system(spec), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": "STATE:\n" + json.dumps(state, indent=1)}],
            output_format=Model, **kw)
        if r.stop_reason == "refusal": raise RuntimeError("refusal")
        o = r.parsed_output
        usage = {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens, "cache_read": r.usage.cache_read_input_tokens or 0}
        if isinstance(o, NoulOut):
            p = o.probability_true; return Answer(pred=p >= 0.5, conf=max(p, 1 - p), raw=o.model_dump(), usage=usage)
        return Answer(pred=o.choice, conf=o.confidence, raw=o.model_dump(), usage=usage)
