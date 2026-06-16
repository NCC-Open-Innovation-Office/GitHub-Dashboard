from datetime import datetime, timedelta, timezone
from typing import Any, Optional

_store: dict[str, Any] = {}
_expiry: dict[str, datetime] = {}


def cache_get(key: str) -> Optional[Any]:
    if key in _store:
        if datetime.now(tz=timezone.utc) < _expiry[key]:
            return _store[key]
        _store.pop(key, None)
        _expiry.pop(key, None)
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    _store[key] = value
    _expiry[key] = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)


def cache_clear(key: str | None = None) -> None:
    if key:
        _store.pop(key, None)
        _expiry.pop(key, None)
    else:
        _store.clear()
        _expiry.clear()
