"""
agent.core - Agent Core orchestration (ph-06).

Owns goals, state, interpretation of repaired LLM output, and continuation
signals. Does NOT implement HTTP, shell, filesystem, or TUI rendering.

Dependencies are injected:
  - send(message: str) -> ChatResponse   (usually Scheduler-gated client)
  - optional prompt builder (default: flat user text + light context)

Tools/MCP execution and approval gates arrive in later phases; pending
actions are recorded on state for those layers to consume.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from freecode.agent.lifecycle import apply_response, transition
from freecode.config.logging import get_logger
from freecode.domain.errors import LLMError, LLMRateLimitError, LLMServerError
from freecode.domain.state import AgentPhase, AgentState
from freecode.llm.protocol import AgentResponse
from freecode.llm.repair import repair_response
from freecode.llm.response import ChatResponse

log = get_logger(__name__)

SendFn = Callable[[str], Awaitable[ChatResponse]]
PromptFn = Callable[[AgentState, str], str]


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    """Outcome of one user → model turn."""

    response: AgentResponse
    phase: AgentPhase
    chat: ChatResponse | None = None
    error: str | None = None

    @property
    def message(self) -> str:
        if self.error:
            return self.error
        return self.response.message or self.response.raw_text or ""


def default_prompt(state: AgentState, user_text: str) -> str:
    """
    Minimal flat prompt for the single-string API.

    Later phases replace this with the Prompt Compiler + Context Engine.
    """
    parts: list[str] = []
    if state.goal and state.goal != user_text:
        parts.append(f"Goal: {state.goal}")
    if state.facts:
        parts.append("Known facts:\n" + "\n".join(f"- {f}" for f in state.facts[-12:]))
    # Recent history (exclude the user turn we are about to add if already present)
    recent = state.history[-6:]
    if recent:
        lines = []
        for turn in recent:
            prefix = "User" if turn.role == "user" else "Assistant"
            lines.append(f"{prefix}: {turn.content}")
        parts.append("Recent conversation:\n" + "\n".join(lines))
    parts.append(f"User: {user_text}")
    parts.append(
        "Respond helpfully. When possible, reply with JSON only of the form "
        '{"message":"...","actions":[],"status":"continue|done|needs_input",'
        '"context_update":{"facts":[]}}.'
    )
    return "\n\n".join(parts)


class AgentCore:
    """
    Orchestrates a single agent session.

    Usage:
        core = AgentCore(send=client.send)
        result = await core.handle_user_message("fix the bug")
        print(result.message, result.phase)
    """

    def __init__(
        self,
        send: SendFn,
        *,
        state: AgentState | None = None,
        build_prompt: PromptFn | None = None,
    ) -> None:
        self._send = send
        self._build_prompt = build_prompt or default_prompt
        self.state = state if state is not None else AgentState()
        self._interrupted = False

    @property
    def phase(self) -> AgentPhase:
        return self.state.phase

    @property
    def is_busy(self) -> bool:
        return self.state.phase is AgentPhase.RUNNING

    def set_goal(self, goal: str) -> None:
        goal = goal.strip()
        if not goal:
            return
        self.state.goal = goal

    def interrupt(self) -> None:
        """Request cancellation of the in-flight turn (cooperative)."""
        self._interrupted = True
        if self.state.phase is AgentPhase.RUNNING:
            try:
                transition(self.state, AgentPhase.INTERRUPTED)
            except Exception:
                self.state.phase = AgentPhase.INTERRUPTED
        log.info("agent interrupt requested")

    def clear_interrupt(self) -> None:
        self._interrupted = False

    def reset(self) -> None:
        self.state = AgentState()
        self._interrupted = False

    async def handle_user_message(self, text: str) -> AgentTurnResult:
        """
        Run one reasoning turn for a user message.

        Steps: record user → build prompt → send → repair → update state.
        Does not execute actions (tools/MCP are later phases).
        """
        text = (text or "").strip()
        if not text:
            empty = AgentResponse.plain_text_fallback("")
            return AgentTurnResult(response=empty, phase=self.state.phase, error="empty message")

        self.clear_interrupt()
        if self.state.goal is None:
            self.set_goal(text)
        self.state.append_user(text)
        transition(self.state, AgentPhase.RUNNING)

        prompt = self._build_prompt(self.state, text)
        log.debug("agent turn=%d prompt_chars=%d", self.state.turn + 1, len(prompt))

        if self._interrupted:
            transition(self.state, AgentPhase.INTERRUPTED)
            resp = AgentResponse.plain_text_fallback("Interrupted.")
            return AgentTurnResult(response=resp, phase=self.state.phase, error="interrupted")

        try:
            chat = await self._send(prompt)
        except LLMRateLimitError as exc:
            self.state.phase = AgentPhase.ERROR
            self.state.error = str(exc)
            resp = AgentResponse.plain_text_fallback(f"Rate limited: {exc}")
            return AgentTurnResult(response=resp, phase=self.state.phase, error=str(exc))
        except LLMServerError as exc:
            self.state.phase = AgentPhase.ERROR
            self.state.error = str(exc)
            resp = AgentResponse.plain_text_fallback(f"Server error: {exc}")
            return AgentTurnResult(response=resp, phase=self.state.phase, error=str(exc))
        except LLMError as exc:
            self.state.phase = AgentPhase.ERROR
            self.state.error = str(exc)
            resp = AgentResponse.plain_text_fallback(f"LLM error: {exc}")
            return AgentTurnResult(response=resp, phase=self.state.phase, error=str(exc))

        if self._interrupted:
            transition(self.state, AgentPhase.INTERRUPTED)
            resp = AgentResponse.plain_text_fallback("Interrupted after response.")
            return AgentTurnResult(response=resp, phase=self.state.phase, chat=chat, error="interrupted")

        parsed = repair_response(chat.text)
        phase = apply_response(self.state, parsed)
        log.debug(
            "agent applied status=%s phase=%s actions=%d fallback=%s",
            parsed.status,
            phase.value,
            len(parsed.actions),
            parsed.fallback,
        )
        return AgentTurnResult(response=parsed, phase=phase, chat=chat)
