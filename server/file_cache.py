"""Local cache for files downloaded from CTFd challenges.

Filenames are sanitized to stop path traversal; content is stored under the
configured ``file_cache_dir``.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import settings

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """Return a filesystem-safe basename derived from ``name``."""
    cleaned = _SAFE_CHARS.sub("_", name).strip("._")
    if not cleaned:
        return "download.bin"
    return cleaned[-255:]  # stay well below path length limits


def save_file(name: str, content: bytes) -> str:
    """Write ``content`` to the cache directory and return the saved path."""
    cache_dir = Path(settings.file_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / safe_filename(name)
    path.write_bytes(content)
    return str(path)