"""
Shared in-process TTL cache utilities.

Provides two cache classes used across route modules:

  TTLCache      — single-value cache (global stats, player lists, etc.)
  TTLCacheDict  — per-key cache (player-scoped data keyed by puuid/window)

Both classes use double-checked locking (stampede protection) so that only
ONE thread runs the expensive compute_fn even when 50 concurrent requests
arrive on a cold cache simultaneously.  All other callers block on a
_compute_lock, then find the cache warm on the second check and return
immediately without touching the DB.
"""
import threading
import time
from typing import Any, Callable, Dict, Optional

_CACHE_TTL = 300  # seconds — cache entries expire after 5 minutes


class TTLCache:
    """Thread-safe single-value TTL cache with stampede protection."""

    def __init__(self) -> None:
        self._lock         = threading.Lock()
        self._compute_lock = threading.Lock()
        self._value: Optional[Any] = None
        self._expires_at: float = 0.0

    def get(self) -> Optional[Any]:
        with self._lock:
            if time.monotonic() < self._expires_at:
                return self._value
            return None

    def set(self, value: Any) -> None:
        with self._lock:
            self._value      = value
            self._expires_at = time.monotonic() + _CACHE_TTL

    def get_or_compute(self, compute_fn: Callable[[], Any]) -> Any:
        """Return cached value or compute it — only one thread computes at a time."""
        val = self.get()
        if val is not None:
            return val
        with self._compute_lock:
            val = self.get()
            if val is not None:
                return val
            result = compute_fn()
            self.set(result)
            return result


class TTLCacheDict:
    """Thread-safe per-key TTL cache with stampede protection."""

    def __init__(self) -> None:
        self._lock         = threading.Lock()
        self._values:    Dict[Any, Any]            = {}
        self._expires:   Dict[Any, float]          = {}
        self._key_locks: Dict[Any, threading.Lock] = {}

    def _key_lock(self, key: Any) -> threading.Lock:
        with self._lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get(self, key: Any) -> Optional[Any]:
        with self._lock:
            if key in self._values and time.monotonic() < self._expires[key]:
                return self._values[key]
            return None

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._values[key]  = value
            self._expires[key] = time.monotonic() + _CACHE_TTL

    def get_or_compute(self, key: Any, compute_fn: Callable[[], Any]) -> Any:
        val = self.get(key)
        if val is not None:
            return val
        with self._key_lock(key):
            val = self.get(key)
            if val is not None:
                return val
            result = compute_fn()
            self.set(key, result)
            return result
