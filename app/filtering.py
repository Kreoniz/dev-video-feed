from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.models import ParsedVideo, SkippedReason

SHORT_RE = re.compile(
    r"(#shorts?\b|\byoutube\s+shorts?\b|\byt\s+shorts?\b|\bshorts\b)",
    re.IGNORECASE,
)

STREAM_RE = re.compile(
    r"\b("
    r"live|livestream|live\s+stream|stream|streamed|streaming|vod|"
    r"full\s+stream|replay|premiere|recording|clip"
    r")\b",
    re.IGNORECASE,
)


def get_skip_reason(
    video: ParsedVideo,
    *,
    min_video_duration_seconds: int = 0,
) -> SkippedReason | None:
    if not video.video_id:
        return SkippedReason.MISSING_VIDEO_ID

    if not is_youtube_watch_url(video.url):
        return SkippedReason.NON_YOUTUBE

    if is_short(video):
        return SkippedReason.SHORT

    if is_stream(video):
        return SkippedReason.STREAM

    if (
        min_video_duration_seconds > 0
        and video.duration_seconds is not None
        and video.duration_seconds < min_video_duration_seconds
    ):
        return SkippedReason.SHORT

    return None


def is_youtube_watch_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return False

    if parsed.path != "/watch":
        return False

    return bool(parse_qs(parsed.query).get("v"))


def is_short(video: ParsedVideo) -> bool:
    urls = [video.url, video.source_url or ""]
    if any(_is_shorts_path(url) for url in urls):
        return True

    return bool(SHORT_RE.search(_metadata_text(video)))


def is_stream(video: ParsedVideo) -> bool:
    if video.live_broadcast_content in {"live", "upcoming"}:
        return True

    if video.has_live_streaming_details:
        return True

    return bool(STREAM_RE.search(_metadata_text(video)))


def description_snippet(description: str, max_length: int = 240) -> str:
    snippet = " ".join(description.split())
    if len(snippet) <= max_length:
        return snippet

    return f"{snippet[: max_length - 3].rstrip()}..."


def _metadata_text(video: ParsedVideo) -> str:
    return f"{video.title}\n{video.description}\n{video.source_url or ''}\n{video.url}"


def _is_shorts_path(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path == "/shorts" or parsed.path.startswith("/shorts/")
