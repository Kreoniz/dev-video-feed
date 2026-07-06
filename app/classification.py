from __future__ import annotations

import re

from app.models import Confidence, ParsedVideo, Priority

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "TypeScript": (
        "typescript",
        "type-safe",
        "type safe",
        "tsconfig",
        "type checking",
    ),
    "React": (
        "react",
        "next.js",
        "nextjs",
        "jsx",
        "server components",
    ),
    "Frontend": (
        "frontend",
        "front end",
        "ui",
        "browser",
        "client-side",
        "client side",
        "html",
        "dom",
    ),
    "JavaScript": (
        "javascript",
        "ecmascript",
        "node.js",
        "nodejs",
        "bun",
        "deno",
    ),
    "CSS": (
        "css",
        "tailwind",
        "flexbox",
        "css grid",
        "animation",
    ),
    "AI tooling": (
        "ai",
        "llm",
        "chatgpt",
        "copilot",
        "cursor",
        "claude",
        "openai",
        "agent",
    ),
    "Dev tools": (
        "developer tools",
        "devtools",
        "tooling",
        "cli",
        "terminal",
        "docker",
        "git",
        "vite",
        "webpack",
        "eslint",
        "prettier",
        "lint",
        "testing",
        "editor",
        "ide",
    ),
    "Architecture": (
        "architecture",
        "architectural",
        "system design",
        "design pattern",
        "patterns",
        "monorepo",
        "serverless",
        "microservice",
        "scaling",
        "performance",
    ),
    "Open source": (
        "open source",
        "oss",
        "github",
        "maintainer",
        "contribute",
    ),
    "Web platform": (
        "web platform",
        "webassembly",
        "wasm",
        "service worker",
        "pwa",
        "http",
        "websocket",
        "workers",
    ),
}

HIGH_PRIORITY_TOPICS = {
    "TypeScript",
    "React",
    "Frontend",
    "AI tooling",
    "Dev tools",
    "Architecture",
    "Web platform",
}

PRACTICAL_RE = re.compile(
    r"\b("
    r"tutorial|guide|build|building|from scratch|how to|explained|deep dive|"
    r"course|learn|patterns?|architecture|release|changes?|migration|"
    r"debug|testing|performance|tooling"
    r")\b",
    re.IGNORECASE,
)

LOW_SIGNAL_RE = re.compile(
    r"\b("
    r"drama|career|jobs?|salary|hot take|rant|reaction|reacts|"
    r"thoughts|opinion|vibe|life update"
    r")\b",
    re.IGNORECASE,
)


def infer_topics(title: str, description: str) -> list[str]:
    text = f"{title}\n{description}".lower()
    topics: list[str] = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            topics.append(topic)

    return topics


def infer_priority(title: str, description: str, topics: list[str]) -> Priority:
    text = f"{title}\n{description}"
    has_practical_signal = bool(PRACTICAL_RE.search(text))
    has_low_signal = bool(LOW_SIGNAL_RE.search(text))
    has_high_topic = any(topic in HIGH_PRIORITY_TOPICS for topic in topics)

    if has_low_signal and not has_practical_signal:
        return Priority.LOW

    if has_high_topic and (has_practical_signal or len(topics) >= 2):
        return Priority.HIGH

    if topics or has_practical_signal:
        return Priority.MEDIUM

    return Priority.LOW


def infer_confidence(video: ParsedVideo) -> Confidence:
    title_rich = len(video.title.strip()) >= 12
    description_rich = len(video.description.strip()) >= 120

    if title_rich and description_rich and video.thumbnail:
        return Confidence.HIGH

    if title_rich and (video.description.strip() or video.thumbnail):
        return Confidence.MEDIUM

    return Confidence.LOW


def make_summary(title: str, description: str, max_length: int = 280) -> str:
    description = " ".join(description.split())
    title = " ".join(title.split())

    if not description:
        return title

    first_sentence = description.split(". ", 1)[0].strip()
    summary = f"{title}. {first_sentence}"
    if len(summary) <= max_length:
        return summary

    return f"{summary[: max_length - 3].rstrip()}..."


def make_why_watch(topics: list[str], priority: Priority) -> str:
    if topics:
        topic_text = ", ".join(topics[:3])
        if priority is Priority.HIGH:
            return f"Useful for practical technical context on {topic_text}."
        return f"Useful if you are tracking updates or opinions around {topic_text}."

    return "Useful if the title and description match a current technical question you have."
