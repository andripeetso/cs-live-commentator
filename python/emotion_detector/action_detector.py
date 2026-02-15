"""Action detector — wraps MediaPipe PoseLandmarker for real-time action recognition."""

from __future__ import annotations

import os
import time
from collections import deque

import cv2
import numpy as np

from . import config
from .action_rules import ActionResult, Landmark, detect_all


# Path to the pose landmarker model (relative to python/ directory)
_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "pose_landmarker_lite.task",
)


class ActionDetector:
    """Extracts pose landmarks via MediaPipe and classifies actions.

    Call detect(frame) for each frame. Maintains an internal temporal
    buffer for actions that need multi-frame context (waving, clapping).

    Uses the MediaPipe Tasks API (PoseLandmarker) — not the legacy
    mp.solutions API which was removed in mediapipe 0.10.21+.
    """

    def __init__(self, buffer_size: int = config.ACTION_BUFFER_SIZE) -> None:
        self._landmarker = None  # lazy init
        self._buffer: deque[list[Landmark]] = deque(maxlen=buffer_size)
        self._frame_ts = 0  # monotonic timestamp for VIDEO mode

    def _ensure_pose(self) -> None:
        """Lazy-initialize MediaPipe PoseLandmarker."""
        if self._landmarker is not None:
            return

        import mediapipe as mp

        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=config.POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=config.POSE_MIN_TRACKING_CONFIDENCE,
        )
        self._landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._mp = mp  # keep reference for Image creation

    def detect(self, frame: np.ndarray) -> ActionResult:
        """Run pose estimation and action rules on a single frame."""
        self._ensure_pose()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        self._frame_ts += 33  # ~30fps, monotonically increasing ms
        result = self._landmarker.detect_for_video(image, self._frame_ts)

        if not result.pose_landmarks:
            return ActionResult()

        # Convert MediaPipe landmarks to our Landmark dataclass
        pose = result.pose_landmarks[0]
        landmarks = [
            Landmark(
                x=lm.x,
                y=lm.y,
                z=lm.z,
                visibility=lm.visibility,
            )
            for lm in pose
        ]

        self._buffer.append(landmarks)

        return detect_all(landmarks, self._buffer)

    def close(self) -> None:
        """Release MediaPipe resources."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
