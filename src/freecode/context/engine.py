"""
context.engine - assemble the smallest useful flat prompt for ApiFreeLLM.
"""
from __future__ import annotations

from pathlib import Path

from freecode.config.logging import get_logger
from freecode.config.settings import ContextSettings
from freecode.context.compress import compress_history, format_history
from freecode.context.index import ProjectIndex, build_index
from freecode.context.rank import read_snippets, select_relevant
from freecode.context.tokens import budget_from_settings, estimate_tokens, trim_to_budget
from freecode.context.coalesce import EventCoalescer
from freecode.domain.state import AgentState

log = get_logger(__name__)

_SYSTEM_HINT = (
    "You are FreeCode, a terminal coding agent. "
    "When possible, reply with JSON only of the form "
    '{"message":"...","actions":[],"status":"continue|done|needs_input",'
    '"context_update":{"facts":[]}}. '
    "Action types: edit {file,old,new}, command {command,reason}."
)


class ContextEngine:
    """
    Builds budgeted prompts from goal, facts, history, and relevant files.
    """

    def __init__(
        self,
        root: Path | str = ".",
        settings: ContextSettings | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.settings = settings or ContextSettings()
        self._index: ProjectIndex | None = None
        self.coalescer = EventCoalescer()

    def refresh_index(self) -> ProjectIndex:
        self._index = build_index(self.root)
        log.debug("indexed %d files under %s", len(self._index), self.root)
        return self._index

    @property
    def index(self) -> ProjectIndex:
        if self._index is None:
            self.refresh_index()
        assert self._index is not None
        return self._index

    def assemble(self, state: AgentState, user_text: str) -> str:
        """
        Produce a single string prompt within the token budget.
        """
        settings = self.settings
        cpt = settings.chars_per_token
        total_budget = budget_from_settings(settings)

        sections: list[str] = []
        used = 0

        def add(section: str) -> bool:
            nonlocal used
            cost = estimate_tokens(section, cpt)
            if used + cost > total_budget and sections:
                return False
            sections.append(section)
            used += cost
            return True

        add(_SYSTEM_HINT)

        if state.goal:
            add(f"Goal: {state.goal}")

        if state.facts:
            facts = state.facts[-20:]
            add("Known facts:\n" + "\n".join(f"- {f}" for f in facts))

        events_block = self.coalescer.coalesce_for_prompt(
            token_budget=max(200, int((total_budget - used) * 0.2)),
            chars_per_token=cpt,
            drain=True,
        )
        if events_block:
            add(events_block)

        # History: allocate ~35% of remaining budget
        remaining = max(0, total_budget - used)
        hist_budget = max(200, int(remaining * 0.35))
        # history already includes current user turn when called from AgentCore
        turns = compress_history(
            state.history,
            token_budget=hist_budget,
            chars_per_token=cpt,
        )
        # Avoid duplicating the final user message if we append it again
        if turns and turns[-1].role == "user" and turns[-1].content.strip() == user_text.strip():
            turns = turns[:-1]
        if turns:
            add("Recent conversation:\n" + format_history(turns))

        # Relevant files: ~40% of remaining after history
        remaining = max(0, total_budget - used)
        file_budget = max(200, int(remaining * 0.45))
        query = " ".join(filter(None, [state.goal or "", user_text, " ".join(state.facts[-5:])]))
        entries = select_relevant(self.index, query, limit=6)
        snippets = read_snippets(self.index, entries, max_chars_each=1000)
        if snippets:
            block_parts = ["Relevant project files:"]
            for rel, body in snippets:
                piece = f"--- {rel} ---\n{body}"
                cost = estimate_tokens("\n".join(block_parts + [piece]), cpt)
                if cost > file_budget and len(block_parts) > 1:
                    break
                block_parts.append(piece)
            add("\n".join(block_parts))

        add(f"User: {user_text}")

        prompt = "\n\n".join(sections)
        prompt = trim_to_budget(prompt, total_budget, cpt)
        log.debug(
            "assembled prompt tokens~%d budget=%d files=%d history_turns=%d",
            estimate_tokens(prompt, cpt),
            total_budget,
            len(snippets),
            len(turns),
        )
        return prompt

    def prompt_builder(self, state: AgentState, user_text: str) -> str:
        """Signature compatible with AgentCore build_prompt."""
        return self.assemble(state, user_text)
