from pydantic import BaseModel, Field
from typing import Any, Optional, Literal

class AgentResponse(BaseModel):
    agent: str
    status: Literal["ok", "error"] = "ok"
    result: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    needs_approval: bool = False
    error_message: Optional[str] = None

class AgentRequest(BaseModel):
    code: str
    task_id: str