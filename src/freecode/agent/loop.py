"""
agent.loop - multi-step turn helper for full integration (ph-12).

After tools run, pending coalesced events can feed a continuation turn
without the user re-typing. Respects interrupt and a max-step cap so we
never burn free-tier slots in a tight loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from freecode.agent.core import AgentCore, AgentTurnResult
from freecode.config.logging import get_logger
from freecode.domain.actions import Action
from freecode.domain.state import AgentPhase
from freecode.llm.protocol import AgentResponse
from freecode.tools.executor import ToolExecutor
from freecode.tools.results import ToolResult

log = get_logger(__name__)


@dataclass
class StepOutcome:
    turn: AgentTurnResult
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class LoopOutcome:
    steps: list[StepOutcome] = field(default_factory=list)
    stopped_reason: str = "done"

    @property
    def last(self) -> AgentTurnResult | None:
        return self.steps[-1].turn if self.steps else None


class AgentLoop:
    """
    Optional multi-step runner used by the TUI integration path.

    Single-step is the default; continuation only when the model returns
    status=continue after tools and max_steps allows it.
    """

    def __init__(
        self,
        core: AgentCore,
        tools: ToolExecutor,
        *,
        authorize,
        max_steps: int = 3,
    ) -> None:
        self.core = core
        self.tools = tools
        self.authorize = authorize  # async (action) -> bool
        self.max_steps = max_steps

    async def run_user_message(self, text: str) -> LoopOutcome:
        outcome = LoopOutcome()
        first = await self.core.handle_user_message(text)
        tool_results = await self._maybe_run_actions(first.response.actions)
        outcome.steps.append(StepOutcome(turn=first, tool_results=tool_results))

        steps = 1
        while (
            steps < self.max_steps
            and first.response.status == "continue"
            and tool_results
            and self.core.phase not in (AgentPhase.INTERRUPTED, AgentPhase.ERROR, AgentPhase.DONE)
            and not self.core.state.phase is AgentPhase.NEEDS_INPUT
        ):
            # Continuation: model sees coalesced tool events via ContextEngine
            cont = await self.core.handle_user_message(
                "[system] Tool results are in context. Continue the task or set status done."
            )
            tool_results = await self._maybe_run_actions(cont.response.actions)
            outcome.steps.append(StepOutcome(turn=cont, tool_results=tool_results))
            first = cont
            steps += 1
            if cont.response.status in ("done", "needs_input"):
                break
            if not cont.response.actions:
                break

        if self.core.phase is AgentPhase.INTERRUPTED:
            outcome.stopped_reason = "interrupted"
        elif self.core.phase is AgentPhase.ERROR:
            outcome.stopped_reason = "error"
        elif self.core.phase is AgentPhase.NEEDS_INPUT:
            outcome.stopped_reason = "needs_input"
        elif steps >= self.max_steps:
            outcome.stopped_reason = "max_steps"
        else:
            outcome.stopped_reason = first.response.status
        return outcome

    async def _maybe_run_actions(self, actions: tuple[Action, ...]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for action in actions:
            ok = await self.authorize(action)
            if not ok:
                results.append(
                    ToolResult(
                        tool=getattr(action, "type", "action"),
                        status="denied",
                        error="user denied",
                        mutating=True,
                    )
                )
                continue
            results.append(await self.tools.execute_action(action, approved=True))
        return results
