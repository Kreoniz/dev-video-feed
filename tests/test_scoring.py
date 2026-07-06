from app.models import Priority
from app.scoring import score_video


def test_practical_high_priority_tutorial_scores_highest() -> None:
    score = score_video(
        title="Build a React TypeScript app from scratch",
        description="A practical tutorial covering frontend architecture and tooling.",
        topics=["React", "TypeScript", "Frontend", "Architecture"],
        priority=Priority.HIGH,
    )

    assert score >= 90


def test_medium_ecosystem_update_scores_between_low_and_high() -> None:
    score = score_video(
        title="JavaScript ecosystem update",
        description="A discussion of recent changes with practical implications.",
        topics=["JavaScript"],
        priority=Priority.MEDIUM,
    )

    assert 45 <= score <= 75


def test_low_signal_commentary_scores_low() -> None:
    score = score_video(
        title="Developer drama and hot takes",
        description="General commentary without practical technical detail.",
        topics=[],
        priority=Priority.LOW,
    )

    assert score <= 30


def test_score_is_clamped_to_valid_range() -> None:
    score = score_video(
        title="Build React TypeScript frontend architecture with AI tooling",
        description="tutorial " * 200,
        topics=[
            "React",
            "TypeScript",
            "Frontend",
            "Architecture",
            "AI tooling",
            "Dev tools",
        ],
        priority=Priority.HIGH,
    )

    assert score == 100
