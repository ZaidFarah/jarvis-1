from __future__ import annotations

from voice.wake import WakeDetector


def make_detector(threshold: float = 0.72) -> WakeDetector:
    return WakeDetector(
        wake_phrase="hey jarvis",
        aliases=["hi jarvis", "wake up jarvis", "jarvis wake up", "okay jarvis", "yo jarvis"],
        threshold=threshold,
    )


def test_exact_wake_phrase_match() -> None:
    result = make_detector().detect("Hey Jarvis")

    assert result.detected is True
    assert result.matched_phrase == "hey jarvis"
    assert result.match_type == "exact"
    assert result.score == 1.0


def test_alias_wake_phrase_match() -> None:
    result = make_detector().detect("wake up jarvis please")

    assert result.detected is True
    assert result.matched_phrase == "wake up jarvis"
    assert result.match_type == "exact"


def test_fuzzy_wake_phrase_match() -> None:
    result = make_detector().detect("hey jervis")

    assert result.detected is True
    assert result.matched_phrase == "hey jarvis"
    assert result.match_type == "fuzzy"
    assert result.score >= result.threshold


def test_non_match() -> None:
    result = make_detector().detect("what time is it")

    assert result.detected is False
    assert result.match_type == "none"


def test_threshold_behavior() -> None:
    low_threshold = make_detector(threshold=0.72).detect("hey jervis")
    high_threshold = make_detector(threshold=0.98).detect("hey jervis")

    assert low_threshold.detected is True
    assert high_threshold.detected is False
