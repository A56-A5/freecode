"""
freecode.cli - Command-line interface and subcommands.

Provides CLI entry points for FreeCode, including:
- Main TUI app
- MCP server (for use with Claude, Cursor, etc.)
- Setup wizard for configuration
- Debugging utilities
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def run_mcp_subcommand(args: list[str]) -> int:
    """Run the MCP server subcommand."""
    from freecode.mcp import run_mcp_server

    project_root = args[0] if args else "."
    try:
        await run_mcp_server(project_root)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_tui_subcommand(args: list[str]) -> int:
    """Run the main TUI subcommand (synchronous — do not wrap in asyncio.run)."""
    from freecode.config import get_logger, load_config, setup_logging
    from freecode.tui.app import run_tui

    config = load_config()
    setup_logging(config)
    log = get_logger("main")
    if config.llm.api_keys or config.llm.groq_api_keys:
        log.info("live LLM mode (API key present)")
    else:
        log.warning("no API key — set FREECODE_API_KEY or GROQ_API_KEY")
    return run_tui(config)


async def run_setup_subcommand(args: list[str]) -> int:
    """Run the setup wizard subcommand."""
    try:
        await run_setup_wizard()
        return 0
    except KeyboardInterrupt:
        print("\nSetup cancelled")
        return 0
    except Exception as e:
        print(f"Setup error: {e}", file=sys.stderr)
        return 1


async def run_setup_wizard() -> None:
    """Interactive setup wizard for FreeCode configuration."""
    from pathlib import Path
    import json

    freecode_dir = Path.home() / ".freecode"
    config_path = freecode_dir / "config.toml"

    print("\n" + "=" * 60)
    print("FreeCode Setup Wizard")
    print("=" * 60)

    # Create .freecode directory if needed
    freecode_dir.mkdir(exist_ok=True)

    print("\n📋 Configuration Summary")
    print("-" * 60)

    # Check API keys
    print("\n1️⃣ API Keys")
    has_apifreellm = bool(__import__("os").getenv("FREECODE_API_KEY"))
    has_groq = bool(__import__("os").getenv("GROQ_API_KEY"))

    if has_apifreellm:
        print("   ✓ ApiFreeLLM key found")
    else:
        print("   ✗ ApiFreeLLM key NOT set")
        print("   Set: export FREECODE_API_KEY=\"your-key\"")

    if has_groq:
        print("   ✓ Groq key found")
    else:
        print("   ℹ Groq key optional (faster, no rate limit floor)")
        print("   Set: export GROQ_API_KEY=\"gsk_...\"")

    # Check config file
    print("\n2️⃣ Configuration File")
    if config_path.exists():
        print(f"   ✓ Config found: {config_path}")
    else:
        print(f"   ℹ No config yet. Will use defaults.")
        print(f"   Create: {config_path}")

    # Check theme
    print("\n3️⃣ Color Theme")
    theme_path = freecode_dir / "theme.toml"
    if theme_path.exists():
        print(f"   ✓ Custom theme: {theme_path}")
    else:
        print("   ℹ Using default theme")

    # Show next steps
    print("\n" + "=" * 60)
    print("📌 Next Steps")
    print("=" * 60)

    if not (has_apifreellm or has_groq):
        print("\n1. Set an API key:")
        print("   export FREECODE_API_KEY=\"your-key\"")
        print("   # From https://apifreellm.com (free, no signup)")
        print("\n   OR for faster responses:")
        print("   export GROQ_API_KEY=\"gsk_...\"")
        print("   # From https://console.groq.com (free)")

    print("\n2. Launch FreeCode:")
    print("   freecode")

    print("\n3. Use with Claude Desktop:")
    print("   freecode mcp .")
    print("   # Then add to ~/.claude/claude_desktop_config.json")

    print("\n4. Read documentation:")
    print("   - ./README.md — Overview & features")
    print("   - ./FreeCode.md — Architecture & design")
    print("   - ./docs/MCP.md — MCP server guide")

    # Optional: create default config
    if not config_path.exists():
        should_create = input("\nCreate default config at ~/.freecode/config.toml? (y/n) ").lower()
        if should_create == "y":
            default_config = """# FreeCode Configuration

[approval]
# auto: approve all actions automatically
# ask: prompt for approval on mutating ops
# auto_readonly: auto-approve read-only, ask for mutating
default_policy = "ask"

# Commands that are considered "read-only"
readonly_allowlist = ["git", "grep", "ls", "cat", "head", "tail", "find"]

[context]
# Token budget for LLM context (ApiFreeLLM free tier uses this)
token_budget = 8000

[scheduler]
# Cooldown floor in seconds (ApiFreeLLM free tier ~20-25s)
cooldown_floor_seconds = 20

[logging]
# Log level: DEBUG, INFO, WARNING, ERROR
level = "INFO"
"""
            config_path.write_text(default_config)
            print(f"\n✓ Created: {config_path}")

    print("\n✓ Setup complete!")
    print("Run: freecode")
    print()



def print_help() -> None:
    """Print help message."""
    print(
        """FreeCode — Terminal AI coding agent on ApiFreeLLM's free tier

USAGE
  freecode                      Launch interactive TUI agent
  freecode mcp [PROJECT]        Run as MCP server for Claude/Cursor
  freecode setup                Configure shortcuts, keybinds, theme
  freecode --help, -h           Show this help
  freecode --version            Show version

SUBCOMMANDS
  freecode mcp [PATH]
    Start MCP server for a project directory.
    Default: current directory (.)
    
    Add to ~/.claude/claude_desktop_config.json to use with Claude:
      "freecode": {
        "command": "freecode",
        "args": ["mcp", "/path/to/project"]
      }
    
    Use with Cursor settings → MCP servers section.

  freecode setup
    Interactive setup wizard for:
    - Keyboard shortcuts (Ctrl+Enter to send, Ctrl+E to edit, etc)
    - Color theme (light, dark, custom)
    - API key configuration
    - Project defaults

ENVIRONMENT VARIABLES
  FREECODE_API_KEY              ApiFreeLLM API key (required for agent)
  FREECODE_API_KEY_2            Secondary key for rate limit rotation
  GROQ_API_KEY                  Groq API key (optional, faster)
  GROQ_MODEL                    Groq model to use (default: openai/gpt-oss-20b)
  FREECODE_LOG_LEVEL            Debug log level (DEBUG, INFO, WARNING, ERROR)

CONFIGURATION
  ~/.freecode/config.toml       Project/global config (timeouts, approval policy)
  ~/.freecode/theme.toml        Color theme customization
  ~/.freecode/state.db          Session database (auto-created)
  .freecode/config.toml         Project-specific overrides

EXAMPLES
  # Launch the TUI agent in current project
  freecode

  # Use agent with Groq (faster, no rate limit floor)
  export GROQ_API_KEY="gsk_..."
  freecode

  # Set up with Claude Desktop
  freecode mcp .
  # → Add to ~/.claude/claude_desktop_config.json as shown above
  # → Restart Claude → tools available instantly

  # Configure shortcuts and theme
  freecode setup

  # Run without API key (mock mode, UI only)
  freecode

KEYBOARD SHORTCUTS (in TUI)
  Ctrl+Enter      Send message to agent
  Enter           New line (no send)
  Ctrl+E          Edit last prompt
  Ctrl+X          Interrupt agent
  /               Command palette
  Ctrl+/          Command palette (alternative)

COMMANDS (in TUI)
  /help           Show keyboard shortcuts
  /sessions       List previous sessions
  /session 1      Switch to session #1
  /new            Start fresh chat
  /plan           Toggle dry-run mode (no mutations)
  /undo           Undo last file edits
  /provider       List available providers
  /model          Switch Groq model
  /theme          Change color theme

COST
  ✓ ApiFreeLLM free tier   No cost, community tier
  ✓ Groq free tier         No cost, instant requests
  ✓ Local tools            Free (file I/O, git, search on your machine)

DOCUMENTATION
  Full docs:     https://github.com/A56-A5/freecode
  MCP guide:     ./docs/MCP.md
  Architecture:  ./FreeCode.md
  Quick start:   ./examples/mcp-quickstart.md

SUPPORT
  Issues:        https://github.com/A56-A5/freecode/issues
  Discussions:   https://github.com/A56-A5/freecode/discussions
""",
    )


def main() -> int:
    """Console-script entry point (sync TUI; asyncio only for setup/mcp)."""
    args = sys.argv[1:]
    try:
        if not args:
            return run_tui_subcommand([])
        head = args[0]
        if head in ("--help", "-h", "help"):
            print_help()
            return 0
        if head in ("--version", "-V", "version"):
            print("FreeCode 0.1.0")
            return 0
        if head == "setup":
            return asyncio.run(run_setup_subcommand(args[1:]))
        if head == "mcp":
            return asyncio.run(run_mcp_subcommand(args[1:]))
        if head.startswith("-"):
            print(f"Unknown option: {head}", file=sys.stderr)
            print("Try `freecode --help`.", file=sys.stderr)
            return 2
        return run_tui_subcommand(args)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
