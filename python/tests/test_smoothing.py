"""Tests for EmotionSmoother."""

import time
from unittest.mock import MagicMock

from emotion_detector.events import EmotionEvent, EventEmitter
from emotion_detector.smoothing import EmotionSmoother


def _make_scores(dominant: str, value: float = 80.0) -> dict[str, float]:
    """Create emotion scores with one dominant emotion."""
    scores = {
        "angry": 2.0,
        "disgust": 1.0,
        "fear": 2.0,
        "happy": 3.0,
        "sad": 2.0,
        "surprise": 2.0,
        "neutral": 8.0,
    }
    scores[dominant] = value
    return scores


class TestEmotionSmoother:
    def test_initial_state_is_neutral(self):
        emitter = EventEmitter()
        smoother = EmotionSmoother(event_emitter=emitter)
        assert smoother.state.dominant == "neutral"

    def test_single_update_sets_dominant(self):
        emitter = EventEmitter()
        smoother = EmotionSmoother(event_emitter=emitter, window_size=1, debounce_seconds=0)
        state = smoother.update(_make_scores("happy", 90.0))
        assert state.dominant == "happy"

    def test_smoothing_averages_over_window(self):
        emitter = EventEmitter()
        smoother = EmotionSmoother(event_emitter=emitter, window_size=3, debounce_seconds=0)

        smoother.update(_make_scores("happy", 90.0))
        smoother.update(_make_scores("happy", 60.0))
        state = smoother.update(_make_scores("happy", 30.0))

        # Average of 90, 60, 30 = 60
        assert state.scores["happy"] == 60.0

    def test_dominant_changes_after_consistent_input(self):
        emitter = EventEmitter()
        smoother = EmotionSmoother(event_emitter=emitter, window_size=3, debounce_seconds=0)

        smoother.update(_make_scores("happy", 90.0))
        smoother.update(_make_scores("sad", 90.0))
        state = smoother.update(_make_scores("sad", 90.0))

        # 2 out of 3 frames are sad-dominant, but averaging matters
        # sad avg = (2 + 90 + 90) / 3 = 60.67
        # happy avg = (90 + 3 + 3) / 3 = 32.0
        assert state.dominant == "sad"

    def test_emits_event_on_change(self):
        emitter = EventEmitter()
        callback = MagicMock()
        emitter.on_emotion(callback)

        smoother = EmotionSmoother(event_emitter=emitter, window_size=1, debounce_seconds=0)

        smoother.update(_make_scores("happy", 90.0))
        assert callback.call_count == 1

        event: EmotionEvent = callback.call_args[0][0]
        assert event.dominant_emotion == "happy"
        assert event.confidence > 0.5

    def test_debounce_prevents_rapid_emission(self):
        emitter = EventEmitter()
        callback = MagicMock()
        emitter.on_emotion(callback)

        smoother = EmotionSmoother(event_emitter=emitter, window_size=1, debounce_seconds=2.0)

        smoother.update(_make_scores("happy", 90.0))
        assert callback.call_count == 1

        # Change emotion immediately — should NOT emit due to debounce
        smoother.update(_make_scores("sad", 90.0))
        assert callback.call_count == 1

    def test_no_emit_when_same_emotion(self):
        emitter = EventEmitter()
        callback = MagicMock()
        emitter.on_emotion(callback)

        smoother = EmotionSmoother(event_emitter=emitter, window_size=1, debounce_seconds=0)

        smoother.update(_make_scores("happy", 90.0))
        smoother.update(_make_scores("happy", 85.0))
        smoother.update(_make_scores("happy", 80.0))

        # Only first call should emit (emotion didn't change)
        assert callback.call_count == 1

    def test_confidence_is_normalized(self):
        emitter = EventEmitter()
        callback = MagicMock()
        emitter.on_emotion(callback)

        smoother = EmotionSmoother(event_emitter=emitter, window_size=1, debounce_seconds=0)
        smoother.update(_make_scores("happy", 75.0))

        event: EmotionEvent = callback.call_args[0][0]
        assert 0.0 <= event.confidence <= 1.0
        assert event.all_scores["happy"] <= 1.0
