"""Tests for EmotionEvent and EventEmitter."""

import json
from unittest.mock import MagicMock

from emotion_detector.events import DetectionResult, EmotionEvent, EventEmitter


class TestEmotionEvent:
    def test_to_dict(self):
        event = EmotionEvent(
            timestamp=1000.0,
            dominant_emotion="happy",
            confidence=0.87,
            all_scores={"happy": 0.87, "sad": 0.05},
            face_region=(10, 20, 100, 100),
        )
        d = event.to_dict()
        assert d["dominant_emotion"] == "happy"
        assert d["confidence"] == 0.87
        assert d["face_region"] == (10, 20, 100, 100)

    def test_to_json_is_valid(self):
        event = EmotionEvent(
            timestamp=1000.0,
            dominant_emotion="sad",
            confidence=0.6,
            all_scores={"happy": 0.1, "sad": 0.6},
            face_region=(0, 0, 50, 50),
        )
        parsed = json.loads(event.to_json())
        assert parsed["dominant_emotion"] == "sad"
        assert isinstance(parsed["all_scores"], dict)


class TestDetectionResult:
    def test_no_face(self):
        result = DetectionResult(face_found=False)
        assert not result.face_found
        assert result.dominant_emotion == "neutral"

    def test_with_face(self):
        result = DetectionResult(
            face_found=True,
            dominant_emotion="surprise",
            emotion_scores={"surprise": 80.0},
            face_region=(10, 20, 50, 50),
        )
        assert result.face_found
        assert result.dominant_emotion == "surprise"


class TestEventEmitter:
    def test_register_and_emit(self):
        emitter = EventEmitter()
        callback = MagicMock()
        emitter.on_emotion(callback)

        event = EmotionEvent(
            timestamp=1000.0,
            dominant_emotion="happy",
            confidence=0.9,
            all_scores={"happy": 0.9},
        )
        emitter.emit(event)

        callback.assert_called_once_with(event)

    def test_multiple_callbacks(self):
        emitter = EventEmitter()
        cb1 = MagicMock()
        cb2 = MagicMock()
        emitter.on_emotion(cb1)
        emitter.on_emotion(cb2)

        event = EmotionEvent(
            timestamp=1000.0,
            dominant_emotion="angry",
            confidence=0.7,
            all_scores={"angry": 0.7},
        )
        emitter.emit(event)

        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_bad_callback_doesnt_crash(self):
        emitter = EventEmitter()

        def bad_callback(event):
            raise ValueError("boom")

        good_callback = MagicMock()
        emitter.on_emotion(bad_callback)
        emitter.on_emotion(good_callback)

        event = EmotionEvent(
            timestamp=1000.0,
            dominant_emotion="neutral",
            confidence=0.5,
            all_scores={"neutral": 0.5},
        )
        emitter.emit(event)

        # Good callback still called despite bad one raising
        good_callback.assert_called_once()
