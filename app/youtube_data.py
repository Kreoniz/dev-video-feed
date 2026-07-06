from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace

import httpx

from app.config import Settings
from app.models import ParsedVideo

logger = logging.getLogger(__name__)

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


class YouTubeDataAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoDetails:
    video_id: str
    duration_iso: str | None
    duration_seconds: int | None
    live_broadcast_content: str | None
    has_live_streaming_details: bool


async def fetch_video_details(
    client: httpx.AsyncClient,
    video_ids: list[str],
    settings: Settings,
) -> dict[str, VideoDetails]:
    if not settings.youtube_api_key:
        return {}

    unique_ids = list(dict.fromkeys(video_ids))
    details: dict[str, VideoDetails] = {}

    for batch in _chunks(unique_ids, settings.youtube_details_batch_size):
        params = {
            "part": "snippet,contentDetails,liveStreamingDetails,status",
            "id": ",".join(batch),
            "key": settings.youtube_api_key,
        }
        try:
            response = await client.get(
                YOUTUBE_VIDEOS_URL,
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            error = _youtube_error_message(exc.response)
            raise YouTubeDataAPIError(error) from exc
        except httpx.HTTPError as exc:
            raise YouTubeDataAPIError(f"{exc.__class__.__name__}: {exc}") from exc

        for item in payload.get("items", []):
            parsed = parse_video_details(item)
            if parsed is not None:
                details[parsed.video_id] = parsed

    logger.info(
        "youtube_data_enrichment_success",
        extra={
            "event": "youtube_data_enrichment_success",
            "requested": len(unique_ids),
            "received": len(details),
        },
    )
    return details


def apply_video_details_to_results(
    results: list,
    details: dict[str, VideoDetails],
) -> list:
    return [
        replace(
            result,
            videos=[
                enrich_video(video, details[video.video_id]) if video.video_id in details else video
                for video in result.videos
            ],
        )
        for result in results
    ]


def enrich_video(video: ParsedVideo, details: VideoDetails) -> ParsedVideo:
    return video.model_copy(
        update={
            "duration_iso": details.duration_iso,
            "duration_seconds": details.duration_seconds,
            "youtube_data_enriched": True,
            "live_broadcast_content": details.live_broadcast_content,
            "has_live_streaming_details": details.has_live_streaming_details,
        }
    )


def parse_video_details(item: dict) -> VideoDetails | None:
    video_id = item.get("id")
    if not isinstance(video_id, str) or not video_id:
        return None

    content_details = item.get("contentDetails") or {}
    snippet = item.get("snippet") or {}
    duration_iso = content_details.get("duration")
    duration_seconds = parse_youtube_duration(duration_iso) if duration_iso else None
    live_streaming_details = item.get("liveStreamingDetails")

    return VideoDetails(
        video_id=video_id,
        duration_iso=duration_iso if isinstance(duration_iso, str) else None,
        duration_seconds=duration_seconds,
        live_broadcast_content=_optional_string(snippet.get("liveBroadcastContent")),
        has_live_streaming_details=isinstance(live_streaming_details, dict),
    )


def parse_youtube_duration(value: str) -> int | None:
    match = YOUTUBE_DURATION_RE.fullmatch(value)
    if match is None:
        return None

    parts = {key: int(raw) if raw else 0 for key, raw in match.groupdict().items()}
    total = (
        parts["days"] * 86_400 + parts["hours"] * 3_600 + parts["minutes"] * 60 + parts["seconds"]
    )
    return total


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Unknown"

    if seconds < 0:
        return "Unknown"

    hours, remainder = divmod(seconds, 3_600)
    minutes, remaining_seconds = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if remaining_seconds or not parts:
        parts.append(f"{remaining_seconds}s")

    return " ".join(parts)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _youtube_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code} from YouTube Data API"

    error = payload.get("error") or {}
    message = error.get("message")
    reason = None
    errors = error.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            reason = first.get("reason")

    if reason and message:
        return f"HTTP {response.status_code} from YouTube Data API: {reason}: {message}"
    if message:
        return f"HTTP {response.status_code} from YouTube Data API: {message}"
    return f"HTTP {response.status_code} from YouTube Data API"
