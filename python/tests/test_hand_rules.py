"""Tests for hand gesture detection rules."""

from emotion_detector.hand_rules import (
    GestureResult,
    HandLandmark,
    detect_gesture,
    is_fist,
    is_middle_finger,
    is_open_palm,
    is_peace_sign,
    is_thumbs_up,
)


def _hlm(x: float, y: float, z: float = 0.0) -> HandLandmark:
    """Shorthand to create a hand landmark."""
    return HandLandmark(x=x, y=y, z=z)


def _make_hand_landmarks(overrides: dict[int, HandLandmark] | None = None) -> list[HandLandmark]:
    """Create 21 default hand landmarks with optional overrides.

    Default: relaxed open hand, fingers slightly extended upward.
    Wrist at bottom (y=0.8), fingertips at top (y=0.2-0.4).
    """
    # Default open hand (all fingers extended)
    defaults = {
        0: _hlm(0.5, 0.8),       # wrist

        # Thumb
        1: _hlm(0.35, 0.7),      # thumb_cmc
        2: _hlm(0.30, 0.6),      # thumb_mcp
        3: _hlm(0.25, 0.5),      # thumb_ip
        4: _hlm(0.20, 0.4),      # thumb_tip

        # Index finger
        5: _hlm(0.40, 0.5),      # index_mcp
        6: _hlm(0.40, 0.4),      # index_pip
        7: _hlm(0.40, 0.3),      # index_dip
        8: _hlm(0.40, 0.2),      # index_tip

        # Middle finger
        9: _hlm(0.50, 0.48),     # middle_mcp
        10: _hlm(0.50, 0.38),    # middle_pip
        11: _hlm(0.50, 0.28),    # middle_dip
        12: _hlm(0.50, 0.18),    # middle_tip

        # Ring finger
        13: _hlm(0.60, 0.5),     # ring_mcp
        14: _hlm(0.60, 0.4),     # ring_pip
        15: _hlm(0.60, 0.3),     # ring_dip
        16: _hlm(0.60, 0.2),     # ring_tip

        # Pinky
        17: _hlm(0.70, 0.55),    # pinky_mcp
        18: _hlm(0.70, 0.45),    # pinky_pip
        19: _hlm(0.70, 0.35),    # pinky_dip
        20: _hlm(0.70, 0.25),    # pinky_tip
    }
    if overrides:
        defaults.update(overrides)
    return [defaults[i] for i in range(21)]


def _make_fist() -> list[HandLandmark]:
    """All fingers curled into a fist, thumb tucked."""
    return _make_hand_landmarks({
        # Thumb tucked (very close to index mcp at 0.40, 0.5)
        1: _hlm(0.38, 0.65),     # thumb_cmc
        2: _hlm(0.38, 0.6),      # thumb_mcp
        3: _hlm(0.39, 0.55),     # thumb_ip
        4: _hlm(0.40, 0.53),     # thumb_tip — right on index mcp

        # Index curled
        6: _hlm(0.40, 0.55),     # index_pip
        7: _hlm(0.40, 0.6),      # index_dip
        8: _hlm(0.40, 0.65),     # index_tip (below mcp y=0.5)

        # Middle curled
        10: _hlm(0.50, 0.55),
        11: _hlm(0.50, 0.6),
        12: _hlm(0.50, 0.65),

        # Ring curled
        14: _hlm(0.60, 0.55),
        15: _hlm(0.60, 0.6),
        16: _hlm(0.60, 0.65),

        # Pinky curled
        18: _hlm(0.70, 0.6),
        19: _hlm(0.70, 0.65),
        20: _hlm(0.70, 0.7),
    })


def _make_middle_finger() -> list[HandLandmark]:
    """Only middle finger extended, all others curled."""
    lms = _make_fist()
    # Extend middle finger
    lms[9] = _hlm(0.50, 0.48)   # middle_mcp
    lms[10] = _hlm(0.50, 0.38)  # middle_pip
    lms[11] = _hlm(0.50, 0.28)  # middle_dip
    lms[12] = _hlm(0.50, 0.18)  # middle_tip
    return lms


def _make_thumbs_up() -> list[HandLandmark]:
    """Thumb extended upward, all fingers curled."""
    lms = _make_fist()
    # Extend thumb upward and outward
    lms[1] = _hlm(0.35, 0.7)
    lms[2] = _hlm(0.28, 0.55)
    lms[3] = _hlm(0.22, 0.4)
    lms[4] = _hlm(0.18, 0.3)   # thumb tip high and far from index mcp
    return lms


def _make_peace_sign() -> list[HandLandmark]:
    """Index + middle extended, others curled."""
    lms = _make_fist()
    # Extend index
    lms[6] = _hlm(0.40, 0.4)
    lms[7] = _hlm(0.40, 0.3)
    lms[8] = _hlm(0.40, 0.2)
    # Extend middle
    lms[10] = _hlm(0.50, 0.38)
    lms[11] = _hlm(0.50, 0.28)
    lms[12] = _hlm(0.50, 0.18)
    return lms


class TestMiddleFinger:
    def test_middle_finger_detected(self):
        lms = _make_middle_finger()
        detected, confidence = is_middle_finger(lms)
        assert detected is True
        assert confidence > 0.5

    def test_open_hand_not_middle_finger(self):
        lms = _make_hand_landmarks()  # all fingers extended
        detected, _ = is_middle_finger(lms)
        assert detected is False

    def test_fist_not_middle_finger(self):
        lms = _make_fist()
        detected, _ = is_middle_finger(lms)
        assert detected is False


class TestThumbsUp:
    def test_thumbs_up_detected(self):
        lms = _make_thumbs_up()
        detected, confidence = is_thumbs_up(lms)
        assert detected is True
        assert confidence > 0.5

    def test_open_hand_not_thumbs_up(self):
        lms = _make_hand_landmarks()
        detected, _ = is_thumbs_up(lms)
        assert detected is False

    def test_fist_not_thumbs_up(self):
        lms = _make_fist()
        detected, _ = is_thumbs_up(lms)
        assert detected is False


class TestFist:
    def test_fist_detected(self):
        lms = _make_fist()
        detected, confidence = is_fist(lms)
        assert detected is True
        assert confidence > 0.5

    def test_open_hand_not_fist(self):
        lms = _make_hand_landmarks()
        detected, _ = is_fist(lms)
        assert detected is False


class TestPeaceSign:
    def test_peace_sign_detected(self):
        lms = _make_peace_sign()
        detected, confidence = is_peace_sign(lms)
        assert detected is True
        assert confidence > 0.5

    def test_fist_not_peace(self):
        lms = _make_fist()
        detected, _ = is_peace_sign(lms)
        assert detected is False

    def test_middle_finger_not_peace(self):
        lms = _make_middle_finger()
        detected, _ = is_peace_sign(lms)
        assert detected is False


class TestOpenPalm:
    def test_open_palm_detected(self):
        lms = _make_hand_landmarks()
        detected, confidence = is_open_palm(lms)
        assert detected is True
        assert confidence > 0.5

    def test_fist_not_open_palm(self):
        lms = _make_fist()
        detected, _ = is_open_palm(lms)
        assert detected is False


class TestDetectGesture:
    def test_middle_finger_priority(self):
        lms = _make_middle_finger()
        result = detect_gesture(lms, hand_label="Right")
        assert result.gesture == "middle_finger"
        assert result.hand_label == "Right"

    def test_no_gesture_for_fist(self):
        # Fist should be detected
        lms = _make_fist()
        result = detect_gesture(lms)
        assert result.gesture == "fist"

    def test_open_palm_detected(self):
        lms = _make_hand_landmarks()
        result = detect_gesture(lms)
        assert result.gesture == "open_palm"

    def test_returns_gesture_result(self):
        lms = _make_thumbs_up()
        result = detect_gesture(lms)
        assert isinstance(result, GestureResult)
        assert result.gesture == "thumbs_up"
