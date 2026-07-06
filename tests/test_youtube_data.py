from pathlib import Path

import httpx

from app.config import Settings
from app.youtube_data import (
    fetch_video_details,
    format_duration,
    parse_video_details,
    parse_youtube_duration,
)

FIXTURE = Path(__file__).parent / "fixtures" / "youtube_videos_response.json"


def make_settings() -> Settings:
    return Settings(
        app_name="dev-video-feed",
        app_version="test",
        cache_ttl_seconds=900,
        http_timeout_seconds=15.0,
        log_level="INFO",
        feed_entries_per_channel=7,
        youtube_api_key="test-key",
        youtube_data_api_enabled=True,
        youtube_data_api_required=False,
        youtube_details_batch_size=50,
        min_video_duration_seconds=180,
    )


def test_parse_youtube_duration() -> None:
    assert parse_youtube_duration("PT12M34S") == 754
    assert parse_youtube_duration("PT2H4M") == 7440
    assert parse_youtube_duration("P1DT2H3M4S") == 93784
    assert parse_youtube_duration("not-a-duration") is None


def test_format_duration() -> None:
    assert format_duration(None) == "Unknown"
    assert format_duration(0) == "0s"
    assert format_duration(58) == "58s"
    assert format_duration(754) == "12m 34s"
    assert format_duration(7440) == "2h 4m"


def test_parse_video_details() -> None:
    payload = httpx.Response(200, content=FIXTURE.read_bytes()).json()

    details = parse_video_details(payload["items"][0])

    assert details is not None
    assert details.video_id == "valid123"
    assert details.duration_iso == "PT12M34S"
    assert details.duration_seconds == 754
    assert details.live_broadcast_content == "none"
    assert details.has_live_streaming_details is False


async def test_fetch_video_details_uses_batched_videos_list_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/youtube/v3/videos"
        assert request.url.params["part"] == "snippet,contentDetails,liveStreamingDetails,status"
        assert request.url.params["id"] == "valid123,live123"
        assert request.url.params["key"] == "test-key"
        return httpx.Response(200, content=FIXTURE.read_bytes())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://www.googleapis.com",
    ) as client:
        details = await fetch_video_details(client, ["valid123", "live123"], make_settings())

    assert details["valid123"].duration_seconds == 754
    assert details["live123"].has_live_streaming_details is True
