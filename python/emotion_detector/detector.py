"""Emotion detector — wraps DeepFace.analyze() in a processing thread."""

from __future__ import annotations

import queue
import threading
import time

import numpy as np

from . import config
from .events import DetectionResult, EventEmitter
from .smoothing import EmotionSmoother, SmoothedState


class EmotionDetector:
    """Processor: reads frames from capture queue, runs DeepFace, writes results.

    Runs in a daemon thread. Produces (frame, DetectionResult, SmoothedState)
    tuples into the result queue for the display to consume.
    """

    def __init__(
        self,
        capture_queue: queue.Queue,
        result_queue: queue.Queue,
        smoother: EmotionSmoother,
    ) -> None:
        self._capture_queue = capture_queue
        self._result_queue = result_queue
        self._smoother = smoother
        self._running = False
        self._thread: threading.Thread | None = None
        self._deepface = None  # lazy import

    def start(self) -> None:
        """Start the detector thread (daemon)."""
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def _ensure_deepface(self) -> None:
        """Lazy import DeepFace to avoid slow import at startup."""
        if self._deepface is None:
            from deepface import DeepFace
            self._deepface = DeepFace

    def _process_loop(self) -> None:
        self._ensure_deepface()

        while self._running:
            try:
                frame = self._capture_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            start = time.time()
            result = self._analyze_frame(frame)
            result.processing_time_ms = (time.time() - start) * 1000

            # Feed to smoother if face found
            smoothed = self._smoother.state
            if result.face_found:
                smoothed = self._smoother.update(
                    result.emotion_scores,
                    result.face_region,
                )

            # Put result for display
            if self._result_queue.full():
                try:
                    self._result_queue.get_nowait()
                except queue.Empty:
                    pass
            self._result_queue.put((frame, result, smoothed))

    def _analyze_frame(self, frame: np.ndarray) -> DetectionResult:
        """Run DeepFace.analyze() on a single frame."""
        try:
            results = self._deepface.analyze(
                img_path=frame,
                actions=config.ACTIONS,
                enforce_detection=config.ENFORCE_DETECTION,
                detector_backend=config.DETECTOR_BACKEND,
                silent=True,
            )

            if not results:
                return DetectionResult(face_found=False)

            face = results[0]
            region = face.get("region", {})

            return DetectionResult(
                face_found=True,
                dominant_emotion=face["dominant_emotion"],
                emotion_scores=face["emotion"],
                face_region=(
                    region.get("x", 0),
                    region.get("y", 0),
                    region.get("w", 0),
                    region.get("h", 0),
                ),
            )

        except Exception:
            return DetectionResult(face_found=False)

    def stop(self) -> None:
        """Signal the detector thread to stop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
