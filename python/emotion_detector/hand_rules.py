"""Hand gesture detection rules based on MediaPipe Hand landmarks.

Each rule takes a list of 21 hand landmarks and returns (detected, confidence).
Landmarks are normalized x/y/z coordinates.

MediaPipe Hand landmark indices:
    0: wrist
    1-4: thumb (cmc, mcp, ip, tip)
    5-8: index finger (mcp, pip, dip, tip)
    9-12: middle finger (mcp, pip, dip, tip)
    13-16: ring finger (mcp, pip, dip, tip)
    17-20: pinky (mcp, pip, dip, tip)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HandLandmark:
    """Single hand landmark with normalized coordinates."""

    x: float
    y: float
    z: float = 0.0


@dataclass
class GestureResult:
    """Result from gesture detection on a single hand."""

    gesture: str | None = None  # e.g. "middle_finger", "thumbs_up"
    confidence: float = 0.0
    hand_label: str = ""  # "Left" or "Right"


# Landmark index constants
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20


def _is_finger_extended(
    lms: list[HandLandmark],
    mcp: int,
    pip: int,
    dip: int,
    tip: int,
) -> bool:
    """Check if a finger is extended (tip above pip, pip above mcp in y).

    Y axis is inverted: lower y = higher position.
    A finger is extended when its tip is above (lower y) its pip joint.
    """
    return lms[tip].y < lms[pip].y and lms[dip].y < lms[mcp].y


def _is_finger_curled(
    lms: list[HandLandmark],
    mcp: int,
    pip: int,
    tip: int,
) -> bool:
    """Check if a finger is curled (tip below or near mcp)."""
    return lms[tip].y > lms[mcp].y


def _is_thumb_extended(lms: list[HandLandmark]) -> bool:
    """Check if thumb is extended (tip far from index mcp)."""
    thumb_tip = lms[THUMB_TIP]
    index_mcp = lms[INDEX_MCP]
    dx = abs(thumb_tip.x - index_mcp.x)
    dy = abs(thumb_tip.y - index_mcp.y)
    return (dx + dy) > 0.1


def _is_thumb_up(lms: list[HandLandmark]) -> bool:
    """Check if thumb is pointing up (tip above mcp in y)."""
    return lms[THUMB_TIP].y < lms[THUMB_MCP].y


def is_middle_finger(lms: list[HandLandmark]) -> tuple[bool, float]:
    """Detect middle finger gesture: only middle finger extended, others curled."""
    middle_extended = _is_finger_extended(lms, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP)
    index_curled = _is_finger_curled(lms, INDEX_MCP, INDEX_PIP, INDEX_TIP)
    ring_curled = _is_finger_curled(lms, RING_MCP, RING_PIP, RING_TIP)
    pinky_curled = _is_finger_curled(lms, PINKY_MCP, PINKY_PIP, PINKY_TIP)

    if middle_extended and index_curled and ring_curled and pinky_curled:
        return True, 0.9
    return False, 0.0


def is_thumbs_up(lms: list[HandLandmark]) -> tuple[bool, float]:
    """Detect thumbs up: thumb extended upward, all fingers curled."""
    thumb_up = _is_thumb_up(lms) and _is_thumb_extended(lms)
    index_curled = _is_finger_curled(lms, INDEX_MCP, INDEX_PIP, INDEX_TIP)
    middle_curled = _is_finger_curled(lms, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP)
    ring_curled = _is_finger_curled(lms, RING_MCP, RING_PIP, RING_TIP)
    pinky_curled = _is_finger_curled(lms, PINKY_MCP, PINKY_PIP, PINKY_TIP)

    if thumb_up and index_curled and middle_curled and ring_curled and pinky_curled:
        return True, 0.9
    return False, 0.0


def is_fist(lms: list[HandLandmark]) -> tuple[bool, float]:
    """Detect closed fist: all fingers curled, thumb tucked."""
    index_curled = _is_finger_curled(lms, INDEX_MCP, INDEX_PIP, INDEX_TIP)
    middle_curled = _is_finger_curled(lms, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP)
    ring_curled = _is_finger_curled(lms, RING_MCP, RING_PIP, RING_TIP)
    pinky_curled = _is_finger_curled(lms, PINKY_MCP, PINKY_PIP, PINKY_TIP)
    thumb_tucked = not _is_thumb_extended(lms)

    if index_curled and middle_curled and ring_curled and pinky_curled and thumb_tucked:
        return True, 0.85
    return False, 0.0


def is_peace_sign(lms: list[HandLandmark]) -> tuple[bool, float]:
    """Detect peace/victory sign: index + middle extended, others curled."""
    index_extended = _is_finger_extended(lms, INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP)
    middle_extended = _is_finger_extended(lms, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP)
    ring_curled = _is_finger_curled(lms, RING_MCP, RING_PIP, RING_TIP)
    pinky_curled = _is_finger_curled(lms, PINKY_MCP, PINKY_PIP, PINKY_TIP)

    if index_extended and middle_extended and ring_curled and pinky_curled:
        return True, 0.85
    return False, 0.0


def is_open_palm(lms: list[HandLandmark]) -> tuple[bool, float]:
    """Detect open palm/wave: all fingers extended."""
    index_ext = _is_finger_extended(lms, INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP)
    middle_ext = _is_finger_extended(lms, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP)
    ring_ext = _is_finger_extended(lms, RING_MCP, RING_PIP, RING_DIP, RING_TIP)
    pinky_ext = _is_finger_extended(lms, PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP)
    thumb_ext = _is_thumb_extended(lms)

    if index_ext and middle_ext and ring_ext and pinky_ext and thumb_ext:
        return True, 0.8
    return False, 0.0


# Priority-ordered list of gestures to check
_GESTURE_CHECKS = [
    ("middle_finger", is_middle_finger),
    ("thumbs_up", is_thumbs_up),
    ("peace_sign", is_peace_sign),
    ("fist", is_fist),
    ("open_palm", is_open_palm),
]


def detect_gesture(lms: list[HandLandmark], hand_label: str = "") -> GestureResult:
    """Run all gesture rules and return the first match (priority-ordered)."""
    for name, check_fn in _GESTURE_CHECKS:
        detected, confidence = check_fn(lms)
        if detected:
            return GestureResult(gesture=name, confidence=confidence, hand_label=hand_label)
    return GestureResult(hand_label=hand_label)
