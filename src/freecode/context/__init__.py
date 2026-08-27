"""
context/ - Context Engine (ph-08).

Indexes the project, selects relevant files, compresses history, and
assembles a flat prompt within the token budget for ApiFreeLLM.
"""
from freecode.context.engine import ContextEngine
from freecode.context.index import FileEntry, ProjectIndex, build_index
from freecode.context.tokens import budget_from_settings, estimate_tokens, trim_to_budget

__all__ = [
    "ContextEngine",
    "FileEntry",
    "ProjectIndex",
    "build_index",
    "budget_from_settings",
    "estimate_tokens",
    "trim_to_budget",
]
