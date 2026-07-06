from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class ChannelConfig:
    name: str
    rss_url: str


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    cache_ttl_seconds: int
    http_timeout_seconds: float
    log_level: str
    feed_entries_per_channel: int


CHANNELS: tuple[ChannelConfig, ...] = (
    ChannelConfig(
        name="Theo / t3.gg",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCbRP3c757lWg9M-U7TyEkXA",
    ),
    ChannelConfig(
        name="ThePrimeTime",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCUyeluBRhGPCW4rPe_UvBZQ",
    ),
    ChannelConfig(
        name="ThePrimeagen",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UC8ENHE5xdFSwx71u3fDH5Xw",
    ),
    ChannelConfig(
        name="Web Dev Simplified",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCFbNIlppjAuEX4znoulh0Cw",
    ),
    ChannelConfig(
        name="Matt Pocock",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCswG6FSbgZjbWtdf_hMLaow",
    ),
    ChannelConfig(
        name="Awesome / @awesome-coding",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCXzw-OdotBUcNA9yhuYQBwA",
    ),
    ChannelConfig(
        name="Syntax",
        rss_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCyU5wkjgQYGRB0hIHMwm2Sg",
    ),
)

SAMPLE_CHANNEL_NAMES = frozenset({"Theo / t3.gg", "ThePrimeTime"})


def _get_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        msg = f"{name} must be an integer"
        raise RuntimeError(msg) from exc

    if value < minimum:
        msg = f"{name} must be greater than or equal to {minimum}"
        raise RuntimeError(msg)

    return value


def _get_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = float(raw)
    except ValueError as exc:
        msg = f"{name} must be a number"
        raise RuntimeError(msg) from exc

    if value < minimum:
        msg = f"{name} must be greater than or equal to {minimum}"
        raise RuntimeError(msg)

    return value


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "dev-video-feed"),
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        cache_ttl_seconds=_get_int("CACHE_TTL_SECONDS", 900, minimum=0),
        http_timeout_seconds=_get_float("HTTP_TIMEOUT_SECONDS", 15.0, minimum=0.1),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        feed_entries_per_channel=_get_int("FEED_ENTRIES_PER_CHANNEL", 7, minimum=1),
    )


def get_sample_channels() -> tuple[ChannelConfig, ...]:
    return tuple(channel for channel in CHANNELS if channel.name in SAMPLE_CHANNEL_NAMES)
