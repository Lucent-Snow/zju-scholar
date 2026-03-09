"""zju_cache.py — 本地 JSON 缓存管理"""

import json
import time
import hashlib
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = SKILL_DIR / "cache"

# TTL in seconds
TTL_MAP = {
    "timetable": 7 * 24 * 3600,       # 7 days
    "grades": 6 * 3600,                # 6 hours
    "major_grades": 6 * 3600,          # 6 hours
    "exams": 12 * 3600,                # 12 hours
    "todos": 1 * 3600,                 # 1 hour
    "zhiyun_search": 4 * 3600,         # 4 hours
    "zhiyun_transcript": 0,            # permanent (subtitles don't change)
}


class CacheManager:
    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str, category: str = "") -> dict | list | None:
        path = self._cache_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        ttl = TTL_MAP.get(category, 3600)
        if ttl > 0:
            cached_at = cached.get("_cached_at", 0)
            if time.time() - cached_at > ttl:
                return None

        return cached.get("data")

    def set(self, key: str, data, category: str = ""):
        path = self._cache_path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"_cached_at": time.time(), "_category": category, "data": data}, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def invalidate(self, key: str):
        path = self._cache_path(key)
        if path.exists():
            path.unlink(missing_ok=True)

    def clear_all(self):
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)

    @staticmethod
    def make_search_key(teacher: str = "", keyword: str = "") -> str:
        raw = f"zhiyun_search_{teacher}_{keyword}"
        return f"zhiyun_search_{hashlib.md5(raw.encode()).hexdigest()[:12]}"
