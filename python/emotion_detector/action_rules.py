"""Heuristic action detection rules based on MediaPipe Pose landmarks.

Each rule is a pure function that takes landmarks (and optionally a temporal
buffer of past landmarks) and returns a confidence score (0.0–1.0).

MediaPipe Pose landmark indices used:
    0: nose, 9: mouth_left, 10: mouth_right
    11: left_shoulder, 12: right_shoulder
    13: left_elbow, 14: right_elbow
    15: left_wrist, 16: right_wrist
    23: left_hip, 24: right_hip
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Landmark:
    """Single pose landmark with x, y, z (normalized 0–1) and visibility."""

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

def _distance(a: Landmark, b: Landmark) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _angle(a: Landmark, b: Landmark, c: Landmark) -> float:
    """Angle at point b formed by segments ba and bc, in degrees."""
    ba = (a.x - b.x, a.y - b.y)
    bc = (c.x - b.x, c.y - b.y)
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    mag_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2)
    mag_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2)
    if mag_ba * mag_bc == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_angle))


def _visible(lm: Landmark, threshold: float = 0.5) -> bool:
    return lm.visibility >= threshold


# --- Action rules ---

def is_hand_raised(landmarks: list[Landmark]) -> float:
    """Detect one or both hands raised above shoulders.

    Returns confidence 0.0–1.0 based on how far wrist is above shoulder.
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


def is_waving(
    landmarks: list[Landmark],
    buffer: deque[list[Landmark]],
    min_oscillations: int = 2,
) -> float:
    """Detect waving: hand raised + wrist X oscillating over recent frames.

    Needs a buffer of at least 8 frames to detect oscillation.
    """
    if len(buffer) < 8:
        return 0.0

    # Check if hand is currently raised
    if is_hand_raised(landmarks) < 0.3:
        return 0.0

    # Track wrist X position across buffer for both wrists
    for wrist_idx in (15, 16):
        shoulder_idx = 11 if wrist_idx == 15 else 12
        xs = []
        for frame_lms in buffer:
            wrist = frame_lms[wrist_idx]
            shoulder = frame_lms[shoulder_idx]
            if _visible(wrist) and _visible(shoulder) and shoulder.y - wrist.y > 0.05:
                xs.append(wrist.x)

        if len(xs) < 6:
            continue

        # Count direction changes (oscillations)
        direction_changes = 0
        for i in range(2, len(xs)):
            prev_dir = xs[i - 1] - xs[i - 2]
            curr_dir = xs[i] - xs[i - 1]
            if prev_dir * curr_dir < 0 and abs(curr_dir) > 0.005:
                direction_changes += 1

        if direction_changes >= min_oscillations:
            return min(1.0, direction_changes / 4.0)

    return 0.0


def is_clapping(
    landmarks: list[Landmark],
    buffer: deque[list[Landmark]],
    min_claps: int = 1,
) -> float:
    """Detect clapping: both wrists repeatedly coming close together.

    Looks for oscillation in wrist-to-wrist distance over recent frames.
    """
    if len(buffer) < 5:
        return 0.0

    l_wrist, r_wrist = landmarks[15], landmarks[16]
    if not (_visible(l_wrist) and _visible(r_wrist)):
        return 0.0

    # Track wrist-to-wrist distance
    distances = []
    for frame_lms in buffer:
        lw, rw = frame_lms[15], frame_lms[16]
        if _visible(lw) and _visible(rw):
            distances.append(_distance(lw, rw))

    if len(distances) < 4:
        return 0.0

    # Count close-far transitions (clap cycles)
    close_threshold = 0.08  # wrists very close
    far_threshold = 0.15   # wrists apart
    clap_cycles = 0
    was_close = distances[0] < close_threshold

    for d in distances[1:]:
        if was_close and d > far_threshold:
            was_close = False
        elif not was_close and d < close_threshold:
            was_close = True
            clap_cycles += 1

    # Current frame: wrists close together
    current_dist = _distance(l_wrist, r_wrist)
    if current_dist < close_threshold and clap_cycles >= min_claps:
        return min(1.0, clap_cycles / 2.0)

    return 0.0


def is_drinking(landmarks: list[Landmark]) -> float:
    """Detect drinking: wrist near mouth with elbow flexion.

    Returns confidence based on proximity of wrist to mouth area.
    """
    mouth_left, mouth_right = landmarks[9], landmarks[10]
    mouth_x = (mouth_left.x + mouth_right.x) / 2
    mouth_y = (mouth_left.y + mouth_right.y) / 2
    mouth = Landmark(x=mouth_x, y=mouth_y)

    for wrist_idx, elbow_idx, shoulder_idx in ((15, 13, 11), (16, 14, 12)):
        wrist = landmarks[wrist_idx]
        elbow = landmarks[elbow_idx]
        shoulder = landmarks[shoulder_idx]

        if not (_visible(wrist) and _visible(elbow) and _visible(shoulder)):
            continue

        dist_to_mouth = _distance(wrist, mouth)
        elbow_angle = _angle(shoulder, elbow, wrist)

        # Wrist close to mouth AND elbow bent (not straight arm across face)
        if dist_to_mouth < 0.12 and elbow_angle < 120:
            confidence = max(0.0, 1.0 - dist_to_mouth / 0.12)
            return confidence

    return 0.0


def is_arms_crossed(landmarks: list[Landmark]) -> float:
    """Detect arms crossed: wrists near opposite elbows, in front of chest."""
    l_wrist, r_wrist = landmarks[15], landmarks[16]
    l_elbow, r_elbow = landmarks[13], landmarks[14]
    l_shoulder, r_shoulder = landmarks[11], landmarks[12]

    if not all(_visible(lm) for lm in (l_wrist, r_wrist, l_elbow, r_elbow, l_shoulder, r_shoulder)):
        return 0.0

    # Wrists should be crossed: left wrist near right side and vice versa
    l_wrist_on_right = l_wrist.x > (l_shoulder.x + r_shoulder.x) / 2
    r_wrist_on_left = r_wrist.x < (l_shoulder.x + r_shoulder.x) / 2

    # Wrists should be at chest height (between shoulders and hips)
    chest_y = (l_shoulder.y + r_shoulder.y) / 2
    wrists_at_chest = (
        abs(l_wrist.y - chest_y) < 0.15
        and abs(r_wrist.y - chest_y) < 0.15
    )

    if l_wrist_on_right and r_wrist_on_left and wrists_at_chest:
        return 0.8

    return 0.0


def detect_all(
    landmarks: list[Landmark],
    buffer: deque[list[Landmark]],
) -> ActionResult:
    """Run all action rules and return combined result."""
    actions = {}

    hand_raised = is_hand_raised(landmarks)
    if hand_raised > 0.3:
        # Check if it's specifically waving
        waving = is_waving(landmarks, buffer)
        if waving > 0.3:
            actions["waving"] = waving
        else:
            actions["hand_raised"] = hand_raised

    clapping = is_clapping(landmarks, buffer)
    if clapping > 0.3:
        actions["clapping"] = clapping

    drinking = is_drinking(landmarks)
    if drinking > 0.3:
        actions["drinking"] = drinking

    arms_crossed = is_arms_crossed(landmarks)
    if arms_crossed > 0.3:
        actions["arms_crossed"] = arms_crossed

    return ActionResult(actions=actions)
