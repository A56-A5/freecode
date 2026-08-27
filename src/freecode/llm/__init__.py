"""
llm/ - ApiFreeLLM transport layer.

ph-03: client + request/response models
ph-04: scheduler + cooldown + priority queue
ph-05: response protocol + repair
"""
from freecode.llm.client import ApiFreeLLMClient
from freecode.llm.protocol import AgentResponse, AgentStatus, ContextUpdate
from freecode.llm.queue import RequestPriority, RequestQueue
from freecode.llm.repair import extract_json_candidates, repair_chat_text, repair_response
from freecode.llm.request import ChatRequest
from freecode.llm.response import ChatResponse, ResponseFeatures
from freecode.llm.scheduler import (
    FakeClock,
    Scheduler,
    SchedulerSnapshot,
    SystemClock,
    TimerMode,
)

__all__ = [
    "AgentResponse",
    "AgentStatus",
    "ApiFreeLLMClient",
    "ChatRequest",
    "ChatResponse",
    "ContextUpdate",
    "FakeClock",
    "RequestPriority",
    "RequestQueue",
    "ResponseFeatures",
    "Scheduler",
    "SchedulerSnapshot",
    "SystemClock",
    "TimerMode",
    "extract_json_candidates",
    "repair_chat_text",
    "repair_response",
]
