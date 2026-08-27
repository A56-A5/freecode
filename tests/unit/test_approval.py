"""Phase 11 (Approval + security) unit tests."""
from __future__ import annotations

from freecode.config.settings import ApprovalSettings
from freecode.domain.actions import CommandAction, EditAction
from freecode.security import ApprovalGate, Decision, RiskLevel, classify_action, classify_command


def test_classify_readonly():
    settings = ApprovalSettings()
    a = CommandAction(command="git status")
    assert classify_action(a, settings) is RiskLevel.READONLY


def test_classify_git_mutation():
    assert classify_command("git commit -m 'x'") is RiskLevel.GIT_MUTATION
    assert classify_command("git push origin main") is RiskLevel.GIT_MUTATION


def test_classify_destructive():
    assert classify_command("rm -rf build") is RiskLevel.DESTRUCTIVE
    assert classify_command("git reset --hard") is RiskLevel.DESTRUCTIVE


def test_classify_edit():
    assert classify_action(EditAction(file="a.py", old="x", new="y")) is RiskLevel.WRITE


def test_gate_auto_readonly():
    gate = ApprovalGate(ApprovalSettings(default_policy="auto_readonly"))
    ro = gate.decide(CommandAction(command="git status"))
    assert ro.decision is Decision.ALLOW
    edit = gate.decide(EditAction(file="a.py", old="", new="x"))
    assert edit.decision is Decision.PROMPT
    danger = gate.decide(CommandAction(command="rm -rf /tmp/x"))
    assert danger.decision is Decision.PROMPT


def test_gate_auto_allows_all():
    gate = ApprovalGate(ApprovalSettings(default_policy="auto"))
    assert gate.decide(EditAction(file="a.py", old="", new="x")).decision is Decision.ALLOW
    assert gate.authorize(CommandAction(command="echo hi")) is True


def test_gate_ask_prompts():
    gate = ApprovalGate(ApprovalSettings(default_policy="ask"))
    assert gate.decide(CommandAction(command="echo hi")).decision is Decision.PROMPT
    # no prompt_fn → deny
    assert gate.authorize(CommandAction(command="echo hi")) is False


def test_gate_prompt_fn_allow():
    gate = ApprovalGate(
        ApprovalSettings(default_policy="ask"),
        prompt_fn=lambda req: True,
    )
    assert gate.authorize(EditAction(file="a.py", old="", new="1")) is True


def test_gate_prompt_fn_deny():
    gate = ApprovalGate(
        ApprovalSettings(default_policy="ask"),
        prompt_fn=lambda req: False,
    )
    assert gate.authorize(EditAction(file="a.py", old="", new="1")) is False
