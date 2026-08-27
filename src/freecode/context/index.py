"""
context.index - lightweight project file index for relevance selection.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".freecode",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "target",
}

_TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".js", ".ts",
    ".tsx", ".jsx", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".hpp",
    ".css", ".html", ".sh", ".bash", ".zsh", ".ini", ".cfg", ".rst",
}


@dataclass(frozen=True, slots=True)
class FileEntry:
    rel_path: str
    size: int
    name_lower: str


@dataclass(slots=True)
class ProjectIndex:
    root: Path
    files: list[FileEntry]

    def __len__(self) -> int:
        return len(self.files)


def build_index(root: Path | str, *, max_files: int = 2000) -> ProjectIndex:
    root_p = Path(root).resolve()
    files: list[FileEntry] = []
    if not root_p.is_dir():
        return ProjectIndex(root=root_p, files=files)

    for dirpath, dirnames, filenames in os.walk(root_p):
        # prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if len(files) >= max_files:
                return ProjectIndex(root=root_p, files=files)
            path = Path(dirpath) / name
            suffix = path.suffix.lower()
            if suffix and suffix not in _TEXT_SUFFIXES:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > 500_000:
                continue
            try:
                rel = str(path.relative_to(root_p))
            except ValueError:
                continue
            files.append(FileEntry(rel_path=rel, size=size, name_lower=name.lower()))
    return ProjectIndex(root=root_p, files=files)
