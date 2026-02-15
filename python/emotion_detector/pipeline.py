"""Pipeline orchestrator — wires capture, detector, and display together."""

from __future__ import annotations

import queue

import cv2

from . import config
from .action_smoothing import ActionSmoother
from .capture import WebcamCapture
from .commentator import Commentator
from .detector import EmotionDetector
from .display import AnnotatedDisplay
from .events import ActionEvent, EmotionEvent, EventEmitter
from .smoothing import EmotionSmoother


class EmotionPipeline:
    """Creates and manages all pipeline components.

    Architecture:
        Capture Thread (daemon) → Queue → Detector Thread (daemon) → Queue → Display (main thread)

    The detector interleaves:
        - MediaPipe Pose (every frame) → action detection
        - DeepFace (every Nth frame) → emotion detection

    The display MUST run on the main thread (macOS cv2.imshow requirement).
    """

    def __init__(self, camera_index: int = config.CAMERA_INDEX) -> None:
        # Queues
        self._capture_queue: queue.Queue = queue.Queue(maxsize=config.CAPTURE_QUEUE_SIZE)
        self._result_queue: queue.Queue = queue.Queue(maxsize=config.RESULT_QUEUE_SIZE)

        # Event system
        self._event_emitter = EventEmitter()
        self._event_emitter.on_emotion(self._log_emotion)
        self._event_emitter.on_action(self._log_action)

        # Components
        self._smoother = EmotionSmoother(event_emitter=self._event_emitter)
        self._action_smoother = ActionSmoother(event_emitter=self._event_emitter)
        self._capture = WebcamCapture(
            camera_index=camera_index,
            frame_queue=self._capture_queue,
        )
        self._detector = EmotionDetector(
            capture_queue=self._capture_queue,
            result_queue=self._result_queue,
            smoother=self._smoother,
            action_smoother=self._action_smoother,
        )
        self._display = AnnotatedDisplay(result_queue=self._result_queue)
        self._commentator = Commentator(event_emitter=self._event_emitter)

    @property
    def event_emitter(self) -> EventEmitter:
        """Access the event emitter to register additional callbacks."""
        return self._event_emitter

    def run(self) -> None:
        """Start the pipeline. Blocks until user quits.

        Opens camera on main thread (required by macOS), then starts
        capture and detector threads, then runs display on main thread.
        """
        # Camera MUST be opened on main thread for macOS authorization
        if not self._capture.open_camera():
            print("ERROR: Could not open camera. Check permissions in System Settings > Privacy > Camera.")
            return

        print("[PIPELINE] Loading models (first run may download ~100MB)...")
        self._capture.start()
        self._detector.start()
        self._commentator.start()
        print("[PIPELINE] Pipeline running. Press 'q' in the preview window to quit.")
        print("[PIPELINE] Detecting: emotions (DeepFace) + actions (MediaPipe Pose)")

        try:
            self._display.run()  # Blocking — runs on main thread
        except KeyboardInterrupt:
            print("\n[PIPELINE] Interrupted by user")
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully stop all components."""
        try:
            self._display.running = False
            self._commentator.stop()
            self._capture.stop()
            self._detector.stop()
            cv2.destroyAllWindows()
            print("[PIPELINE] Pipeline stopped.")
        except KeyboardInterrupt:
            print("\n[PIPELINE] Force quit.")
            cv2.destroyAllWindows()

    @staticmethod
    def _log_emotion(event: EmotionEvent) -> None:
        """Default handler: print emotion events as JSON to stdout."""
        print(f"[EVENT] Emotion changed → {event.dominant_emotion} ({event.confidence:.0%})")
        print(f"        {event.to_json()}")

    @staticmethod
    def _log_action(event: ActionEvent) -> None:
        """Default handler: print action events to stdout."""
        label = event.action.upper().replace("_", " ")
        print(f"[EVENT] Action detected → {label} ({event.confidence:.0%})")
        print(f"        {event.to_json()}")
