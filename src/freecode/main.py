"""
FreeCode entry point.

ph-00 Foundation: package installs, console script works.
ph-01 TUI shell: launches the Textual app.
ph-02 Configuration + logging.
ph-03..05: client, scheduler, repair — TUI can use live ApiFreeLLM when
FREECODE_API_KEY / APIFREELLM_API_KEY is set; otherwise mock replies.
"""
from __future__ import annotations

from freecode.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
