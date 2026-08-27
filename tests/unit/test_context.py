"""Phase 8 (Context Engine) unit tests."""
from __future__ import annotations

from pathlib import Path

from freecode.config.settings import ContextSettings
from freecode.context import ContextEngine, build_index, estimate_tokens, trim_to_budget
from freecode.context.compress import compress_history, format_history
from freecode.context.rank import select_relevant, tokenize
from freecode.domain.state import AgentState, TurnRecord


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1  # 4 chars / 4


def test_trim_to_budget():
    text = "a" * 1000
    out = trim_to_budget(text, budget=10, chars_per_token=4.0)
    assert len(out) < len(text)
    assert "truncated" in out


def test_build_index(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text("def login():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# project\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.py").write_text("skip", encoding="utf-8")
    idx = build_index(tmp_path)
    paths = {e.rel_path for e in idx.files}
    assert "src/auth.py" in paths
    assert "README.md" in paths
    assert not any(".venv" in p for p in paths)


def test_select_relevant(tmp_path: Path):
    (tmp_path / "auth.py").write_text("login", encoding="utf-8")
    (tmp_path / "utils.py").write_text("helper", encoding="utf-8")
    idx = build_index(tmp_path)
    hits = select_relevant(idx, "fix auth login", limit=5, min_score=0.5)
    assert hits
    assert hits[0].rel_path == "auth.py"


def test_compress_history():
    history = [
        TurnRecord(role="user", content="a" * 100),
        TurnRecord(role="assistant", content="b" * 100),
        TurnRecord(role="user", content="c" * 100),
    ]
    kept = compress_history(history, token_budget=30, chars_per_token=4.0)
    assert len(kept) >= 1
    assert kept[-1].content.startswith("c")


def test_engine_assemble(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    engine = ContextEngine(tmp_path, ContextSettings(token_budget=2000, context_window=4000))
    state = AgentState(goal="say hi")
    state.facts = ("use python",)
    state.append_user("hello")
    state.append_assistant("hi there")
    prompt = engine.assemble(state, "print something")
    assert "FreeCode" in prompt
    assert "print something" in prompt
    assert "use python" in prompt
    assert estimate_tokens(prompt) < 5000


def test_tokenize():
    assert "auth_helper" in tokenize("fix Auth_helper")
    assert "fix" in tokenize("fix Auth_helper")
