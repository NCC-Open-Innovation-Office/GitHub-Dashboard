from datetime import datetime, timedelta, timezone
from typing import Any, Optional

_store: dict[str, Any] = {}
_expiry: dict[str, datetime] = {}
_stats: dict[str, int] = {"hits": 0, "misses": 0}


def cache_get(key: str) -> Optional[Any]:
    if key in _store:
        if datetime.now(tz=timezone.utc) < _expiry[key]:
            _stats["hits"] += 1
            return _store[key]
        _store.pop(key, None)
        _expiry.pop(key, None)
    _stats["misses"] += 1
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    _store[key] = value
    _expiry[key] = (
        datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
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
    if key:
        _store.pop(key, None)
        _expiry.pop(key, None)
    else:
        _store.clear()
        _expiry.clear()


def cache_stats() -> dict[str, Any]:
    """Return cache hit/miss statistics"""
    total = _stats["hits"] + _stats["misses"]
    hit_rate = (_stats["hits"] / total * 100) if total > 0 else 0
    return {
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "total": total,
        "hit_rate_percent": round(hit_rate, 2),
    }


def cache_info() -> dict:
    """Return detailed cache information"""
    return {
        "size": len(_store),
        "keys": list(_store.keys()),
        "stats": cache_stats()
    }
