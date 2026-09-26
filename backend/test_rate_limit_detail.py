"""429 responses keep the provider's reason (sweep 02:54 IST: three models 429'd in 8s with no way to tell why)."""
import httpx

from backend.ai_provider import _rate_limit_detail


def _res(body):
    return httpx.Response(429, json=body)


def test_daily_free_quota_is_named():
    d = _rate_limit_detail(_res({"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day"}}))
    assert "daily free-model quota" in d and "free-models-per-day" in d


def test_upstream_throttle_reason_is_kept():
    d = _rate_limit_detail(_res({"error": {"code": 429, "message": "Provider returned error",
                                           "metadata": {"raw": "google/gemma-4-31b-it:free is temporarily rate-limited upstream."}}}))
    assert "temporarily rate-limited upstream" in d and "daily" not in d


def test_non_json_body_is_silent():
    assert _rate_limit_detail(httpx.Response(429, text="Too Many Requests")) == ""


def test_post_with_deadline_stops_a_stalled_request(monkeypatch):
    """A stalled body read must not hang a Create (sweep 03:18 IST: 12+ min)."""
    import asyncio
    import time
    import pytest
    import backend.ai_provider as ap

    class StallClient:
        async def post(self, url, **kw):
            await asyncio.sleep(30)

    monkeypatch.setattr(ap, "_TOTAL_DEADLINE_EXTRA", 0.1)
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(ap._post_with_deadline(StallClient(), "http://x", timeout=0.1))
    assert time.monotonic() - t0 < 5
