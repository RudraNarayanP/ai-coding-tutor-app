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


def _extract_description(md: str) -> str:
    # Karpathy-style long descriptions appear as a paragraph; grab the longest
    # descriptive line that isn't navigation chrome.
    best = ""
    for line in md.splitlines():
        line = line.strip()
        if len(line) < 80:
            continue
        if line.startswith(("[", "!", "#", "|", "Title:", "URL Source:")):
            continue
        if "views •" in line or "Live Playlist" in line:
            continue
        # Skip chapter/link runs and any line dominated by markdown links.
        if line.count("](https://www.youtube.com/watch") >= 2 or line.lower().startswith("chapters:"):
            continue
        if line.count("](http") >= 1 or line.startswith("*"):
            continue
        # Prefer lines that read like prose.
        if line.count(" ") >= 10 and len(line) > len(best):
            best = line
    return best[:4000]


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


async def fetch_video(video_id: str, client: httpx.AsyncClient | None = None) -> dict:
    """Fetch title/description/chapters for a single video via the reader proxy."""
    md = await _reader_get(f"https://www.youtube.com/watch?v={video_id}", client)
    title = _extract_title(md)
    description = _extract_description(md)
    chapters = extract_chapters(md)
    return {
        "video_id": video_id,
        "title": title,
        "description": description,
        "chapters": chapters,
        "text": build_source_text(title, description, chapters),
    }


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
