"""Emotion/action event dataclasses and callback-based event emitter."""

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
class ActionEvent:
    """Represents a detected action change."""

    timestamp: float
    action: str  # e.g. "waving", "clapping", "hand_raised"
    confidence: float  # 0.0 - 1.0

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
        self._emotion_callbacks: list[Callable[[EmotionEvent], None]] = []
        self._action_callbacks: list[Callable[[ActionEvent], None]] = []

    def on_emotion(self, callback: Callable[[EmotionEvent], None]) -> None:
        """Register a callback for emotion change events."""
        self._emotion_callbacks.append(callback)

    def on_action(self, callback: Callable[[ActionEvent], None]) -> None:
        """Register a callback for action change events."""
        self._action_callbacks.append(callback)

    def emit(self, event: EmotionEvent) -> None:
        """Call all registered emotion callbacks."""
        for cb in self._emotion_callbacks:
            try:
                cb(event)
            except Exception:
                pass  # Don't let a bad callback crash the pipeline

    def emit_action(self, event: ActionEvent) -> None:
        """Call all registered action callbacks."""
        for cb in self._action_callbacks:
            try:
                cb(event)
            except Exception:
                pass
