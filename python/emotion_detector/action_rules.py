"""Heuristic action detection rules based on MediaPipe Pose landmarks.

Only includes high-confidence rules. Fine-grained gesture detection is
handled by hand_rules.py (MediaPipe HandLandmarker) and vision_analyzer.py
(GPT-5-mini vision API).

MediaPipe Pose landmark indices used:
    11: left_shoulder, 12: right_shoulder
    15: left_wrist, 16: right_wrist
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Landmark:
    """Single pose landmark with x, y, z (normalized 0-1) and visibility."""

    x: float
    y: float
    z: float = 0.0
    visibility: float = 0.0


@dataclass
class ActionResult:
    """Detected actions from a single frame."""

    actions: dict[str, float] = field(default_factory=dict)  # action_name -> confidence 0-1

    @property
    def dominant_action(self) -> str | None:
        if not self.actions:
            return None
        top = max(self.actions, key=self.actions.get)
        return top if self.actions[top] > 0.0 else None


# --- Landmark helpers ---

def _visible(lm: Landmark, threshold: float = 0.5) -> bool:
    return lm.visibility >= threshold


# --- Action rules ---

def is_hand_raised(landmarks: list[Landmark]) -> float:
    """Detect one or both hands raised above shoulders.

    Returns confidence 0.0-1.0 based on how far wrist is above shoulder.
    """
    l_shoulder, r_shoulder = landmarks[11], landmarks[12]
    l_wrist, r_wrist = landmarks[15], landmarks[16]

    if not (_visible(l_shoulder) or _visible(r_shoulder)):
        return 0.0

    best = 0.0

    # Left hand raised (y axis is inverted: lower y = higher position)
    if _visible(l_wrist) and _visible(l_shoulder):
        delta = l_shoulder.y - l_wrist.y
        if delta > 0.08:  # wrist significantly above shoulder
            best = max(best, min(1.0, delta / 0.25))

    # Right hand raised
    if _visible(r_wrist) and _visible(r_shoulder):
        delta = r_shoulder.y - r_wrist.y
        if delta > 0.08:
            best = max(best, min(1.0, delta / 0.25))

    return best


def detect_all(
    landmarks: list[Landmark],
    buffer: deque[list[Landmark]],
) -> ActionResult:
    """Run all action rules and return combined result."""
    actions = {}

    hand_raised = is_hand_raised(landmarks)
    if hand_raised > 0.3:
        actions["hand_raised"] = hand_raised

    return ActionResult(actions=actions)
