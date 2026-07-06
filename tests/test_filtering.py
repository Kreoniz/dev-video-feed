from datetime import UTC, datetime

from app.filtering import get_skip_reason
from app.models import ParsedVideo, SkippedReason


def make_video(
    *,
    title: str = "Build a TypeScript API",
    description: str = "A practical tutorial about web development.",
    url: str = "https://www.youtube.com/watch?v=abc123",
    source_url: str | None = None,
    video_id: str = "abc123",
) -> ParsedVideo:
    return ParsedVideo(
        video_id=video_id,
        title=title,
        url=url,
        source_url=source_url,
        published=datetime(2026, 1, 1, tzinfo=UTC),
        channel="Example",
        description=description,
    )


def test_skips_shorts_by_source_url_path() -> None:
    video = make_video(source_url="https://www.youtube.com/shorts/abc123")

    assert get_skip_reason(video) == SkippedReason.SHORT


def test_skips_shorts_by_metadata_marker() -> None:
    video = make_video(title="A quick CSS tip #shorts")

    assert get_skip_reason(video) == SkippedReason.SHORT


def test_skips_streams_by_metadata_marker() -> None:
    video = make_video(title="Live coding stream replay")

    assert get_skip_reason(video) == SkippedReason.STREAM


def test_skips_non_youtube_urls() -> None:
    video = make_video(url="https://example.com/watch?v=abc123")

    assert get_skip_reason(video) == SkippedReason.NON_YOUTUBE


def test_accepts_normal_youtube_watch_url() -> None:
    video = make_video()

    assert get_skip_reason(video) is None
