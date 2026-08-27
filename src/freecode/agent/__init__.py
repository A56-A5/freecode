"""
agent/ - Agent Core orchestration (ph-06).
"""
from freecode.agent.core import AgentCore, AgentTurnResult, default_prompt
from freecode.agent.loop import AgentLoop, LoopOutcome, StepOutcome
from freecode.agent.lifecycle import LifecycleError, apply_response, phase_from_status, transition
from freecode.domain.state import AgentPhase, AgentState, TurnRecord

__all__ = [
    "AgentCore",
    "AgentLoop",
    "LoopOutcome",
    "StepOutcome",
    "AgentPhase",
    "AgentState",
    "AgentTurnResult",
    "LifecycleError",
    "TurnRecord",
    "apply_response",
    "default_prompt",
    "phase_from_status",
    "transition",
]
