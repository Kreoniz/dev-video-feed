from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
from defusedxml import ElementTree

from app.classification import (
    infer_confidence,
    infer_priority,
    infer_topics,
    make_summary,
    make_why_watch,
)
from app.config import ChannelConfig, Settings
from app.filtering import description_snippet, get_skip_reason
from app.models import (
    ChannelFailure,
    FeedItem,
    FeedResponse,
    ParsedVideo,
    SampleItem,
    SampleResponse,
    SkippedItem,
    SkippedReason,
)
from app.scoring import score_video
from app.youtube_data import (
    YouTubeDataAPIError,
    apply_video_details_to_results,
    fetch_video_details,
    format_duration,
)

logger = logging.getLogger(__name__)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


@dataclass(frozen=True)
class FeedParseResult:
    videos: list[ParsedVideo]
    skipped: list[SkippedItem]


@dataclass(frozen=True)
class ChannelFetchResult:
    channel: str
    videos: list[ParsedVideo]
    skipped: list[SkippedItem]
    failure: ChannelFailure | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def parse_video_id_from_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path == "/watch":
        video_ids = parse_qs(parsed.query).get("v")
        return video_ids[0] if video_ids else None

    if host == "youtu.be":
        video_id = parsed.path.strip("/")
        return video_id or None

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path.startswith(
        "/shorts/"
    ):
        video_id = parsed.path.removeprefix("/shorts/").split("/", 1)[0]
        return video_id or None

    return None


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_youtube_feed(
    xml_text: str,
    *,
    configured_channel: str,
    max_entries: int,
) -> FeedParseResult:
    root = ElementTree.fromstring(xml_text)
    entries = root.findall("atom:entry", NS)[:max_entries]
    videos: list[ParsedVideo] = []
    skipped: list[SkippedItem] = []

    for entry in entries:
        title = _entry_title(entry) or "Untitled YouTube video"
        channel = _entry_channel(entry) or configured_channel
        source_url = _entry_link(entry)
        video_id = _entry_video_id(entry) or parse_video_id_from_url(source_url)

        if not video_id:
            skipped.append(
                SkippedItem(
                    channel=channel,
                    title=title,
                    video_id=None,
                    reason=SkippedReason.MISSING_VIDEO_ID,
                )
            )
            continue

        description = _entry_description(entry) or ""
        thumbnail = _entry_thumbnail(entry)
        published = parse_datetime(_text(entry, "atom:published")) or parse_datetime(
            _text(entry, "atom:updated")
        )

        videos.append(
            ParsedVideo(
                video_id=video_id,
                title=title,
                url=canonical_youtube_url(video_id),
                source_url=source_url,
                published=published or datetime.fromtimestamp(0, UTC),
                channel=channel,
                description=description,
                thumbnail=thumbnail,
            )
        )

    return FeedParseResult(videos=videos, skipped=skipped)


async def fetch_channels(
    channels: tuple[ChannelConfig, ...],
    settings: Settings,
) -> list[ChannelFetchResult]:
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    headers = {
        "User-Agent": f"{settings.app_name}/{settings.app_version} (+YouTube RSS normalizer)",
        "Accept": "application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        tasks = [fetch_channel(client, channel, settings) for channel in channels]
        results = list(await asyncio.gather(*tasks))

        if should_enrich_with_youtube_data(settings):
            results = await enrich_channel_results(client, results, settings)

        return results


def should_enrich_with_youtube_data(settings: Settings) -> bool:
    return settings.youtube_data_api_enabled and bool(settings.youtube_api_key)


async def enrich_channel_results(
    client: httpx.AsyncClient,
    results: list[ChannelFetchResult],
    settings: Settings,
) -> list[ChannelFetchResult]:
    video_ids = [video.video_id for result in results for video in result.videos]
    if not video_ids:
        return results

    try:
        details = await fetch_video_details(client, video_ids, settings)
    except YouTubeDataAPIError as exc:
        logger.warning(
            "youtube_data_enrichment_failed",
            extra={
                "event": "youtube_data_enrichment_failed",
                "error": str(exc),
                "required": settings.youtube_data_api_required,
            },
        )
        if settings.youtube_data_api_required:
            return [
                _failed_channel(
                    ChannelConfig(name=result.channel, rss_url="YouTube Data API"),
                    str(exc),
                )
                for result in results
            ]
        return results

    return apply_video_details_to_results(results, details)


async def fetch_channel(
    client: httpx.AsyncClient,
    channel: ChannelConfig,
    settings: Settings,
) -> ChannelFetchResult:
    try:
        response = await client.get(channel.rss_url)
        response.raise_for_status()
        parsed = parse_youtube_feed(
            response.text,
            configured_channel=channel.name,
            max_entries=settings.feed_entries_per_channel,
        )
    except httpx.HTTPStatusError as exc:
        error = f"HTTP {exc.response.status_code} while fetching feed"
        logger.warning(
            "feed_fetch_failed",
            extra={
                "event": "feed_fetch_failed",
                "channel": channel.name,
                "url": channel.rss_url,
                "status_code": exc.response.status_code,
            },
        )
        return _failed_channel(channel, error)
    except httpx.HTTPError as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        logger.warning(
            "feed_fetch_failed",
            extra={
                "event": "feed_fetch_failed",
                "channel": channel.name,
                "url": channel.rss_url,
                "error": error,
            },
        )
        return _failed_channel(channel, error)
    except ElementTree.ParseError as exc:
        error = f"Invalid XML feed: {exc}"
        logger.warning(
            "feed_parse_failed",
            extra={
                "event": "feed_parse_failed",
                "channel": channel.name,
                "url": channel.rss_url,
                "error": error,
            },
        )
        return _failed_channel(channel, error)
    except Exception as exc:  # pragma: no cover - defensive boundary around network parsing
        error = f"{exc.__class__.__name__}: {exc}"
        logger.exception(
            "feed_unexpected_failure",
            extra={
                "event": "feed_unexpected_failure",
                "channel": channel.name,
                "url": channel.rss_url,
            },
        )
        return _failed_channel(channel, error)

    logger.info(
        "feed_fetch_success",
        extra={
            "event": "feed_fetch_success",
            "channel": channel.name,
            "url": channel.rss_url,
            "items": len(parsed.videos),
            "skipped": len(parsed.skipped),
        },
    )
    return ChannelFetchResult(
        channel=channel.name,
        videos=parsed.videos,
        skipped=parsed.skipped,
        failure=None,
    )


def build_feed_response(results: list[ChannelFetchResult], settings: Settings) -> FeedResponse:
    generated_at = utc_now()
    checked = [result.channel for result in results]
    failures = [result.failure for result in results if result.failure is not None]
    skipped: list[SkippedItem] = []
    accepted: list[FeedItem] = []
    seen_video_ids: set[str] = set()
    seen_urls: set[str] = set()

    videos = sorted(
        (video for result in results for video in result.videos),
        key=lambda video: video.published,
        reverse=True,
    )

    for result in results:
        skipped.extend(result.skipped)

    for video in videos:
        reason = get_skip_reason(
            video,
            min_video_duration_seconds=settings.min_video_duration_seconds,
        )
        if reason is not None:
            skipped.append(_skip(video, reason))
            continue

        if video.video_id in seen_video_ids or video.url in seen_urls:
            skipped.append(_skip(video, SkippedReason.DUPLICATE))
            continue

        seen_video_ids.add(video.video_id)
        seen_urls.add(video.url)
        accepted.append(_to_feed_item(video))

    return FeedResponse(
        generated_at=generated_at,
        count=len(accepted),
        channels_checked=checked,
        channels_failed=failures,
        items=accepted,
        skipped=skipped,
    )


def build_sample_response(results: list[ChannelFetchResult], *, limit: int = 3) -> SampleResponse:
    generated_at = utc_now()
    checked = [result.channel for result in results]
    failures = [result.failure for result in results if result.failure is not None]
    skipped = [skipped for result in results for skipped in result.skipped]
    videos = sorted(
        (video for result in results for video in result.videos),
        key=lambda video: video.published,
        reverse=True,
    )[:limit]

    return SampleResponse(
        generated_at=generated_at,
        count=len(videos),
        channels_checked=checked,
        channels_failed=failures,
        items=[
            SampleItem(
                title=video.title,
                video_id=video.video_id,
                url=video.url,
                published=video.published,
                description_snippet=description_snippet(video.description),
                channel=video.channel,
                thumbnail=video.thumbnail,
                duration=format_duration(video.duration_seconds),
                duration_seconds=video.duration_seconds,
                duration_iso=video.duration_iso,
            )
            for video in videos
        ],
        skipped=skipped,
    )


def all_channels_failed(response: FeedResponse | SampleResponse) -> bool:
    return bool(response.channels_checked) and len(response.channels_failed) == len(
        response.channels_checked
    )


def _failed_channel(channel: ChannelConfig, error: str) -> ChannelFetchResult:
    return ChannelFetchResult(
        channel=channel.name,
        videos=[],
        skipped=[],
        failure=ChannelFailure(
            channel=channel.name,
            feed_url=channel.rss_url,
            error=error,
        ),
    )


def _skip(video: ParsedVideo, reason: SkippedReason) -> SkippedItem:
    return SkippedItem(
        channel=video.channel,
        title=video.title,
        video_id=video.video_id,
        reason=reason,
    )


def _to_feed_item(video: ParsedVideo) -> FeedItem:
    topics = infer_topics(video.title, video.description)
    priority = infer_priority(video.title, video.description, topics)
    score = score_video(
        title=video.title,
        description=video.description,
        topics=topics,
        priority=priority,
    )

    return FeedItem(
        video_id=video.video_id,
        title=video.title,
        url=video.url,
        published=video.published,
        channel=video.channel,
        description=video.description,
        description_snippet=description_snippet(video.description),
        thumbnail=video.thumbnail,
        duration=format_duration(video.duration_seconds),
        duration_seconds=video.duration_seconds,
        duration_iso=video.duration_iso,
        source="YouTube RSS + YouTube Data API" if video.youtube_data_enriched else "YouTube RSS",
        confidence=infer_confidence(video),
        topics=topics,
        priority=priority,
        score=score,
        summary=make_summary(video.title, video.description),
        why_watch=make_why_watch(topics, priority),
    )


def _text(element: ElementTree.Element, path: str) -> str | None:
    found = element.find(path, NS)
    if found is None or found.text is None:
        return None

    text = found.text.strip()
    return text or None


def _entry_title(entry: ElementTree.Element) -> str | None:
    return _text(entry, "atom:title") or _text(entry, "media:group/media:title")


def _entry_description(entry: ElementTree.Element) -> str | None:
    return _text(entry, "media:group/media:description") or _text(entry, "atom:summary")


def _entry_channel(entry: ElementTree.Element) -> str | None:
    author = entry.find("atom:author", NS)
    if author is None:
        return None

    return _text(author, "atom:name")


def _entry_video_id(entry: ElementTree.Element) -> str | None:
    video_id = _text(entry, "yt:videoId")
    if video_id:
        return video_id

    entry_id = _text(entry, "atom:id")
    if entry_id and entry_id.startswith("yt:video:"):
        return entry_id.removeprefix("yt:video:")

    return None


def _entry_link(entry: ElementTree.Element) -> str | None:
    for link in entry.findall("atom:link", NS):
        if link.attrib.get("rel") == "alternate" and link.attrib.get("href"):
            return link.attrib["href"]

    first_link = entry.find("atom:link", NS)
    if first_link is not None:
        return first_link.attrib.get("href")

    return None


def _entry_thumbnail(entry: ElementTree.Element) -> str | None:
    thumbnail = entry.find("media:group/media:thumbnail", NS)
    if thumbnail is None:
        return None

    url = thumbnail.attrib.get("url")
    return url.strip() if url else None
