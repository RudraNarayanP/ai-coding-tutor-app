"""Tests for the provider TTL cache used by the settings service.

The cache exists so repeated settings lookups and health checks do not
hammer provider APIs on every UI poll. These tests cover the cache module
itself and the cache invalidation contract in api_settings.
"""

import asyncio
import time
from threading import Thread

import pytest

from backend.api_settings import (
    _provider_cache,
    remove_provider_key,
    update_provider_key,
)
from backend.provider_cache import CacheEntry, ProviderCache


class TestCacheEntry:

    def test_fresh_entry_not_expired(self):
        entry = CacheEntry(value="x", timestamp=time.time(), ttl=10.0)
        assert not entry.is_expired()

    def test_expired_entry(self):
        entry = CacheEntry(value="x", timestamp=time.time() - 20, ttl=10.0)
        assert entry.is_expired()


class TestProviderCacheBasics:

    def test_get_missing_returns_none(self):
        cache = ProviderCache()
        assert cache.get("nope") is None

    def test_set_get_roundtrip(self):
        cache = ProviderCache()
        cache.set("openai", {"model": "gpt"})
        assert cache.get("openai") == {"model": "gpt"}

    def test_suffix_keys_are_independent(self):
        cache = ProviderCache()
        cache.set("openai", "info-value", suffix="info")
        cache.set("openai", "status-value", suffix="status")
        assert cache.get("openai", "info") == "info-value"
        assert cache.get("openai", "status") == "status-value"
        assert cache.get("openai") is None  # bare key untouched

    def test_delete_removes_entry(self):
        cache = ProviderCache()
        cache.set("openai", "v")
        cache.delete("openai")
        assert cache.get("openai") is None
        cache.delete("nope")  # must not raise

    def test_clear_empties_everything(self):
        cache = ProviderCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None and cache.get("b") is None


class TestProviderCacheTTL:

    def test_expired_entry_is_evicted_and_returns_none(self):
        cache = ProviderCache()
        cache.set("openai", "v", ttl=-1.0)
        assert cache.get("openai") is None

    def test_default_ttl_used_when_not_specified(self):
        cache = ProviderCache(default_ttl=0.0)
        cache.set("openai", "v")
        assert cache.get("openai") is None  # 0 ttl -> instantly expired

    def test_live_entry_survives_within_ttl(self):
        cache = ProviderCache()
        cache.set("openai", "v", ttl=60.0)
        assert cache.get("openai") == "v"


class TestProviderCacheHelpers:

    def test_provider_info_helpers(self):
        cache = ProviderCache()
        assert cache.get_provider_info("openai") is None
        cache.set_provider_info("openai", "INFO")
        assert cache.get_provider_info("openai") == "INFO"

    def test_providers_overview_helpers(self):
        cache = ProviderCache()
        assert cache.get_providers_overview() is None
        cache.set_providers_overview(["A", "B"])
        assert cache.get_providers_overview() == ["A", "B"]

    def test_provider_status_helpers(self):
        cache = ProviderCache()
        assert cache.get_provider_status("ollama") is None
        cache.set_provider_status("ollama", "STATUS")
        assert cache.get_provider_status("ollama") == "STATUS"


class TestProviderCacheThreadSafety:

    def test_concurrent_writes_do_not_lose_entries(self):
        cache = ProviderCache()

        def _writer(i: int):
            for j in range(50):
                cache.set(f"p{i}", j)

        threads = [Thread(target=_writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(5):
            assert cache.get(f"p{i}") is not None


class TestSettingsInvalidation:

    def teardown_method(self):
        _provider_cache.clear()
        remove_provider_key("testcache")

    def test_update_key_invalidates_cached_info_and_overview(self):
        _provider_cache.set_provider_info("testcache", "STALE-INFO")
        _provider_cache.set_providers_overview(["STALE-OVERVIEW"])

        update_provider_key("testcache", "sk-test-1234567890abcdef")

        assert _provider_cache.get_provider_info("testcache") is None
        assert _provider_cache.get_providers_overview() is None

    def test_remove_key_invalidates_cached_info_and_overview(self):
        _provider_cache.set_provider_info("testcache", "STALE-INFO")
        _provider_cache.set_providers_overview(["STALE-OVERVIEW"])

        remove_provider_key("testcache")

        assert _provider_cache.get_provider_info("testcache") is None
        assert _provider_cache.get_providers_overview() is None

    def test_cached_info_returned_until_invalidated(self):
        # Prove the wiring actually consults the cache: after seeding, the
        # cached object is what get_provider_info serves.
        from backend.api_settings import get_provider_info

        async def _call():
            return await get_provider_info("openai")

        # Prime through the real path, then verify the second call serves
        # the identical (cached) instance.
        first = asyncio.run(_call())
        second = asyncio.run(_call())
        assert first is second
