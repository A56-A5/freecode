"""
Phase 5 (Response protocol + repair) unit tests.
"""
from __future__ import annotations

import json

import pytest

from freecode.domain.actions import CommandAction, EditAction, parse_action
from freecode.llm.protocol import AgentResponse, ContextUpdate
from freecode.llm.repair import extract_json_candidates, repair_response


class TestParseAction:
    def test_edit(self):
        a = parse_action(
            {"type": "edit", "file": "a.py", "old": "x", "new": "y"}
        )
        assert isinstance(a, EditAction)
        assert a.file == "a.py"
        assert a.old == "x"
        assert a.new == "y"

    def test_command(self):
        a = parse_action(
            {"type": "command", "command": "pytest", "reason": "check"}
        )
        assert isinstance(a, CommandAction)
        assert a.command == "pytest"
        assert a.reason == "check"

    def test_unknown_type(self):
        with pytest.raises(ValueError, match="unknown action type"):
            parse_action({"type": "delete", "path": "x"})

    def test_edit_requires_file(self):
        with pytest.raises(ValueError, match="file"):
            parse_action({"type": "edit", "old": "", "new": ""})


class TestAgentResponseFromMapping:
    def test_full_payload(self):
        data = {
            "message": "Fixed auth",
            "actions": [
                {
                    "type": "edit",
                    "file": "src/auth.py",
                    "old": "a",
                    "new": "b",
                },
                {
                    "type": "command",
                    "command": "pytest tests/test_auth.py",
                    "reason": "verify",
                },
            ],
            "context_update": {"facts": ["auth uses JWT"]},
            "status": "continue",
        }
        resp = AgentResponse.from_mapping(data)
        assert resp.message == "Fixed auth"
        assert resp.status == "continue"
        assert resp.fallback is False
        assert len(resp.actions) == 2
        assert isinstance(resp.actions[0], EditAction)
        assert isinstance(resp.actions[1], CommandAction)
        assert resp.context_update.facts == ("auth uses JWT",)

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="status"):
            AgentResponse.from_mapping({"message": "x", "status": "nope"})

    def test_plain_text_fallback_factory(self):
        resp = AgentResponse.plain_text_fallback("hello world")
        assert resp.fallback is True
        assert resp.message == "hello world"
        assert resp.actions == ()
        assert resp.status == "continue"


class TestExtractCandidates:
    def test_pure_json(self):
        text = '{"message": "x", "status": "done"}'
        cands = extract_json_candidates(text)
        assert text in cands

    def test_fenced_json(self):
        text = 'Here you go:\n```json\n{"message": "ok", "status": "done"}\n```\n'
        cands = extract_json_candidates(text)
        assert any('"message": "ok"' in c for c in cands)

    def test_prose_with_object(self):
        text = 'Sure, plan below.\n{"message": "plan", "status": "continue", "actions": []}\nThanks'
        cands = extract_json_candidates(text)
        assert any(c.startswith("{") and c.endswith("}") for c in cands)

    def test_empty(self):
        assert extract_json_candidates("") == []
        assert extract_json_candidates("   ") == []


class TestRepairResponse:
    def test_strict_json(self):
        payload = {
            "message": "hi",
            "actions": [],
            "status": "done",
        }
        resp = repair_response(json.dumps(payload))
        assert resp.fallback is False
        assert resp.message == "hi"
        assert resp.status == "done"

    def test_fenced_with_prose(self):
        text = (
            "I'll make the change.\n"
            "```json\n"
            '{"message": "edited", "status": "continue", '
            '"actions": [{"type": "edit", "file": "a.py", "old": "1", "new": "2"}]}\n'
            "```\n"
            "Let me know."
        )
        resp = repair_response(text)
        assert resp.fallback is False
        assert resp.message == "edited"
        assert len(resp.actions) == 1
        assert isinstance(resp.actions[0], EditAction)
        assert resp.actions[0].file == "a.py"

    def test_embedded_object_in_prose(self):
        text = (
            'Result:\n{"message": "done work", "status": "done", "actions": []}\n'
        )
        resp = repair_response(text)
        assert resp.fallback is False
        assert resp.message == "done work"
        assert resp.status == "done"

    def test_plain_text_fallback(self):
        resp = repair_response("I couldn't format JSON this time, sorry.")
        assert resp.fallback is True
        assert "couldn't format" in resp.message
        assert resp.actions == ()
        assert resp.status == "continue"

    def test_malformed_json_falls_back(self):
        resp = repair_response('{"message": "oops", "status": ')
        assert resp.fallback is True

    def test_invalid_action_falls_back_or_skips_bad_candidate(self):
        # Valid-looking JSON but bad action type -> fallback
        text = json.dumps(
            {
                "message": "x",
                "status": "continue",
                "actions": [{"type": "explode"}],
            }
        )
        resp = repair_response(text)
        assert resp.fallback is True

    def test_empty_string(self):
        resp = repair_response("")
        assert resp.fallback is True
        assert resp.message == ""

    def test_context_update_facts(self):
        text = json.dumps(
            {
                "message": "note",
                "status": "continue",
                "actions": [],
                "context_update": {"facts": ["a", "b"]},
            }
        )
        resp = repair_response(text)
        assert resp.context_update.facts == ("a", "b")

    def test_no_second_llm_call_on_failure(self):
        """Contract: failed parse returns fallback; does not raise or retry."""
        resp = repair_response("not json at all {{{")
        assert isinstance(resp, AgentResponse)
        assert resp.fallback is True
