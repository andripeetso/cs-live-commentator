"""AI commentator — generates esports-style commentary from emotion/action events."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass

from openai import OpenAI

from . import config
from .events import ActionEvent, EmotionEvent, EventEmitter, GestureEvent

SYSTEM_PROMPT = """\
You are an energetic, hype esports caster doing live onstage commentary. \
You're observing a person through their webcam and commentating on their \
emotions and actions in real time — like a play-by-play sports announcer.

Rules:
- Keep each line SHORT (1-2 sentences max, ~20 words)
- Be dramatic, entertaining, and funny
- Use esports casting style: hype moments, dramatic pauses, catchphrases
- Reference the specific emotion/action you see
- Vary your style — don't repeat the same phrases
- Sometimes add color commentary, speculation about what they're thinking
- Use ALL CAPS sparingly for emphasis on key moments
- No emojis

Examples of good commentary:
"And we see the focus setting in — stone cold neutral, this competitor is LOCKED IN."
"OH! A smile breaks through! The pressure is lifting, folks!"
"Arms crossed — classic power stance. They're thinking. They're SCHEMING."
"The hand goes up! Is that a wave to the crowd? The confidence is REAL!"
"""


@dataclass
class _EventSnapshot:
    """Batched snapshot of recent events for the LLM."""

    emotion: str | None = None
    emotion_confidence: float = 0.0
    prev_emotion: str | None = None
    action: str | None = None
    action_confidence: float = 0.0
    gesture: str | None = None
    gesture_confidence: float = 0.0
    gesture_hand: str = ""
    vision_description: str = ""
    screen_context: str = ""


class Commentator:
    """Subscribes to emotion/action events and generates commentary via OpenAI.

    Runs commentary generation in a background thread to avoid blocking
    the detection pipeline. Batches events over a configurable window
    to avoid spamming the API.
    """

    def __init__(
        self,
        event_emitter: EventEmitter,
        model: str = config.COMMENTATOR_MODEL,
        interval: float = config.COMMENTATOR_INTERVAL,
    ) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[COMMENTATOR] WARNING: OPENAI_API_KEY not set. Commentary disabled.")
            self._enabled = False
            return

        self._enabled = True
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._interval = interval

        # State tracking
        self._current_emotion: str | None = None
        self._current_emotion_confidence: float = 0.0
        self._prev_emotion: str | None = None
        self._current_action: str | None = None
        self._current_action_confidence: float = 0.0
        self._current_gesture: str | None = None
        self._current_gesture_confidence: float = 0.0
        self._current_gesture_hand: str = ""
        self._has_new_event = False

        # External context (set by VisionAnalyzer and ScreenContext)
        self._vision_description: str = ""
        self._screen_context: str = ""

        # Commentary history (for context / avoiding repetition)
        self._history: deque[str] = deque(maxlen=config.COMMENTATOR_HISTORY_SIZE)

        # Register callbacks
        event_emitter.on_emotion(self._on_emotion)
        event_emitter.on_action(self._on_action)
        event_emitter.on_gesture(self._on_gesture)

        # Background thread for generation
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the commentary generation thread."""
        if not self._enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._commentary_loop, daemon=True)
        self._thread.start()
        print(f"[COMMENTATOR] Started (model={self._model}, interval={self._interval}s)")

    def _on_emotion(self, event: EmotionEvent) -> None:
        self._prev_emotion = self._current_emotion
        self._current_emotion = event.dominant_emotion
        self._current_emotion_confidence = event.confidence
        self._has_new_event = True

    def _on_action(self, event: ActionEvent) -> None:
        self._current_action = event.action
        self._current_action_confidence = event.confidence
        self._has_new_event = True

    def _on_gesture(self, event: GestureEvent) -> None:
        self._current_gesture = event.gesture
        self._current_gesture_confidence = event.confidence
        self._current_gesture_hand = event.hand_label
        self._has_new_event = True

    def set_vision_description(self, description: str) -> None:
        """Called by VisionAnalyzer to provide scene context."""
        self._vision_description = description

    def set_screen_context(self, context: str) -> None:
        """Called by ScreenContext to provide desktop context."""
        self._screen_context = context

    def _commentary_loop(self) -> None:
        # Wait for first detection
        while self._running and not self._has_new_event:
            time.sleep(0.5)

        while self._running:
            if self._has_new_event:
                self._has_new_event = False
                snapshot = _EventSnapshot(
                    emotion=self._current_emotion,
                    emotion_confidence=self._current_emotion_confidence,
                    prev_emotion=self._prev_emotion,
                    action=self._current_action,
                    action_confidence=self._current_action_confidence,
                    gesture=self._current_gesture,
                    gesture_confidence=self._current_gesture_confidence,
                    gesture_hand=self._current_gesture_hand,
                    vision_description=self._vision_description,
                    screen_context=self._screen_context,
                )
                self._generate(snapshot)

            time.sleep(self._interval)

    def _generate(self, snap: _EventSnapshot) -> None:
        """Call OpenAI and print the commentary line."""
        # Build the user message describing what's happening
        parts = []
        if snap.emotion:
            if snap.prev_emotion and snap.prev_emotion != snap.emotion:
                parts.append(
                    f"Emotion just changed from {snap.prev_emotion} to {snap.emotion} "
                    f"(confidence: {snap.emotion_confidence:.0%})"
                )
            else:
                parts.append(f"Current emotion: {snap.emotion} ({snap.emotion_confidence:.0%})")

        if snap.action:
            parts.append(f"Action detected: {snap.action} ({snap.action_confidence:.0%})")

        if snap.gesture:
            hand = f" ({snap.gesture_hand} hand)" if snap.gesture_hand else ""
            parts.append(f"Hand gesture: {snap.gesture}{hand} ({snap.gesture_confidence:.0%})")

        if snap.vision_description:
            parts.append(f"Scene analysis: {snap.vision_description}")

        if snap.screen_context:
            parts.append(f"On screen: {snap.screen_context}")

        if not parts:
            return

        situation = ". ".join(parts) + "."

        # Include recent history to avoid repetition
        history_context = ""
        if self._history:
            recent = list(self._history)[-3:]
            history_context = (
                "\n\nYour last few lines (DO NOT repeat these):\n"
                + "\n".join(f'- "{line}"' for line in recent)
            )

        user_msg = f"What's happening now: {situation}{history_context}\n\nYour commentary line:"

        try:
            print(f"[COMMENTATOR] Generating for: {situation[:80]}")
            start = time.time()
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_completion_tokens=1000,
                timeout=10.0,
            )
            elapsed = time.time() - start

            msg = response.choices[0].message
            content = msg.content
            if content:
                line = content.strip().strip('"')
                self._history.append(line)
                print(f"\n🎙️  {line}  ({elapsed:.1f}s)\n")
            else:
                print(f"[COMMENTATOR] Empty response ({elapsed:.1f}s) finish_reason={response.choices[0].finish_reason}")

        except Exception as e:
            print(f"[COMMENTATOR] API error: {type(e).__name__}: {e}")

    def stop(self) -> None:
        """Stop the commentary thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
