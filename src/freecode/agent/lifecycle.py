"""
agent.lifecycle - phase transitions for Agent Core.

Centralizes legal transitions so the core does not scatter ad-hoc flags.
"""
from __future__ import annotations

from freecode.domain.state import AgentPhase, AgentState
from freecode.llm.protocol import AgentResponse, AgentStatus


_ALLOWED: dict[AgentPhase, frozenset[AgentPhase]] = {
    AgentPhase.IDLE: frozenset(
        {AgentPhase.RUNNING, AgentPhase.INTERRUPTED, AgentPhase.ERROR}
    ),
    AgentPhase.RUNNING: frozenset(
        {
            AgentPhase.WAITING_APPROVAL,
            AgentPhase.NEEDS_INPUT,
            AgentPhase.DONE,
            AgentPhase.RUNNING,
            AgentPhase.ERROR,
            AgentPhase.INTERRUPTED,
            AgentPhase.IDLE,
        }
    ),
    AgentPhase.WAITING_APPROVAL: frozenset(
        {AgentPhase.RUNNING, AgentPhase.DONE, AgentPhase.IDLE, AgentPhase.INTERRUPTED, AgentPhase.ERROR}
    ),
    AgentPhase.NEEDS_INPUT: frozenset(
        {AgentPhase.RUNNING, AgentPhase.IDLE, AgentPhase.INTERRUPTED, AgentPhase.ERROR}
    ),
    AgentPhase.DONE: frozenset({AgentPhase.IDLE, AgentPhase.RUNNING, AgentPhase.INTERRUPTED}),
    AgentPhase.ERROR: frozenset({AgentPhase.IDLE, AgentPhase.RUNNING, AgentPhase.INTERRUPTED}),
    AgentPhase.INTERRUPTED: frozenset({AgentPhase.IDLE, AgentPhase.RUNNING}),
}


class LifecycleError(ValueError):
    """Illegal phase transition."""


def transition(state: AgentState, new_phase: AgentPhase) -> None:
    allowed = _ALLOWED.get(state.phase, frozenset())
    if new_phase not in allowed and new_phase != state.phase:
        raise LifecycleError(f"cannot transition {state.phase.value} → {new_phase.value}")
    state.phase = new_phase


def phase_from_status(status: AgentStatus, *, has_actions: bool) -> AgentPhase:
    """Map structured agent status (+ pending actions) to a lifecycle phase."""
    if status == "done":
        return AgentPhase.DONE
    if status == "needs_input":
        return AgentPhase.NEEDS_INPUT
    if has_actions:
        return AgentPhase.WAITING_APPROVAL
    return AgentPhase.RUNNING


def apply_response(state: AgentState, response: AgentResponse) -> AgentPhase:
    """Update state fields from a parsed response and set the new phase."""
    state.turn += 1
    state.last_message = response.message
    state.last_status = response.status
    state.last_fallback = response.fallback
    state.pending_actions = response.actions
    state.merge_facts(response.context_update.facts)
    state.append_assistant(response.message)
    state.error = None
    new_phase = phase_from_status(response.status, has_actions=bool(response.actions))
    transition(state, new_phase)
    return new_phase
