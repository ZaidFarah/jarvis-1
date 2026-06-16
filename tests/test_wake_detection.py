from __future__ import annotations

from voice.wake import WakeDetector, remove_wake_phrase_prefix


def make_detector(threshold: float = 0.72) -> WakeDetector:
    return WakeDetector(
        wake_phrase="hey jarvis",
        aliases=[
            "jarvis",
            "hi jarvis",
            "wake up jarvis",
            "okay jarvis",
            "yo jarvis",
            "jarvis please",
            "service",
            "jervis",
            "travis",
            "charities",
            "office",
            "jar of this",
            "out of this",
            "turn this",
        ],
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
    assert result.match_type == "phonetic"
    assert result.score >= result.threshold


def test_wake_matching_rejects_similar_non_wake_words() -> None:
    result = make_detector().detect("hey drivers")

    assert result.detected is False
    assert result.match_type == "none"


def test_non_match() -> None:
    result = make_detector().detect("what time is it")

    assert result.detected is False
    assert result.match_type == "none"


def test_wake_detection_requires_prefix_not_embedded_phrase() -> None:
    result = make_detector().detect("i don't know if you can see us")

    assert result.detected is False
    assert result.match_type == "none"


def test_threshold_behavior() -> None:
    low_threshold = make_detector(threshold=0.72).detect("hey jervis")
    high_threshold = make_detector(threshold=0.98).detect("hey jervis")

    assert low_threshold.detected is True
    assert high_threshold.detected is False


def test_exact_wake_phrase_removal() -> None:
    cleaned = remove_wake_phrase_prefix(
        "Hey Jarvis, what can you do?",
        wake_phrase="hey jarvis",
        aliases=["hi jarvis"],
    )

    assert cleaned == "what can you do?"


def test_alias_wake_phrase_removal() -> None:
    cleaned = remove_wake_phrase_prefix(
        "Wake up Jarvis: open settings",
        wake_phrase="hey jarvis",
        aliases=["wake up jarvis"],
    )

    assert cleaned == "open settings"


def test_wake_phrase_removal_cleans_punctuation_and_spacing() -> None:
    cleaned = remove_wake_phrase_prefix(
        "hey jarvis   ,   what can you do ?",
        wake_phrase="hey jarvis",
        aliases=[],
    )

    assert cleaned == "what can you do?"


def test_command_without_wake_phrase_is_unchanged_except_spacing() -> None:
    cleaned = remove_wake_phrase_prefix(
        "what   can you do?",
        wake_phrase="hey jarvis",
        aliases=["wake up jarvis"],
    )

    assert cleaned == "what can you do?"


def test_empty_command_after_wake_phrase_only() -> None:
    cleaned = remove_wake_phrase_prefix(
        "okay jarvis!",
        wake_phrase="hey jarvis",
        aliases=["okay jarvis"],
    )

    assert cleaned == ""


def test_fuzzy_wake_phrase_removal_handles_common_jarvis_mishearing() -> None:
    cleaned = remove_wake_phrase_prefix(
        "hey jervis status report",
        wake_phrase="hey jarvis",
        aliases=["okay jarvis"],
    )

    assert cleaned == "status report"


def test_common_whisper_mistakes_match_as_wake_aliases() -> None:
    assert make_detector().detect("service").detected is True
    assert make_detector().detect("jar of this").detected is True
    assert make_detector().detect("out of this").detected is True
