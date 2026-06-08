from pydantic import BaseModel, ConfigDict


class LLMParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0
    num_ctx: int | None = None
    num_predict: int | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    format: str | None = None
    keep_alive: str | int | None = None
    think: bool | None = None
    max_tokens: int | None = None


AGENT_DEFAULT = {
    "temperature": 0,
    "top_p": 0.1,
    "repeat_penalty": 1.1,
    "keep_alive": "1000h",
    "num_ctx":8192,
}