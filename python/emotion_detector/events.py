"""Emotion event dataclass and callback-based event emitter."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Callable


@dataclass
class EmotionEvent:
    """Represents a detected emotion change."""

    timestamp: float
    dominant_emotion: str
    confidence: float  # 0.0 - 1.0 (normalized from DeepFace's 0-100)
    all_scores: dict[str, float]  # all 7 emotions, normalized 0.0-1.0
    face_region: tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class DetectionResult:
    """Raw result from a single frame analysis."""

    face_found: bool
    dominant_emotion: str = "neutral"
    emotion_scores: dict[str, float] = field(default_factory=dict)  # 0-100 from DeepFace
    face_region: tuple[int, int, int, int] = (0, 0, 0, 0)
    processing_time_ms: float = 0.0


class EventEmitter:
    """Simple callback-based event system.

    For MVP: prints JSON to stdout.
    Future: register callbacks that forward to WebSocket/HTTP.
    """

    def __init__(self) -> None:
        self._callbacks: list[Callable[[EmotionEvent], None]] = []

    def on_emotion(self, callback: Callable[[EmotionEvent], None]) -> None:
        """Register a callback for emotion change events."""
        self._callbacks.append(callback)

    def emit(self, event: EmotionEvent) -> None:
        """Call all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass  # Don't let a bad callback crash the pipeline
