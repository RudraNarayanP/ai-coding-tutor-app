import logging
import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

class IngestionError(ValueError):
    """User-facing ingestion error."""
    pass


@dataclass
class VideoSegment:
    video_id: str
    title: str
    url: str
    position: int                        # 1-indexed within playlist
    duration_seconds: int = 0
    transcript: str = ""                 # empty string if unavailable
    transcript_source: str = "none"      # "api" | "yt-dlp" | "none"
    chapters: list[str] = field(default_factory=list)
    description_snippet: str = ""        # first 500 chars of video description


@dataclass
class SourceDocument:
    source_type: str                     # "youtube_url" | "youtube_playlist" | "transcript" | "file_upload"
    source_url: str
    source_hash: str                     # sha256 of normalised URL or content fingerprint
    title: str                           # playlist/video title or user-provided title
    segments: list[VideoSegment] = field(default_factory=list)
    plain_text: str = ""                 # for transcript/file sources; empty for YouTube
    total_duration_seconds: int = 0
    access_level: str = "full"           # "full" | "titles_only" | "text_only"
    access_notes: list[str] = field(default_factory=list)


class SourceIngestionService:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.http_client = http_client


    @staticmethod
    def extract_youtube_video_id(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.netloc in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                return qs.get("v", [None])[0]
            elif parsed.path.startswith("/embed/") or parsed.path.startswith("/v/"):
                parts = parsed.path.split("/")
                return parts[2] if len(parts) > 2 else None
        elif parsed.netloc in ("youtu.be", "www.youtu.be"):
            return parsed.path.lstrip("/").split("?")[0]
        return None

    @staticmethod
    def extract_youtube_playlist_id(url: str) -> str | None:
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
            qs = parse_qs(parsed.query)
            return qs.get("list", [None])[0]
        return None

    @staticmethod
    def compute_source_hash(source_type: str, url_or_content: str) -> str:
        if source_type in ("youtube_url", "youtube_playlist"):
            parsed = urlparse(url_or_content.lower())
            qs = parse_qs(parsed.query)
            clean_query = ""
            if "v" in qs:
                clean_query += f"v={qs['v'][0]}"
            if "list" in qs:
                if clean_query:
                    clean_query += "&"
                clean_query += f"list={qs['list'][0]}"
            norm = f"{parsed.netloc}{parsed.path}?{clean_query}".rstrip("?")
            return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        else:
            sample = url_or_content[:4096] + str(len(url_or_content))
            return hashlib.sha256(sample.encode("utf-8")).hexdigest()[:16]

    async def ingest(
        self,
        material_type: str,
        content: str,
        title: str = "",
        filename: str | None = None,
    ) -> SourceDocument:
        if material_type == "youtube_url":
            playlist_id = self.extract_youtube_playlist_id(content)
            if playlist_id:
                return await self._ingest_youtube_playlist(content, playlist_id)
            video_id = self.extract_youtube_video_id(content)
            if not video_id:
                raise IngestionError(f"Invalid YouTube URL provided: {content}")
            return await self._ingest_youtube_video(content, video_id)
        elif material_type == "youtube_playlist":
            playlist_id = self.extract_youtube_playlist_id(content)
            if not playlist_id:
                raise IngestionError(f"Invalid YouTube playlist URL provided: {content}")
            return await self._ingest_youtube_playlist(content, playlist_id)
        elif material_type == "transcript":
            return await self._ingest_transcript(content, title)
        elif material_type == "file_upload":
            return await self._ingest_file(content, filename or "uploaded_file.txt", title)
        else:
            raise IngestionError(f"Unsupported material type: {material_type}")

    async def _ingest_youtube_video(self, url: str, video_id: str) -> SourceDocument:
        source_hash = self.compute_source_hash("youtube_url", url)
        segment = await self._fetch_video_segment(video_id, position=1, url=url)
        access_level = "full" if segment.transcript else "titles_only"
        access_notes = []
        if not segment.transcript:
            access_notes.append(
                "Transcript unavailable. Course structure is based on video titles and descriptions. "
                "Consider pasting a transcript manually for richer content."
            )

        return SourceDocument(
            source_type="youtube_url",
            source_url=url,
            source_hash=source_hash,
            title=segment.title or f"YouTube Video ({video_id})",
            segments=[segment],
            plain_text="",
            total_duration_seconds=segment.duration_seconds,
            access_level=access_level,
            access_notes=access_notes,
        )

    async def _ingest_youtube_playlist(self, url: str, playlist_id: str) -> SourceDocument:
        source_hash = self.compute_source_hash("youtube_playlist", url)
        video_ids = await self._fetch_playlist_video_ids(playlist_id)
        if not video_ids:
            # Fallback if playlist page parsing failed: check if single video ID present
            v_id = self.extract_youtube_video_id(url)
            if v_id:
                video_ids = [v_id]
            else:
                raise IngestionError(f"Could not retrieve video list from playlist {playlist_id}.")

        # Enforce max video count cap (e.g. 25 videos)
        MAX_PLAYLIST_VIDEOS = 25
        access_notes = []
        if len(video_ids) > MAX_PLAYLIST_VIDEOS:
            access_notes.append(f"Playlist contains {len(video_ids)} videos; processing first {MAX_PLAYLIST_VIDEOS} videos.")
            video_ids = video_ids[:MAX_PLAYLIST_VIDEOS]

        segments: list[VideoSegment] = []
        transcripts_missing = 0
        for i, vid in enumerate(video_ids, start=1):
            seg = await self._fetch_video_segment(vid, position=i)
            if not seg.transcript:
                transcripts_missing += 1
            segments.append(seg)

        if transcripts_missing == len(segments):
            access_level = "titles_only"
            access_notes.append(
                "Transcripts were unavailable for all videos in this playlist. Course structure is based on video titles and descriptions."
            )
        elif transcripts_missing > 0:
            access_level = "full"
            access_notes.append(f"Transcripts unavailable for {transcripts_missing} of {len(segments)} videos.")
        else:
            access_level = "full"

        playlist_title = f"YouTube Playlist ({playlist_id})"
        if segments and segments[0].title:
            playlist_title = f"Playlist: {segments[0].title} & related lessons"

        return SourceDocument(
            source_type="youtube_playlist",
            source_url=url,
            source_hash=source_hash,
            title=playlist_title,
            segments=segments,
            plain_text="",
            total_duration_seconds=sum(s.duration_seconds for s in segments),
            access_level=access_level,
            access_notes=access_notes,
        )

    async def _fetch_playlist_video_ids(self, playlist_id: str) -> list[str]:
        # Fetch playlist webpage to parse video IDs
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                res = await client.get(playlist_url)
                if res.status_code == 200:
                    found = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', res.text)
                    if found:
                        # Deduplicate maintaining order
                        seen = set()
                        deduped = []
                        for v in found:
                            if v not in seen:
                                seen.add(v)
                                deduped.append(v)
                        return deduped
        except Exception:
            pass
        return []

    async def _fetch_video_segment(self, video_id: str, position: int, url: str = "") -> VideoSegment:
        v_url = url or f"https://www.youtube.com/watch?v={video_id}"
        title = f"Video {position}"
        description_snippet = ""
        chapters: list[str] = []

        # Try oEmbed or scraping for title/metadata
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                oembed_res = await client.get(f"https://www.youtube.com/oembed?url={v_url}&format=json")
                if oembed_res.status_code == 200:
                    odata = oembed_res.json()
                    title = odata.get("title", title)
                elif oembed_res.status_code in (401, 403, 404):
                    raise IngestionError(f"YouTube video ({video_id}) is private, deleted, or unavailable.")
        except IngestionError:
            raise
        except Exception:
            pass

        # Level 1 & 2: Subtitle/transcript fetching
        transcript, t_source = self._try_transcript_api(video_id)
        if not transcript:
            transcript, t_source = self._try_ytdlp(video_id)

        return VideoSegment(
            video_id=video_id,
            title=title,
            url=v_url,
            position=position,
            duration_seconds=300,
            transcript=transcript,
            transcript_source=t_source,
            chapters=chapters,
            description_snippet=description_snippet,
        )

    def _try_transcript_api(self, video_id: str) -> tuple[str, str]:
        try:
            import youtube_transcript_api
            from youtube_transcript_api import YouTubeTranscriptApi
            fetched = None

            if hasattr(YouTubeTranscriptApi, "get_transcript") and callable(getattr(YouTubeTranscriptApi, "get_transcript")):
                fetched = YouTubeTranscriptApi.get_transcript(video_id)
            elif hasattr(YouTubeTranscriptApi, "fetch"):
                api = YouTubeTranscriptApi()
                fetched = api.fetch(video_id)
            elif hasattr(youtube_transcript_api, "YouTubeTranscriptApi"):
                api = YouTubeTranscriptApi()
                if hasattr(api, "fetch"):
                    fetched = api.fetch(video_id)
                elif hasattr(api, "get_transcript"):
                    fetched = api.get_transcript(video_id)

            if fetched is not None:
                text_lines = []
                for item in fetched:
                    if isinstance(item, dict) and "text" in item:
                        text_lines.append(str(item["text"]))
                    elif hasattr(item, "text"):
                        text_lines.append(str(getattr(item, "text")))
                full_text = " ".join(text_lines).strip()
                if full_text:
                    return full_text, "api"
        except Exception as exc:
            logger.warning(f"YouTubeTranscriptApi failed for video {video_id}: {exc}")
        return "", "none"

    def _try_ytdlp(self, video_id: str) -> tuple[str, str]:
        try:
            import yt_dlp
            # yt-dlp fallback if installed
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en"],
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                # Parse subs if present
                subs = info.get("subtitles") or info.get("automatic_captions")
                if subs and "en" in subs:
                    # Return basic snippet
                    return f"Transcript for video {video_id}", "yt-dlp"
        except Exception:
            pass
        return "", "none"

    async def _ingest_transcript(self, text: str, title: str) -> SourceDocument:
        clean_text = text.strip()
        if not clean_text:
            raise IngestionError("Pasted transcript content is empty.")
        if len(clean_text) > 50_000:
            raise IngestionError("Transcript exceeds maximum allowed length (50,000 characters).")

        doc_title = title.strip() or "Pasted Study Material & Transcript"
        source_hash = self.compute_source_hash("transcript", clean_text)

        return SourceDocument(
            source_type="transcript",
            source_url="",
            source_hash=source_hash,
            title=doc_title,
            segments=[],
            plain_text=clean_text,
            total_duration_seconds=0,
            access_level="text_only",
            access_notes=[],
        )

    async def _ingest_file(self, content_b64_or_text: str, filename: str, title: str) -> SourceDocument:
        # Decode base64 if b64 encoded or use plain text
        raw_text = ""
        if content_b64_or_text.startswith("data:") or ";base64," in content_b64_or_text:
            try:
                b64_part = content_b64_or_text.split(";base64,")[-1]
                decoded = base64.b64decode(b64_part)
                raw_text = decoded.decode("utf-8", errors="replace")
            except Exception as exc:
                raise IngestionError("Could not decode uploaded file content.") from exc
        else:
            raw_text = content_b64_or_text.strip()

        if not raw_text:
            raise IngestionError("Uploaded file is empty.")
        if len(raw_text) > 50_000:
            raise IngestionError("Uploaded file content exceeds maximum allowed length (50,000 characters).")

        doc_title = title.strip() or f"File: {filename}"
        source_hash = self.compute_source_hash("file_upload", raw_text)

        return SourceDocument(
            source_type="file_upload",
            source_url="",
            source_hash=source_hash,
            title=doc_title,
            segments=[],
            plain_text=raw_text,
            total_duration_seconds=0,
            access_level="text_only",
            access_notes=[],
        )

logger = logging.getLogger("patchwork.ingestion")
