"""Hand gesture detector — wraps MediaPipe HandLandmarker for finger-level gesture recognition."""

from __future__ import annotations

import os

import cv2
import numpy as np

from . import config
from .hand_rules import GestureResult, HandLandmark, detect_gesture

_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "hand_landmarker.task",
)


class HandDetector:
    """Extracts hand landmarks via MediaPipe and classifies gestures.

    Uses the MediaPipe Tasks API (HandLandmarker) in VIDEO running mode.
    Detects up to 2 hands and returns the most confident gesture found.
    """

    def __init__(self) -> None:
        self._landmarker = None  # lazy init
        self._frame_ts = 0  # monotonic timestamp for VIDEO mode
        self._mp = None

    def _ensure_hands(self) -> None:
        """Lazy-initialize MediaPipe HandLandmarker."""
        if self._landmarker is not None:
            return

        import mediapipe as mp

        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=config.HAND_MIN_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=config.HAND_MIN_PRESENCE_CONFIDENCE,
            min_tracking_confidence=config.HAND_MIN_TRACKING_CONFIDENCE,
        )
        self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self._mp = mp

    def detect(self, frame: np.ndarray) -> GestureResult:
        """Run hand landmark detection and gesture classification on a frame.

        Returns the highest-priority gesture detected across all visible hands.
        """
        self._ensure_hands()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        self._frame_ts += 33  # ~30fps, monotonically increasing ms
        result = self._landmarker.detect_for_video(image, self._frame_ts)

        if not result.hand_landmarks:
            return GestureResult()

        # Check each detected hand for gestures, return first match
        best_gesture = GestureResult()
        for idx, hand_lms in enumerate(result.hand_landmarks):
            hand_label = result.handedness[idx][0].category_name  # "Left" or "Right"

            landmarks = [
                HandLandmark(x=lm.x, y=lm.y, z=lm.z)
                for lm in hand_lms
            ]

            gesture = detect_gesture(landmarks, hand_label=hand_label)
            if gesture.gesture is not None and gesture.confidence > best_gesture.confidence:
                best_gesture = gesture

        return best_gesture

    def close(self) -> None:
        """Release MediaPipe resources."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
