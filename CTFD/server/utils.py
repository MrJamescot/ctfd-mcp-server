import os
from .config import settings
import time

def ensure_cache_dir():
    os.makedirs(settings.file_cache_dir, exist_ok=True)

def now_ts():
    return int(time.time())
