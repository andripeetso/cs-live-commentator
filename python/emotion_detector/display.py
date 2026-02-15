"""Annotated display — renders webcam feed with emotion + action overlays."""

from __future__ import annotations

import queue
import time

import cv2
import numpy as np

from . import config
from .action_smoothing import ActionState
from .events import DetectionResult
from .hand_rules import GestureResult
from .smoothing import SmoothedState


class AnnotatedDisplay:
    """Consumer: reads processed frames from result queue and renders them.

    MUST run on the main thread (macOS requirement for cv2.imshow).
    """

    def __init__(self, result_queue: queue.Queue) -> None:
        self._result_queue = result_queue
        self.running = True
        self._fps_counter = 0
        self._fps_timer = time.time()
        self._fps_display = 0.0

    def run(self) -> None:
        """Main display loop (blocking). Call from the main thread."""
        while self.running:
            try:
                frame, result, smoothed, action_state, gesture = self._result_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            except (ValueError, TypeError):
                continue

            self._update_fps()
            annotated = self._annotate(frame, result, smoothed, action_state, gesture)
            cv2.imshow("Emotion Detector", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.running = False

    def _update_fps(self) -> None:
        self._fps_counter += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps_display = self._fps_counter / elapsed
            self._fps_counter = 0
            self._fps_timer = time.time()

    def _annotate(
        self,
        frame: np.ndarray,
        result: DetectionResult,
        smoothed: SmoothedState,
        action_state: ActionState,
        gesture: GestureResult,
    ) -> np.ndarray:
        """Draw all overlays on the frame."""
        # FPS counter (top-left)
        cv2.putText(
            frame,
            f"FPS: {self._fps_display:.1f}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            config.FONT_SCALE,
            config.TEXT_COLOR,
            1,
        )

        # Processing time
        cv2.putText(
            frame,
            f"Proc: {result.processing_time_ms:.0f}ms",
            (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            config.FONT_SCALE * 0.8,
            (180, 180, 180),
            1,
        )

        if not result.face_found:
            cv2.putText(
                frame,
                "No face detected",
                (10, config.FRAME_HEIGHT - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                config.FONT_SCALE,
                (0, 0, 255),
                config.FONT_THICKNESS,
            )

        if result.face_found:
            x, y, w, h = result.face_region

            # Bounding box
            cv2.rectangle(frame, (x, y), (x + w, y + h), config.BOX_COLOR, 2)

            # Emotion label above the box
            label = f"{smoothed.dominant} {smoothed.confidence:.0%}"
            label_y = max(y - 10, 20)
            cv2.putText(
                frame,
                label,
                (x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                config.FONT_SCALE * 1.2,
                config.BOX_COLOR,
                config.FONT_THICKNESS,
            )

            # Emotion bar chart (right side)
            self._draw_emotion_bars(frame, smoothed.scores)

        # Action label (bottom-left)
        self._draw_action_label(frame, action_state)

        # Gesture label (bottom-left, below action)
        self._draw_gesture_label(frame, gesture)

        return frame

    def _draw_action_label(
        self,
        frame: np.ndarray,
        action_state: ActionState,
    ) -> None:
        """Draw detected action label at the bottom of the frame."""
        if action_state.action is None:
            return

        label = action_state.action.upper().replace("_", " ")
        confidence = f"{action_state.confidence:.0%}"
        text = f"{label} {confidence}"

        # Cyan text, bottom-left area
        y = config.FRAME_HEIGHT - 50
        cv2.putText(
            frame,
            text,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            config.FONT_SCALE * 1.4,
            (255, 255, 0),  # cyan in BGR
            config.FONT_THICKNESS,
        )

    def _draw_gesture_label(
        self,
        frame: np.ndarray,
        gesture: GestureResult,
    ) -> None:
        """Draw detected hand gesture label below the action label."""
        if gesture.gesture is None:
            return

        label = gesture.gesture.upper().replace("_", " ")
        hand = f" ({gesture.hand_label})" if gesture.hand_label else ""
        text = f"{label}{hand} {gesture.confidence:.0%}"

        # Color based on gesture type
        color = (0, 0, 255) if gesture.gesture == "middle_finger" else (0, 255, 255)  # red or yellow

        y = config.FRAME_HEIGHT - 80
        cv2.putText(
            frame,
            text,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            config.FONT_SCALE * 1.4,
            color,
            config.FONT_THICKNESS,
        )

    def _draw_emotion_bars(
        self,
        frame: np.ndarray,
        scores: dict[str, float],
    ) -> None:
        """Draw horizontal bar chart of all emotion confidences."""
        if not scores:
            return

        bar_x = config.FRAME_WIDTH - config.BAR_WIDTH - 15
        bar_y_start = 20

        for i, (emotion, score) in enumerate(sorted(scores.items())):
            y = bar_y_start + i * (config.BAR_HEIGHT + config.BAR_PADDING)
            pct = score / 100.0  # scores are 0-100 from smoother

            # Background bar
            cv2.rectangle(
                frame,
                (bar_x, y),
                (bar_x + config.BAR_WIDTH, y + config.BAR_HEIGHT),
                config.BAR_BG_COLOR,
                -1,
            )

            # Filled bar
            fill_w = int(config.BAR_WIDTH * pct)
            color = config.EMOTION_COLORS.get(emotion, (200, 200, 200))
            if fill_w > 0:
                cv2.rectangle(
                    frame,
                    (bar_x, y),
                    (bar_x + fill_w, y + config.BAR_HEIGHT),
                    color,
                    -1,
                )

            # Label
            cv2.putText(
                frame,
                f"{emotion[:3]} {pct:.0%}",
                (bar_x - 60, y + config.BAR_HEIGHT - 3),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
            )
