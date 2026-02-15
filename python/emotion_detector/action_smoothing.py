"""Temporal smoothing for action detection — rolling vote + debounced events."""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass, field

from . import config
from .action_rules import ActionResult
from .events import ActionEvent, EventEmitter


@dataclass
class ActionState:
    """Current smoothed action state."""

    action: str | None = None  # dominant action label or None
    confidence: float = 0.0
    raw_actions: dict[str, float] = field(default_factory=dict)


class ActionSmoother:
    """Rolling majority vote over N frames with debounced event emission.

    Emits an ActionEvent only when:
    1. The dominant action changed from last emission
    2. At least DEBOUNCE_SECONDS have passed
    """

    def __init__(
        self,
        event_emitter: EventEmitter,
        window_size: int = config.ACTION_SMOOTHING_WINDOW,
        debounce_seconds: float = config.ACTION_DEBOUNCE_SECONDS,
    ) -> None:
        self._emitter = event_emitter
        self._window_size = window_size
        self._debounce_seconds = debounce_seconds
        self._history: deque[str | None] = deque(maxlen=window_size)
        self._last_emitted_action: str | None = None
        self._last_emit_time: float = 0.0
        self.state = ActionState()

    def update(self, result: ActionResult) -> ActionState:
        """Feed a new ActionResult and get smoothed state back."""
        dominant = result.dominant_action
        self._history.append(dominant)

        # Majority vote across window
        counts = Counter(a for a in self._history if a is not None)

        if not counts:
            self.state = ActionState()
        else:
            best_action, best_count = counts.most_common(1)[0]
            confidence = best_count / len(self._history)

            # Only report if it appears in enough frames
            if confidence >= config.ACTION_MIN_VOTE_RATIO:
                self.state = ActionState(
                    action=best_action,
                    confidence=confidence,
                    raw_actions=result.actions,
                )
            else:
                self.state = ActionState(raw_actions=result.actions)

        # Debounced emission
        now = time.time()
        should_emit = (
            self.state.action != self._last_emitted_action
            and (now - self._last_emit_time) >= self._debounce_seconds
        )

        if should_emit and self.state.action is not None:
            self._last_emitted_action = self.state.action
            self._last_emit_time = now
            event = ActionEvent(
                timestamp=now,
                action=self.state.action,
                confidence=round(self.state.confidence, 3),
            )
            self._emitter.emit_action(event)
        elif self.state.action is None and self._last_emitted_action is not None:
            # Action stopped
            if (now - self._last_emit_time) >= self._debounce_seconds:
                self._last_emitted_action = None
                self._last_emit_time = now

        return self.state
