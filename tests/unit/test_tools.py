"""Phase 7 (Tools / MCP) unit tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from freecode.config.settings import ApprovalSettings
from freecode.domain.actions import CommandAction, EditAction
from freecode.tools import ToolExecutor, action_needs_approval, is_readonly_command
from freecode.tools import filesystem


def test_is_readonly_allowlist():
    allow = ("git status", "pytest", "rg ")
    assert is_readonly_command("git status", allow)
    assert is_readonly_command("git status -sb", allow)
    assert is_readonly_command("pytest tests/", allow)
    assert not is_readonly_command("rm -rf /", allow)


def test_action_needs_approval_policies():
    ask = ApprovalSettings(default_policy="ask")
    auto = ApprovalSettings(default_policy="auto")
    ro = ApprovalSettings(default_policy="auto_readonly")
    edit = EditAction(file="a.py", old="x", new="y")
    cmd = CommandAction(command="git status")
    dangerous = CommandAction(command="rm -rf build")
    assert action_needs_approval(edit, ask) is True
    assert action_needs_approval(edit, auto) is False
    assert action_needs_approval(edit, ro) is True
    assert action_needs_approval(cmd, ro) is False
    assert action_needs_approval(dangerous, ro) is True


def test_read_write_list(tmp_path: Path):
    root = tmp_path
    (root / "hello.txt").write_text("hi", encoding="utf-8")
    r = filesystem.read_file(root, "hello.txt")
    assert r.ok and r.output == "hi"
    w = filesystem.write_file(root, "sub/a.txt", "data")
    assert w.ok and (root / "sub" / "a.txt").read_text() == "data"
    listing = filesystem.list_dir(root, ".")
    assert listing.ok
    assert "hello.txt" in listing.output


def test_path_escape_denied(tmp_path: Path):
    r = filesystem.read_file(tmp_path, "../outside")
    assert r.status == "error"


def test_apply_edit(tmp_path: Path):
    p = tmp_path / "f.py"
    p.write_text("abc", encoding="utf-8")
    r = filesystem.apply_edit(tmp_path, "f.py", "b", "B")
    assert r.ok
    assert p.read_text() == "aBc"


@pytest.mark.asyncio
async def test_executor_denies_mutating_without_approval(tmp_path: Path):
    ex = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto_readonly"))
    result = await ex.execute_action(
        EditAction(file="x.py", old="", new="print(1)\\n"),
        approved=False,
    )
    assert result.status == "denied"


@pytest.mark.asyncio
async def test_executor_applies_edit_when_approved(tmp_path: Path):
    ex = ToolExecutor(tmp_path, ApprovalSettings(default_policy="ask"))
    result = await ex.execute_action(
        EditAction(file="x.py", old="", new="print(1)\n"),
        approved=True,
    )
    assert result.ok
    assert (tmp_path / "x.py").read_text() == "print(1)\n"


@pytest.mark.asyncio
async def test_shell_echo(tmp_path: Path):
    ex = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto"))
    result = await ex.run_shell("echo hello", approved=True)
    assert result.ok
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_search_fallback(tmp_path: Path):
    (tmp_path / "a.py").write_text("alpha beta gamma", encoding="utf-8")
    ex = ToolExecutor(tmp_path)
    result = await ex.search("beta")
    assert result.ok
    assert "a.py" in result.output


def test_path_escapes_root(tmp_path):
    from freecode.tools.filesystem import path_escapes_root

    assert path_escapes_root(tmp_path, "inside.py") is None
    outside = path_escapes_root(tmp_path, "/tmp/definitely_outside_freecode")
    assert outside is not None
