"""Detector — runs MediaPipe (every frame) + DeepFace (every Nth frame) in a processing thread."""

from __future__ import annotations

import queue
import threading
import time

import numpy as np

from . import config
from .action_detector import ActionDetector
from .action_smoothing import ActionSmoother, ActionState
from .events import DetectionResult, EventEmitter
from .smoothing import EmotionSmoother, SmoothedState


class EmotionDetector:
    """Processor: reads frames from capture queue, runs detection, writes results.

    Runs in a daemon thread. Interleaves two detectors:
    - MediaPipe Pose: every frame (~25ms) → action detection
    - DeepFace: every Nth frame (~100ms) → emotion detection

    Produces (frame, DetectionResult, SmoothedState, ActionState)
    tuples into the result queue for the display to consume.
    """

    def __init__(
        self,
        capture_queue: queue.Queue,
        result_queue: queue.Queue,
        smoother: EmotionSmoother,
        action_smoother: ActionSmoother,
    ) -> None:
        self._capture_queue = capture_queue
        self._result_queue = result_queue
        self._smoother = smoother
        self._action_smoother = action_smoother
        self._running = False
        self._thread: threading.Thread | None = None
        self._deepface = None  # lazy import
        self._action_detector = ActionDetector()

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
        print("[DETECTOR] Loading MediaPipe Pose model...")
        # Warm up action detector (lazy init)
        self._action_detector._ensure_pose()
        print("[DETECTOR] MediaPipe Pose loaded")

        print("[DETECTOR] Loading DeepFace emotion model...")
        self._ensure_deepface()
        print("[DETECTOR] DeepFace loaded. Processing frames...")

        frame_count = 0
        last_dominant_emotion = None
        last_dominant_action = None

        # Keep latest emotion result for frames where DeepFace doesn't run
        latest_emotion_result = DetectionResult(face_found=False)
        latest_smoothed = self._smoother.state

        while self._running:
            try:
                frame = self._capture_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            start = time.time()

            # --- Action detection: every frame ---
            action_result = self._action_detector.detect(frame)
            action_state = self._action_smoother.update(action_result)

            # Log action changes
            if action_state.action != last_dominant_action:
                if action_state.action is not None:
                    print(f"[ACTION] {action_state.action.upper().replace('_', ' ')} (confidence: {action_state.confidence:.0%})")
                elif last_dominant_action is not None:
                    print("[ACTION] (idle)")
                last_dominant_action = action_state.action

            # --- Emotion detection: every Nth frame ---
            if frame_count % config.DEEPFACE_EVERY_N == 0:
                emotion_start = time.time()
                result = self._analyze_frame(frame)
                result.processing_time_ms = (time.time() - emotion_start) * 1000

                # Feed to smoother if face found
                if result.face_found:
                    latest_smoothed = self._smoother.update(
                        result.emotion_scores,
                        result.face_region,
                    )

                    if latest_smoothed.dominant != last_dominant_emotion:
                        top_3 = sorted(latest_smoothed.scores.items(), key=lambda x: x[1], reverse=True)[:3]
                        top_str = ", ".join(f"{e}:{s:.0f}%" for e, s in top_3)
                        print(f"[EMOTION] {latest_smoothed.dominant.upper()} ({latest_smoothed.confidence:.0%}) | {top_str} | {result.processing_time_ms:.0f}ms")
                        last_dominant_emotion = latest_smoothed.dominant
                else:
                    if last_dominant_emotion is not None:
                        print(f"[EMOTION] No face detected ({result.processing_time_ms:.0f}ms)")
                        last_dominant_emotion = None

                latest_emotion_result = result

            total_ms = (time.time() - start) * 1000
            frame_count += 1

            if frame_count == 1:
                print(f"[DETECTOR] First frame processed in {total_ms:.0f}ms")

            # Put result for display (4-tuple now)
            if self._result_queue.full():
                try:
                    self._result_queue.get_nowait()
                except queue.Empty:
                    pass
            self._result_queue.put((frame, latest_emotion_result, latest_smoothed, action_state))

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
        self._action_detector.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
