import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .config import settings

_lock = threading.RLock()


def _db_path() -> Path:
    configured = Path(settings.stats_db_path)
    if configured.is_absolute():
        return configured
    backend_root = Path(__file__).resolve().parent.parent
    return backend_root / configured


def _ensure_db() -> None:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                hits INTEGER NOT NULL DEFAULT 0,
                misses INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            (
                "INSERT OR IGNORE INTO cache_stats(id, hits, misses) "
                "VALUES (1, 0, 0)"
            )
        )


def initialize_cache() -> None:
    with _lock:
        _ensure_db()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _increment_stat(column: str) -> None:
    if column not in {"hits", "misses"}:
        raise ValueError("Invalid cache stat column")

    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            f"UPDATE cache_stats SET {column} = {column} + 1 "
            "WHERE id = 1"
        )


def cache_get(key: str) -> Optional[Any]:
    with _lock:
        _ensure_db()
        with sqlite3.connect(_db_path()) as conn:
            row = conn.execute(
                (
                    "SELECT value_json, expires_at "
                    "FROM cache_entries WHERE key = ?"
                ),
                (key,),
            ).fetchone()

            if not row:
                _increment_stat("misses")
                return None

            value_json, expires_at_raw = row
            expires_at = datetime.fromisoformat(expires_at_raw)
            if _now() < expires_at:
                _increment_stat("hits")
                return json.loads(value_json)

            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            _increment_stat("misses")
            return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    with _lock:
        _ensure_db()
        expires_at = (_now() + timedelta(seconds=ttl_seconds)).isoformat()
        now_iso = _now().isoformat()
        with sqlite3.connect(_db_path()) as conn:
            conn.execute(
                """
                INSERT INTO cache_entries(
                    key,
                    value_json,
                    expires_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), expires_at, now_iso),
            )


def cache_set_last_good(
    key: str,
    value: Any,
    ttl_seconds: int = 86400,
) -> None:
    cache_set(f"last_good:{key}", value, ttl_seconds)


def cache_get_or_last_good(
    key: str,
    stale_warning: str | None = None,
) -> Optional[Any]:
    cached = cache_get(key)
    if cached and not cached.get("is_placeholder"):
        return cached

    last_good = cache_get(f"last_good:{key}")
    if last_good:
        result = dict(last_good)
        result["is_placeholder"] = True
        if stale_warning:
            result["warning"] = stale_warning
        elif result.get("warning"):
            result["warning"] = (
                f"{result['warning']} Showing last known data while "
                "refresh continues in the background."
            )
        else:
            result["warning"] = (
                "Showing last known data while refresh continues in the "
                "background."
            )
        return result

    return cached


def cache_clear(key: str | None = None) -> None:
    with _lock:
        _ensure_db()
        with sqlite3.connect(_db_path()) as conn:
            if key:
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            else:
                conn.execute("DELETE FROM cache_entries")


def cache_expires_in_seconds(key: str) -> float | None:
    with _lock:
        _ensure_db()
        with sqlite3.connect(_db_path()) as conn:
            row = conn.execute(
                "SELECT expires_at FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            expires_at = datetime.fromisoformat(row[0])
            return (expires_at - _now()).total_seconds()


def cache_entry_metadata(key: str) -> dict[str, Any] | None:
    with _lock:
        _ensure_db()
        with sqlite3.connect(_db_path()) as conn:
            row = conn.execute(
                (
                    "SELECT updated_at, expires_at "
                    "FROM cache_entries WHERE key = ?"
                ),
                (key,),
            ).fetchone()

    if not row:
        return None

    updated_at = datetime.fromisoformat(row[0])
    expires_at = datetime.fromisoformat(row[1])
    now = _now()
    return {
        "key": key,
        "updated_at": updated_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "age_seconds": max(0.0, (now - updated_at).total_seconds()),
        "seconds_until_expiry": (expires_at - now).total_seconds(),
        "is_expired": now >= expires_at,
    }


def cache_stats() -> dict[str, Any]:
    """Return cache hit/miss statistics"""
    with _lock:
        _ensure_db()
        with sqlite3.connect(_db_path()) as conn:
            row = conn.execute(
                "SELECT hits, misses FROM cache_stats WHERE id = 1"
            ).fetchone()

    hits = int(row[0]) if row else 0
    misses = int(row[1]) if row else 0
    total = hits + misses
    hit_rate = (hits / total * 100) if total > 0 else 0
    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "hit_rate_percent": round(hit_rate, 2),
    }


def cache_info() -> dict:
    """Return detailed cache information"""
    with _lock:
        _ensure_db()
        with sqlite3.connect(_db_path()) as conn:
            size_row = conn.execute(
                "SELECT COUNT(*) FROM cache_entries"
            ).fetchone()
            key_rows = conn.execute(
                "SELECT key FROM cache_entries ORDER BY key"
            ).fetchall()

    return {
        "size": int(size_row[0]) if size_row else 0,
        "keys": [row[0] for row in key_rows],
        "db_path": str(_db_path()),
        "stats": cache_stats(),
    }
