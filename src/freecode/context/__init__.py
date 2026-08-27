"""
context/ - Context Engine (ph-08) + Event Coalescer (ph-09).
"""
from freecode.context.coalesce import EventCoalescer
from freecode.context.engine import ContextEngine
from freecode.context.index import FileEntry, ProjectIndex, build_index
from freecode.context.tokens import budget_from_settings, estimate_tokens, trim_to_budget

__all__ = [
    "ContextEngine",
    "EventCoalescer",
    "FileEntry",
    "ProjectIndex",
    "build_index",
    "budget_from_settings",
    "estimate_tokens",
    "trim_to_budget",
]
