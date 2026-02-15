"""Tests for screen context — tests the context property and app detection."""

from unittest.mock import MagicMock, patch

from emotion_detector.screen_context import ScreenContext


class TestScreenContext:
    def test_context_initially_empty(self):
        with patch.dict("sys.modules", {"AppKit": MagicMock()}):
            sc = ScreenContext()
            assert sc.context == ""

    def test_pushes_to_commentator(self):
        mock_commentator = MagicMock()
        with patch.dict("sys.modules", {"AppKit": MagicMock()}):
            sc = ScreenContext(commentator=mock_commentator)
            sc._app_name = "Counter-Strike 2"
            assert sc.context == "Counter-Strike 2"
