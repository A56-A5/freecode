"""
tui.widgets.approval - modal allow/deny for mutating actions.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from freecode.security.approval import ApprovalRequest
from freecode.security.policy import risk_label


class ApprovalModal(ModalScreen[bool]):
    """Return True = allow, False = deny."""

    BINDINGS = [
        Binding("a", "allow", "Allow", show=True),
        Binding("y", "allow", "Allow", show=False),
        Binding("d", "deny", "Deny", show=True),
        Binding("n", "deny", "Deny", show=False),
        Binding("escape", "deny", "Deny", show=False),
    ]

    DEFAULT_CSS = """
    ApprovalModal {
        align: center middle;
    }

    #approval-box {
        width: 70;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }

    #approval-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #approval-risk {
        color: $warning;
        margin-bottom: 1;
    }

    #approval-body {
        margin-bottom: 1;
    }

    #approval-keys {
        color: $secondary;
    }
    """

    def __init__(self, request: ApprovalRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        risk = risk_label(self.request.risk)
        yield Vertical(
            Label("Permission required", id="approval-title"),
            Label(f"Risk: {risk}", id="approval-risk"),
            Static(self.request.summary, id="approval-body"),
            Label("[a] Allow    [d] Deny    Esc = Deny", id="approval-keys"),
            id="approval-box",
        )

    def action_allow(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)
