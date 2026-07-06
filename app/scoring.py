from __future__ import annotations

import re

from app.models import Priority

PRACTICAL_RE = re.compile(
    r"\b("
    r"tutorial|guide|build|building|from scratch|how to|explained|deep dive|"
    r"course|learn|patterns?|migration|debug|testing|performance|tooling"
    r")\b",
    re.IGNORECASE,
)

TECHNICAL_DEPTH_RE = re.compile(
    r"\b("
    r"typescript|react|frontend|architecture|ai|llm|devtools?|tooling|"
    r"web platform|browser|javascript|css|open source"
    r")\b",
    re.IGNORECASE,
)

LOW_SIGNAL_RE = re.compile(
    r"\b("
    r"drama|career|jobs?|salary|hot take|rant|reaction|reacts|"
    r"thoughts|opinion|life update"
    r")\b",
    re.IGNORECASE,
)


def score_video(
    *,
    title: str,
    description: str,
    topics: list[str],
    priority: Priority | str,
) -> int:
    text = f"{title}\n{description}"
    priority_value = priority.value if isinstance(priority, Priority) else priority

    if priority_value == Priority.HIGH.value:
        score = 70
    elif priority_value == Priority.MEDIUM.value:
        score = 50
    else:
        score = 25

    score += min(len(topics) * 4, 16)

    if PRACTICAL_RE.search(text):
        score += 10

    if TECHNICAL_DEPTH_RE.search(text):
        score += 8

    if len(description.strip()) >= 160:
        score += 5

    if LOW_SIGNAL_RE.search(text):
        score -= 20

    return max(0, min(100, score))
