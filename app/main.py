from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import Response as RawResponse

from app.cache import TTLCache
from app.config import CHANNELS, Settings, get_sample_channels, get_settings
from app.feeds import (
    all_channels_failed,
    build_feed_response,
    build_sample_response,
    fetch_channels,
)
from app.models import FeedResponse, HealthResponse, SampleResponse

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Content-Type": "application/json; charset=utf-8",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


_STANDARD_LOG_RECORD_ATTRS = set(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    app.state.cache = TTLCache(settings.cache_ttl_seconds)
    logging.getLogger(__name__).info(
        "app_started",
        extra={
            "event": "app_started",
            "service": settings.app_name,
            "version": settings.app_version,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
        },
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    return FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Technical YouTube RSS feed normalizer.",
        lifespan=lifespan,
    )


app = create_app()


def request_settings(request: Request) -> Settings:
    return request.app.state.settings


def request_cache(request: Request) -> TTLCache:
    return request.app.state.cache


SettingsDep = Annotated[Settings, Depends(request_settings)]
CacheDep = Annotated[TTLCache, Depends(request_cache)]
ForceQuery = Annotated[bool, Query()]


def apply_no_store_headers(response: Response) -> None:
    for name, value in NO_STORE_HEADERS.items():
        response.headers[name] = value


@app.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        ok=True,
        service=settings.app_name,
        version=settings.app_version,
        generated_at=datetime.now(UTC),
    )


@app.get("/feed.json", response_model=FeedResponse)
async def feed_json(
    response: Response,
    settings: SettingsDep,
    cache: CacheDep,
    force: ForceQuery = False,
) -> FeedResponse:
    apply_no_store_headers(response)
    return await _get_feed_response(settings=settings, cache=cache, force=force)


@app.get("/sample", response_model=SampleResponse)
async def sample(
    response: Response,
    settings: SettingsDep,
    cache: CacheDep,
    force: ForceQuery = False,
) -> SampleResponse:
    apply_no_store_headers(response)
    return await _get_sample_response(settings=settings, cache=cache, force=force)


@app.get("/feed.xml", response_class=RawResponse)
async def feed_xml(
    settings: SettingsDep,
    cache: CacheDep,
    force: ForceQuery = False,
) -> RawResponse:
    feed = await _get_feed_response(settings=settings, cache=cache, force=force)
    return RawResponse(content=_render_rss(feed, settings), media_type="application/rss+xml")


async def _get_feed_response(
    *,
    settings: Settings,
    cache: TTLCache,
    force: bool,
) -> FeedResponse:
    cache_key = (
        f"feed:v2:{settings.feed_entries_per_channel}:"
        f"ytdata={settings.youtube_data_api_enabled and bool(settings.youtube_api_key)}:"
        f"min_duration={settings.min_video_duration_seconds}"
    )
    if not force:
        cached = await cache.get(cache_key)
        if isinstance(cached, FeedResponse):
            logging.getLogger(__name__).info(
                "cache_hit",
                extra={"event": "cache_hit", "key": cache_key},
            )
            return cached

    results = await fetch_channels(CHANNELS, settings)
    response = build_feed_response(results, settings)
    _raise_if_all_channels_failed(response)
    await cache.set(cache_key, response)
    return response


async def _get_sample_response(
    *,
    settings: Settings,
    cache: TTLCache,
    force: bool,
) -> SampleResponse:
    cache_key = (
        f"sample:v2:{settings.feed_entries_per_channel}:"
        f"ytdata={settings.youtube_data_api_enabled and bool(settings.youtube_api_key)}"
    )
    if not force:
        cached = await cache.get(cache_key)
        if isinstance(cached, SampleResponse):
            logging.getLogger(__name__).info(
                "cache_hit",
                extra={"event": "cache_hit", "key": cache_key},
            )
            return cached

    results = await fetch_channels(get_sample_channels(), settings)
    response = build_sample_response(results, limit=3)
    _raise_if_all_channels_failed(response)
    await cache.set(cache_key, response)
    return response


def _raise_if_all_channels_failed(response: FeedResponse | SampleResponse) -> None:
    if not all_channels_failed(response):
        return

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=response.model_dump(mode="json", by_alias=True),
    )


def _render_rss(feed: FeedResponse, settings: Settings) -> str:
    generated = feed.generated_at.isoformat()
    items = "\n".join(_render_rss_item(item) for item in feed.items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape(settings.app_name)}</title>
    <link>https://www.youtube.com/</link>
    <description>Normalized technical YouTube RSS feed</description>
    <lastBuildDate>{escape(generated)}</lastBuildDate>
{items}
  </channel>
</rss>
"""


def _render_rss_item(item: Any) -> str:
    description = escape(item.summary or item.description_snippet or item.title)
    return f"""    <item>
      <title>{escape(item.title)}</title>
      <link>{escape(item.url)}</link>
      <guid isPermaLink="true">{escape(item.url)}</guid>
      <pubDate>{escape(item.published.isoformat())}</pubDate>
      <description>{description}</description>
    </item>"""
