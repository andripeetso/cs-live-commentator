"""Vision LLM analyzer — periodically sends webcam frames to GPT-5-mini vision for scene understanding."""

from __future__ import annotations

import base64
import os
import threading
import time

import cv2
import numpy as np
from openai import OpenAI

from . import config

VISION_PROMPT = """\
You are analyzing a webcam frame of a person. Briefly describe what the person \
is doing in 1-2 short sentences. Focus on:
- Physical actions (typing, drinking, eating, punching, gesturing)
- Body language and posture
- Any objects they're interacting with
- Notable gestures (thumbs up, pointing, waving, rude gestures)

Be concise and factual. Example: "Person is leaning back in chair with arms behind head, relaxed posture."
"""


class VisionAnalyzer:
    """Periodically captures a webcam frame and sends it to GPT-5-mini vision.

    Runs in a background daemon thread. Stores the latest analysis result
    which the Commentator can pull for richer context.
    """

    def __init__(
        self,
        commentator: object | None = None,
        interval: float = config.VISION_INTERVAL,
        model: str = config.VISION_MODEL,
    ) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or not config.VISION_ENABLED:
            print("[VISION] Disabled (no API key or VISION_ENABLED=False)")
            self._enabled = False
            return

        self._enabled = True
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._interval = interval
        self._commentator = commentator

        # Latest frame (set by detector thread via set_frame)
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()

        # Latest analysis result
        self._latest_description: str = ""
        self._desc_lock = threading.Lock()

        self._running = False
        self._thread: threading.Thread | None = None

    def set_frame(self, frame: np.ndarray) -> None:
        """Called by the detector to provide the latest webcam frame."""
        with self._frame_lock:
            self._latest_frame = frame

    @property
    def description(self) -> str:
        """Get the latest scene description (thread-safe)."""
        with self._desc_lock:
            return self._latest_description

    def start(self) -> None:
        """Start the vision analysis thread."""
        if not self._enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self._thread.start()
        print(f"[VISION] Started (model={self._model}, interval={self._interval}s)")

    def _analysis_loop(self) -> None:
        # Wait for first frame
        while self._running:
            with self._frame_lock:
                has_frame = self._latest_frame is not None
            if has_frame:
                break
            time.sleep(0.5)

        while self._running:
            self._analyze_current_frame()
            time.sleep(self._interval)

    def _analyze_current_frame(self) -> None:
        """Encode the latest frame and send to vision API."""
        with self._frame_lock:
            frame = self._latest_frame
        if frame is None:
            return

        # Encode as low-res JPEG (~30KB)
        small = cv2.resize(frame, (320, 240))
        _, buffer = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        b64_image = base64.b64encode(buffer).decode("utf-8")

        try:
            start = time.time()
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                    "detail": "low",
                                },
                            },
                        ],
                    }
                ],
                max_completion_tokens=1000,
                timeout=15.0,
            )
            elapsed = time.time() - start

            content = response.choices[0].message.content
            if content:
                desc = content.strip()
                with self._desc_lock:
                    self._latest_description = desc
                # Push to commentator if available
                if self._commentator and hasattr(self._commentator, "set_vision_description"):
                    self._commentator.set_vision_description(desc)
                print(f"[VISION] {desc[:100]} ({elapsed:.1f}s)")
            else:
                print(f"[VISION] Empty response ({elapsed:.1f}s)")

        except Exception as e:
            print(f"[VISION] API error: {type(e).__name__}: {e}")

    def stop(self) -> None:
        """Stop the vision analysis thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
