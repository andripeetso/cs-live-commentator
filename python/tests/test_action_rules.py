"""Tests for action detection heuristic rules."""

from collections import deque

from emotion_detector.action_rules import (
    ActionResult,
    Landmark,
    detect_all,
    is_arms_crossed,
    is_clapping,
    is_drinking,
    is_hand_raised,
    is_waving,
)


def _lm(x: float, y: float, vis: float = 0.9) -> Landmark:
    """Shorthand to create a landmark."""
    return Landmark(x=x, y=y, z=0.0, visibility=vis)


def _make_landmarks(overrides: dict[int, Landmark] | None = None) -> list[Landmark]:
    """Create 33 default landmarks with optional overrides by index.

    Default pose: person standing upright, arms at sides.
    """
    defaults = {
        0: _lm(0.5, 0.15),     # nose
        9: _lm(0.48, 0.18),    # mouth_left
        10: _lm(0.52, 0.18),   # mouth_right
        11: _lm(0.4, 0.3),     # left_shoulder
        12: _lm(0.6, 0.3),     # right_shoulder
        13: _lm(0.35, 0.45),   # left_elbow
        14: _lm(0.65, 0.45),   # right_elbow
        15: _lm(0.33, 0.6),    # left_wrist (at hip level — relaxed)
        16: _lm(0.67, 0.6),    # right_wrist
        23: _lm(0.42, 0.65),   # left_hip
        24: _lm(0.58, 0.65),   # right_hip
    }
    if overrides:
        defaults.update(overrides)
    landmarks = [_lm(0.5, 0.5, 0.1)] * 33  # low visibility defaults
    for idx, lm in defaults.items():
        landmarks[idx] = lm
    return landmarks


class TestHandRaised:
    def test_no_hand_raised_at_rest(self):
        lms = _make_landmarks()
        assert is_hand_raised(lms) == 0.0

    def test_left_hand_raised(self):
        lms = _make_landmarks({
            15: _lm(0.33, 0.05),  # left wrist way above shoulder (y=0.3)
        })
        confidence = is_hand_raised(lms)
        assert confidence > 0.5

    def test_right_hand_raised(self):
        lms = _make_landmarks({
            16: _lm(0.67, 0.1),  # right wrist above shoulder
        })
        confidence = is_hand_raised(lms)
        assert confidence > 0.5

    def test_low_visibility_ignored(self):
        lms = _make_landmarks({
            15: _lm(0.33, 0.05, vis=0.1),  # raised but low visibility
        })
        # Should still detect from right wrist (default position, not raised)
        confidence = is_hand_raised(lms)
        assert confidence == 0.0


class TestWaving:
    def _make_waving_buffer(self) -> deque[list[Landmark]]:
        """Create a buffer simulating waving motion."""
        buffer = deque(maxlen=15)
        for i in range(10):
            # Oscillate wrist X position while keeping it raised
            x_offset = 0.05 * (1 if i % 2 == 0 else -1)
            lms = _make_landmarks({
                15: _lm(0.33 + x_offset, 0.1),  # raised + oscillating
            })
            buffer.append(lms)
        return buffer

    def test_waving_detected(self):
        buffer = self._make_waving_buffer()
        lms = _make_landmarks({15: _lm(0.38, 0.1)})  # hand raised
        confidence = is_waving(lms, buffer)
        assert confidence > 0.3

    def test_static_hand_not_waving(self):
        buffer = deque(maxlen=15)
        for _ in range(10):
            lms = _make_landmarks({15: _lm(0.33, 0.1)})  # raised but static
            buffer.append(lms)
        lms = _make_landmarks({15: _lm(0.33, 0.1)})
        assert is_waving(lms, buffer) == 0.0

    def test_short_buffer_returns_zero(self):
        buffer = deque(maxlen=15)
        for _ in range(3):
            buffer.append(_make_landmarks())
        assert is_waving(_make_landmarks(), buffer) == 0.0


class TestClapping:
    def _make_clapping_buffer(self) -> deque[list[Landmark]]:
        """Create a buffer simulating clapping motion."""
        buffer = deque(maxlen=15)
        for i in range(8):
            if i % 2 == 0:
                # Wrists together (clap)
                lms = _make_landmarks({
                    15: _lm(0.49, 0.4),
                    16: _lm(0.51, 0.4),
                })
            else:
                # Wrists apart
                lms = _make_landmarks({
                    15: _lm(0.35, 0.4),
                    16: _lm(0.65, 0.4),
                })
            buffer.append(lms)
        return buffer

    def test_clapping_detected(self):
        buffer = self._make_clapping_buffer()
        lms = _make_landmarks({
            15: _lm(0.49, 0.4),
            16: _lm(0.51, 0.4),
        })
        confidence = is_clapping(lms, buffer)
        assert confidence > 0.3

    def test_hands_apart_not_clapping(self):
        buffer = deque(maxlen=15)
        for _ in range(8):
            lms = _make_landmarks()  # default: hands at sides
            buffer.append(lms)
        assert is_clapping(_make_landmarks(), buffer) == 0.0


class TestDrinking:
    def test_drinking_detected(self):
        lms = _make_landmarks({
            15: _lm(0.48, 0.17),  # left wrist near mouth (y ~0.18)
            13: _lm(0.40, 0.35),  # elbow bent
        })
        confidence = is_drinking(lms)
        assert confidence > 0.3

    def test_hand_at_rest_not_drinking(self):
        lms = _make_landmarks()  # default rest position
        assert is_drinking(lms) == 0.0


class TestArmsCrossed:
    def test_arms_crossed_detected(self):
        lms = _make_landmarks({
            15: _lm(0.55, 0.35),  # left wrist on right side, at chest
            16: _lm(0.45, 0.35),  # right wrist on left side, at chest
        })
        confidence = is_arms_crossed(lms)
        assert confidence > 0.5

    def test_arms_at_sides_not_crossed(self):
        lms = _make_landmarks()
        assert is_arms_crossed(lms) == 0.0


class TestDetectAll:
    def test_no_action_at_rest(self):
        lms = _make_landmarks()
        buffer = deque(maxlen=15)
        for _ in range(10):
            buffer.append(_make_landmarks())
        result = detect_all(lms, buffer)
        assert result.dominant_action is None

    def test_returns_action_result(self):
        lms = _make_landmarks({15: _lm(0.33, 0.05)})
        buffer = deque(maxlen=15)
        result = detect_all(lms, buffer)
        assert isinstance(result, ActionResult)
        assert result.dominant_action == "hand_raised"
