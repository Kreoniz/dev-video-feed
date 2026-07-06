from pathlib import Path

from app.config import Settings
from app.feeds import ChannelFetchResult, build_feed_response, parse_youtube_feed
from app.models import SkippedReason
from app.youtube_data import VideoDetails, apply_video_details_to_results

FIXTURE = Path(__file__).parent / "fixtures" / "youtube_feed_sample.xml"


def make_settings(*, min_video_duration_seconds: int = 180) -> Settings:
    return Settings(
        app_name="dev-video-feed",
        app_version="test",
        cache_ttl_seconds=900,
        http_timeout_seconds=15.0,
        log_level="INFO",
        feed_entries_per_channel=7,
        youtube_api_key=None,
        youtube_data_api_enabled=False,
        youtube_data_api_required=False,
        youtube_details_batch_size=50,
        min_video_duration_seconds=min_video_duration_seconds,
    )


def test_parse_youtube_feed_normalizes_rss_entries() -> None:
    result = parse_youtube_feed(
        FIXTURE.read_text(),
        configured_channel="Theo / t3.gg",
        max_entries=7,
    )

    assert len(result.videos) == 3
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == SkippedReason.MISSING_VIDEO_ID

    first = result.videos[0]
    assert first.video_id == "valid123"
    assert first.url == "https://www.youtube.com/watch?v=valid123"
    assert first.channel == "Theo / t3.gg"
    assert first.thumbnail == "https://i.ytimg.com/vi/valid123/hqdefault.jpg"


def test_parse_youtube_feed_respects_entry_limit() -> None:
    result = parse_youtube_feed(
        FIXTURE.read_text(),
        configured_channel="Theo / t3.gg",
        max_entries=1,
    )

    assert [video.video_id for video in result.videos] == ["valid123"]
    assert result.skipped == []


def test_build_feed_response_filters_shorts_streams_and_missing_ids() -> None:
    parsed = parse_youtube_feed(
        FIXTURE.read_text(),
        configured_channel="Theo / t3.gg",
        max_entries=7,
    )
    response = build_feed_response(
        [
            ChannelFetchResult(
                channel="Theo / t3.gg",
                videos=parsed.videos,
                skipped=parsed.skipped,
            )
        ],
        make_settings(min_video_duration_seconds=0),
    )

    assert response.count == 1
    assert response.items[0].video_id == "valid123"
    assert response.items[0].duration == "Unknown"

    skipped_reasons = {item.reason for item in response.skipped}
    assert SkippedReason.SHORT in skipped_reasons
    assert SkippedReason.STREAM in skipped_reasons
    assert SkippedReason.MISSING_VIDEO_ID in skipped_reasons


def test_build_feed_response_includes_enriched_duration() -> None:
    parsed = parse_youtube_feed(
        FIXTURE.read_text(),
        configured_channel="Theo / t3.gg",
        max_entries=1,
    )
    results = apply_video_details_to_results(
        [
            ChannelFetchResult(
                channel="Theo / t3.gg",
                videos=parsed.videos,
                skipped=parsed.skipped,
            )
        ],
        {
            "valid123": VideoDetails(
                video_id="valid123",
                duration_iso="PT12M34S",
                duration_seconds=754,
                live_broadcast_content="none",
                has_live_streaming_details=False,
            )
        },
    )

    response = build_feed_response(results, make_settings())

    assert response.count == 1
    assert response.items[0].duration == "12m 34s"
    assert response.items[0].duration_seconds == 754
    assert response.items[0].duration_iso == "PT12M34S"
    assert response.items[0].source == "YouTube RSS + YouTube Data API"
