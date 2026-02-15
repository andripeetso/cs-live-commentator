"""Temporal smoothing and debouncing for emotion detection."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from . import config
from .events import EmotionEvent, EventEmitter


@dataclass
class SmoothedState:
    """Current smoothed emotion state."""

    dominant: str = "neutral"
    scores: dict[str, float] = None  # averaged scores, 0-100
    confidence: float = 0.0  # confidence of dominant emotion, 0-1

    def __post_init__(self) -> None:
        if self.scores is None:
            self.scores = {}


class EmotionSmoother:
    """Rolling average over N frames with debounced event emission.

    Emits an EmotionEvent only when:
    1. Dominant emotion changed from last emission
    2. At least DEBOUNCE_SECONDS have passed
    """

    def __init__(
        self,
        event_emitter: EventEmitter,
        window_size: int = config.SMOOTHING_WINDOW,
        debounce_seconds: float = config.DEBOUNCE_SECONDS,
    ) -> None:
        self._emitter = event_emitter
        self._window_size = window_size
        self._debounce_seconds = debounce_seconds
        self._history: deque[dict[str, float]] = deque(maxlen=window_size)
        self._last_emitted_emotion: str | None = None
        self._last_emit_time: float = 0.0
        self.state = SmoothedState()

    def update(
        self,
        raw_scores: dict[str, float],
        face_region: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> SmoothedState:
        """Feed new raw emotion scores (0-100) and get smoothed state back."""
        self._history.append(raw_scores)

        # Average across window
        averaged: dict[str, float] = {}
        for emotion in raw_scores:
            vals = [h.get(emotion, 0.0) for h in self._history]
            averaged[emotion] = sum(vals) / len(vals)

        # Find dominant
        dominant = max(averaged, key=averaged.get)
        confidence = averaged[dominant] / 100.0  # normalize to 0-1

        self.state = SmoothedState(
            dominant=dominant,
            scores=averaged,
            confidence=confidence,
        )

        # Check if we should emit
        now = time.time()
        should_emit = (
            dominant != self._last_emitted_emotion
            and (now - self._last_emit_time) >= self._debounce_seconds
        )

        if should_emit:
            self._last_emitted_emotion = dominant
            self._last_emit_time = now

            normalized_scores = {k: round(v / 100.0, 3) for k, v in averaged.items()}
            event = EmotionEvent(
                timestamp=now,
                dominant_emotion=dominant,
                confidence=round(confidence, 3),
                all_scores=normalized_scores,
                face_region=face_region,
            )
            self._emitter.emit(event)

        return self.state
