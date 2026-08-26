"""
Phase 0 (Foundation) tests.

Note: run() launches the real Textual app as of ph-01, so we can't call
it directly in a test without blocking on an interactive event loop -
instead we verify the wiring (run() calls tui.app.run_tui()) with a
patch. TUI-specific behavior lives in tests/unit/test_tui.py.
"""
from unittest.mock import patch

from freecode import __version__


def test_version_is_set():
    assert __version__ == "0.0.1"


def test_run_launches_the_tui():
    with patch("freecode.tui.app.run_tui", return_value=0) as mock_run_tui:
        from freecode.main import run

        exit_code = run()

    mock_run_tui.assert_called_once()
    assert exit_code == 0


def test_domain_package_has_no_forbidden_imports():
    """
    Guard rail for the dependency direction described in FreeCode.md 8.2:
    domain/ must not depend on tui, llm, agent, tools, mcp, context,
    storage, or security.
    """
    import ast
    import pathlib

    domain_dir = pathlib.Path(__file__).parents[2] / "src" / "freecode" / "domain"
    forbidden = {"tui", "llm", "agent", "tools", "mcp", "context", "storage", "security"}

    for py_file in domain_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                top_level = node.module.split(".")[0]
                assert top_level not in forbidden, (
                    f"{py_file.name} imports from '{node.module}' - "
                    f"domain/ must stay dependency-free of {forbidden}"
                )
