from pathlib import Path

from app.feeds import ChannelFetchResult, build_feed_response, parse_youtube_feed
from app.models import SkippedReason

FIXTURE = Path(__file__).parent / "fixtures" / "youtube_feed_sample.xml"


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
        ]
    )

    assert response.count == 1
    assert response.items[0].video_id == "valid123"
    assert response.items[0].duration == "Unknown"

    skipped_reasons = {item.reason for item in response.skipped}
    assert SkippedReason.SHORT in skipped_reasons
    assert SkippedReason.STREAM in skipped_reasons
    assert SkippedReason.MISSING_VIDEO_ID in skipped_reasons
