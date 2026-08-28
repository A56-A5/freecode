
"""Plan mode, undo, @mentions, web tool."""
from __future__ import annotations

from pathlib import Path

import pytest

from freecode.context.mentions import expand_mentions, extract_mentions
from freecode.domain.actions import WebAction, parse_action
from freecode.tools.executor import ToolExecutor
from freecode.config.settings import ApprovalSettings


def test_extract_mentions():
    assert extract_mentions("see @src/main.py and @docs/") == ["src/main.py", "docs/"]


def test_expand_file_mention(tmp_path: Path):
    f = tmp_path / "hello.py"
    f.write_text("print(1)\n", encoding="utf-8")
    block = expand_mentions(tmp_path, "look at @hello.py")
    assert "print(1)" in block
    assert "hello.py" in block


def test_parse_web_action():
    a = parse_action({"type": "web", "url": "https://example.com", "reason": "docs"})
    assert isinstance(a, WebAction)
    assert a.url.startswith("https://")


@pytest.mark.asyncio
async def test_plan_mode_skips_edit(tmp_path: Path):
    (tmp_path / "a.py").write_text("old\n", encoding="utf-8")
    tools = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto"))
    tools.plan_mode = True
    from freecode.domain.actions import EditAction
    r = await tools.execute_action(EditAction(file="a.py", old="old", new="new"), approved=True)
    assert r.ok
    assert "plan" in (r.output or "").lower() or r.data.get("planned")
    assert (tmp_path / "a.py").read_text() == "old\n"


@pytest.mark.asyncio
async def test_undo_restores_edit(tmp_path: Path):
    (tmp_path / "a.py").write_text("v1\n", encoding="utf-8")
    tools = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto"))
    tools.begin_action_batch()
    from freecode.domain.actions import EditAction
    r = await tools.execute_action(EditAction(file="a.py", old="v1", new="v2"), approved=True)
    assert r.ok
    tools.commit_undo_batch()
    assert (tmp_path / "a.py").read_text() == "v2\n"
    u = tools.undo_last_batch()
    assert u.ok
    assert (tmp_path / "a.py").read_text() == "v1\n"
