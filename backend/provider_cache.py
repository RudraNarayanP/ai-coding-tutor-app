"""
Provider cache for reducing latency in health checks and settings lookups.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, Any

from .ai_models import ProviderStatus

if TYPE_CHECKING:
    from .api_settings import ProviderInfo


@dataclass
class CacheEntry:
    """Cache entry with timestamp and value."""
    value: Any
    timestamp: float
    ttl: float  # Time to live in seconds

    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return True
        return time.time() - self.timestamp >= self.ttl


class ProviderCache:
    """Thread-safe cache for provider information with TTL."""

    def __init__(self, default_ttl: float = 30.0):
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._lock = RLock()

    def _make_key(self, provider_id: str, suffix: str = "") -> str:
        """Create a cache key."""
        if suffix:
            return f"{provider_id}:{suffix}"
        return provider_id

    def get(self, provider_id: str, suffix: str = "") -> Any | None:
        """Get value from cache if not expired."""
        key = self._make_key(provider_id, suffix)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[key]
                return None
            return entry.value

    def set(self, provider_id: str, value: Any, ttl: float | None = None, suffix: str = ""):
        """Set value in cache."""
        if ttl is None:
            ttl = self._default_ttl
        key = self._make_key(provider_id, suffix)
        with self._lock:
            self._cache[key] = CacheEntry(value=value, timestamp=time.time(), ttl=ttl)

    def delete(self, provider_id: str, suffix: str = ""):
        """Delete value from cache."""
        key = self._make_key(provider_id, suffix)
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def get_providers_overview(self) -> list[ProviderInfo] | None:
        """Get cached providers info list."""
        return self.get("providers_overview")

    def set_providers_overview(self, providers: list[ProviderInfo], ttl: float = 10.0):
        """Cache providers info list."""
        self.set("providers_overview", providers, ttl=ttl)

    def get_provider_info(self, provider_id: str) -> ProviderInfo | None:
        """Get cached provider info."""
        return self.get(provider_id, "info")

    def set_provider_info(self, provider_id: str, info: ProviderInfo, ttl: float = 10.0):
        """Cache provider info."""
        self.set(provider_id, info, ttl=ttl, suffix="info")

    def get_provider_status(self, provider_id: str) -> ProviderStatus | None:
        """Get cached provider status."""
        return self.get(provider_id, "status")

    def set_provider_status(self, provider_id: str, status: ProviderStatus, ttl: float = 15.0):
        """Cache provider status."""
        self.set(provider_id, status, ttl=ttl, suffix="status")
