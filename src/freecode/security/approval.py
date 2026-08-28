"""
security.approval - ApprovalGate (policy decisions without TUI).

Returns allow / deny / needs_prompt so the UI (or tests) can react.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from freecode.config.settings import ApprovalPolicy, ApprovalSettings
from freecode.domain.actions import Action, CommandAction, EditAction
from freecode.domain.events import approval_result_event
from freecode.security.policy import RiskLevel, classify_action, risk_label


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    action: Action
    risk: RiskLevel
    summary: str
    decision: Decision

    def to_prompt_text(self) -> str:
        return (
            f"Allow this {risk_label(self.risk)} action?\n\n"
            f"{self.summary}\n\n"
            f"[a] Allow   [d] Deny"
        )


PromptFn = Callable[[ApprovalRequest], bool]
# prompt returns True = allow, False = deny


class ApprovalGate:
    """
    Pure policy + optional interactive prompt callback.

    TUI supplies `prompt_fn`; unit tests call `decide()` without it.
    """

    def __init__(
        self,
        settings: ApprovalSettings | None = None,
        *,
        prompt_fn: PromptFn | None = None,
        coalescer=None,
    ) -> None:
        self.settings = settings or ApprovalSettings()
        self.prompt_fn = prompt_fn
        self.coalescer = coalescer
        self.project_root = None

    def decide(self, action: Action) -> ApprovalRequest:
        risk = classify_action(action, self.settings, project_root=self.project_root)
        summary = _summarize(action)
        policy: ApprovalPolicy = self.settings.default_policy

        if policy == "auto":
            decision = Decision.ALLOW
        elif policy == "ask":
            decision = Decision.PROMPT if risk != RiskLevel.READONLY else Decision.ALLOW
        else:  # auto_readonly
            if risk == RiskLevel.READONLY:
                decision = Decision.ALLOW
            else:
                decision = Decision.PROMPT

        # Destructive / outside-root always prompts unless fully auto
        if risk in (RiskLevel.DESTRUCTIVE, RiskLevel.OUTSIDE_ROOT, RiskLevel.WEB) and policy != "auto":
            decision = Decision.PROMPT

        return ApprovalRequest(
            action=action,
            risk=risk,
            summary=summary,
            decision=decision,
        )

    def authorize(self, action: Action) -> bool:
        """
        Return True if the action may run.

        For PROMPT decisions, calls prompt_fn if set; otherwise denies
        (safe default when no UI is attached).
        """
        req = self.decide(action)
        if req.decision is Decision.ALLOW:
            self._emit(True, req.summary)
            return True
        if req.decision is Decision.DENY:
            self._emit(False, req.summary)
            return False
        # PROMPT
        if self.prompt_fn is None:
            self._emit(False, req.summary)
            return False
        allowed = bool(self.prompt_fn(req))
        self._emit(allowed, req.summary)
        return allowed

    def _emit(self, approved: bool, summary: str) -> None:
        if self.coalescer is not None:
            self.coalescer.emit(approval_result_event(approved, summary))


def _summarize(action: Action) -> str:
    if isinstance(action, EditAction):
        return f"edit {action.file}"
    if isinstance(action, CommandAction):
        reason = f" ({action.reason})" if action.reason else ""
        return f"shell: {action.command}{reason}"
    return repr(action)
