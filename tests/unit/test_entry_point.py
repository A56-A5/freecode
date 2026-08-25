"""
Phase 0 (Foundation) tests.

Deliberately minimal: this phase's only job is "the project can be
installed and launched through the package entry point." Later phases add
their own test files under tests/unit/ - this file should stay small.
"""
from freecode import __version__
from freecode.main import run


def test_version_is_set():
    assert __version__ == "0.0.1"


def test_run_returns_success_exit_code(capsys):
    exit_code = run()
    assert exit_code == 0


def test_run_prints_version_banner(capsys):
    run()
    captured = capsys.readouterr()
    assert "freecode" in captured.out
    assert __version__ in captured.out


def test_domain_package_has_no_forbidden_imports():
    """
    Guard rail for the dependency direction described in FreeCode.md §8.2:
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
