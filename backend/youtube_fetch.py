"""Robust YouTube fetch pipeline for Create Course.

Datacenter IPs are aggressively bot-blocked by YouTube, so the direct transcript
API and yt-dlp fail from server environments. This module fetches the public
watch/playlist page through a keyless reader proxy (``r.jina.ai``) that performs
the request from its own infrastructure, then extracts high-signal, source-
grounded content: the video title, description, and — most importantly — the
creator-authored **chapter markers**, which for tutorial videos are an ordered,
authoritative outline of exactly what is built.

If a proxy/transcript credential is configured it is used first; otherwise the
reader proxy is used. Everything degrades to a clear "can't ground this" result
rather than fabricating content.
"""
from __future__ import annotations

import os
import re

import httpx

READER_PROXY = os.getenv("YOUTUBE_READER_PROXY", "https://r.jina.ai/").rstrip("/") + "/"
_TIMEOUT = float(os.getenv("YOUTUBE_FETCH_TIMEOUT", "45"))

_CHAPTER_RE = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]\([^)]*\)\s*([^\[\n]+)")


class YouTubeFetchError(Exception):
    pass


async def _reader_get(target_url: str, client: httpx.AsyncClient | None = None) -> str:
    url = f"{READER_PROXY}{target_url}"
    owns = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT)
    try:
        headers = {"X-Return-Format": "markdown", "User-Agent": "PatchworkBot/1.0"}
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200 or not resp.text.strip():
            raise YouTubeFetchError(f"Reader proxy returned {resp.status_code}.")
        return resp.text
    finally:
        if owns:
            await client.aclose()


def _extract_title(md: str) -> str:
    m = re.search(r"^Title:\s*(.+?)(?:\s*-\s*YouTube)?\s*$", md, re.MULTILINE)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    return m.group(1).strip() if m else ""


_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _unmarkdown_links(text: str) -> str:
    """Keep link labels and high-signal URLs (GitHub/Colab), drop the rest of the markup."""

    def _repl(match: re.Match[str]) -> str:
        label, url = match.group(1).strip(), match.group(2).strip()
        if re.search(r"github\.com|colab\.research\.google|huggingface\.co", url, re.I):
            return f"{label} {url}".strip()
        return label

    cleaned = _MD_LINK.sub(_repl, text)
    cleaned = re.sub(r"https://www\.youtube\.com/[^\s)]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _creator_description_block(md: str) -> str:
    """Prefer the ## Description section even if comments appear earlier on the page."""
    match = re.search(
        r"^##\s+Description\s*\n(.+?)(?=^##\s+(?!Description)\b|\Z)",
        md,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1)
    return re.split(
        r"^##\s+(?:Comments|In this video)\b",
        md,
        maxsplit=1,
        flags=re.IGNORECASE | re.MULTILINE,
    )[0]


def _extract_description(md: str) -> str:
    """Pull the creator's own description, not viewer comments or sidebar chrome.

    Reader-proxy pages interleave comments (often the longest prose on the page)
    with the real description. Using the longest line globally turned follow-along
    tutorials into comment snippets and caused false rejects.

    Creator descriptions often embed YouTube/GitHub markdown links; unmarkdown
    those and keep the prose rather than dropping the line.
    """
    block = _creator_description_block(md)
    pieces: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if len(line) < 20:
            continue
        if line.startswith(("#", "|", "Title:", "URL Source:", "Warning:")):
            continue
        if "views •" in line or "Live Playlist" in line:
            continue
        if line.lower().startswith("chapters:"):
            continue
        if line.startswith("*"):
            continue
        prose = _unmarkdown_links(line)
        if len(prose) < 20:
            continue
        if re.match(r"^(hey|wow|nice|thanks|thank you|great video)\b", prose, re.I) and len(prose) < 180:
            continue
        pieces.append(prose)
    joined = " ".join(pieces)
    return joined[:4000]


def extract_chapters(md: str) -> list[tuple[str, str]]:
    """Return ordered (timestamp, title) chapters from the description block.

    De-duplicates and filters out recommendation-sidebar entries (which carry a
    "views •" suffix).
    """
    # Focus on the "Chapters:" run if present (single line with many markers).
    chapter_line = ""
    for line in md.splitlines():
        if line.count("](https://www.youtube.com/watch") >= 4 and re.search(r"\[\d{1,2}:\d{2}", line):
            if len(line) > len(chapter_line):
                chapter_line = line
    haystack = chapter_line or md

    seen: set[str] = set()
    chapters: list[tuple[str, str]] = []
    for ts, raw_title in _CHAPTER_RE.findall(haystack):
        title = raw_title.strip(" -–—:•\t")
        # Drop recommendation rows and empties.
        if not title or "views •" in title or "Live Playlist" in title or "Mix (" in title:
            continue
        if len(title) < 3:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        chapters.append((ts, title))
    return chapters


def build_source_text(title: str, description: str, chapters: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    if chapters:
        parts.append("Chapters:")
        for _ts, ch_title in chapters:
            parts.append(ch_title)
    return "\n".join(parts)


_CHALLENGE_MARKERS = ("just a moment", "security verification", "performing security", "verifying you are")
_FETCH_ATTEMPTS = int(os.getenv("YOUTUBE_FETCH_ATTEMPTS", "3"))


def _looks_incomplete(md: str, chapters: list) -> bool:
    low = md.lower()
    if any(marker in low for marker in _CHALLENGE_MARKERS):
        return True
    # A real watch page is large; a challenge/loading page is tiny.
    return len(md) < 1500 and not chapters


async def fetch_video(video_id: str, client: httpx.AsyncClient | None = None) -> dict:
    """Fetch title/description/chapters for a single video via the reader proxy.

    The reader proxy intermittently returns a challenge/loading page; retry a few
    times and keep the best (most chapters) result."""
    best: dict | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        try:
            md = await _reader_get(f"https://www.youtube.com/watch?v={video_id}", client)
        except Exception:  # noqa: BLE001
            continue
        title = _extract_title(md)
        description = _extract_description(md)
        chapters = extract_chapters(md)
        result = {
            "video_id": video_id,
            "title": title,
            "description": description,
            "chapters": chapters,
            "text": build_source_text(title, description, chapters),
        }
        if best is None or len(chapters) > len(best["chapters"]) or (
            len(chapters) == len(best.get("chapters") or [])
            and len(description) > len(best.get("description") or "")
        ):
            best = result
        # Good enough — stop early. Description-only videos (no chapters) still count.
        if (chapters or len(description) >= 120) and not _looks_incomplete(md, chapters):
            return result
    if best is not None:
        return best
    raise YouTubeFetchError("Reader proxy did not return usable content.")


async def fetch_playlist_video_ids(playlist_id: str, client: httpx.AsyncClient | None = None) -> list[str]:
    """Return ordered, de-duplicated video ids from a playlist page."""
    md = await _reader_get(f"https://www.youtube.com/playlist?list={playlist_id}", client)
    ids: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"watch\?v=([A-Za-z0-9_-]{11})", md):
        vid = m.group(1)
        if vid not in seen:
            seen.add(vid)
            ids.append(vid)
    return ids
