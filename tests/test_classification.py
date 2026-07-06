from app.classification import infer_confidence, infer_priority, infer_topics
from app.models import Confidence, ParsedVideo, Priority


def test_infer_topics_detects_expected_technical_topics() -> None:
    topics = infer_topics(
        "Build a React TypeScript app with AI tooling",
        "Use Vite and browser APIs for a frontend workflow.",
    )

    assert "React" in topics
    assert "TypeScript" in topics
    assert "AI tooling" in topics
    assert "Dev tools" in topics
    assert "Frontend" in topics


def test_infer_priority_high_for_practical_high_signal_topics() -> None:
    topics = ["TypeScript", "React", "Frontend"]

    priority = infer_priority(
        "Build a React TypeScript app from scratch",
        "A practical tutorial about frontend architecture.",
        topics,
    )

    assert priority is Priority.HIGH


def test_infer_priority_low_for_vague_commentary() -> None:
    priority = infer_priority("Developer drama and hot takes", "", [])

    assert priority is Priority.LOW


def test_confidence_high_requires_rich_metadata() -> None:
    video = ParsedVideo(
        video_id="abc123",
        title="Build a practical TypeScript service",
        url="https://www.youtube.com/watch?v=abc123",
        published="2026-01-01T00:00:00Z",
        channel="Example",
        description="A" * 140,
        thumbnail="https://i.ytimg.com/vi/abc123/hqdefault.jpg",
    )

    assert infer_confidence(video) is Confidence.HIGH
