import os
from pathlib import Path

CACHE_DIR = Path("./file_cache")
CACHE_DIR.mkdir(exist_ok=True)

def save_file(name: str, content: bytes):
    p = CACHE_DIR / name
    p.write_bytes(content)
    return str(p)
