"""Tests for vision analyzer — mocks OpenAI API calls."""

from unittest.mock import MagicMock, patch

import numpy as np

from emotion_detector.vision_analyzer import VisionAnalyzer


class TestVisionAnalyzer:
    def test_disabled_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            va = VisionAnalyzer()
            assert va._enabled is False

    def test_enabled_with_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer()
            assert va._enabled is True

    def test_set_frame_stores_frame(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            va.set_frame(frame)
            assert va._latest_frame is not None

    def test_description_initially_empty(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer()
            assert va.description == ""

    def test_analyze_updates_description(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            va.set_frame(frame)

            # Mock the OpenAI client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Person is sitting at desk typing."
            va._client.chat.completions.create = MagicMock(return_value=mock_response)

            va._analyze_current_frame()
            assert va.description == "Person is sitting at desk typing."

    def test_analyze_pushes_to_commentator(self):
        mock_commentator = MagicMock()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer(commentator=mock_commentator)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            va.set_frame(frame)

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Person waving at camera."
            va._client.chat.completions.create = MagicMock(return_value=mock_response)

            va._analyze_current_frame()
            mock_commentator.set_vision_description.assert_called_once_with("Person waving at camera.")

    def test_analyze_handles_api_error(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            va.set_frame(frame)

            va._client.chat.completions.create = MagicMock(side_effect=Exception("API error"))
            # Should not raise
            va._analyze_current_frame()
            assert va.description == ""

    def test_analyze_handles_no_frame(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            va = VisionAnalyzer()
            # No frame set — should not crash
            va._analyze_current_frame()
            assert va.description == ""
