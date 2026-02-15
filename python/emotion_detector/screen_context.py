"""Screen context — detects active window/app for desktop awareness."""

from __future__ import annotations

import threading
import time


class ScreenContext:
    """Polls the active window title and app name on macOS.

    Runs in a background daemon thread, updates every few seconds.
    Provides context like "Counter-Strike 2" or "VS Code — main.py"
    to the commentator for richer commentary.

    Uses pyobjc (macOS-only). Falls back gracefully if not installed.
    """

    def __init__(
        self,
        commentator: object | None = None,
        interval: float = 3.0,
    ) -> None:
        self._commentator = commentator
        self._interval = interval
        self._enabled = False
        self._running = False
        self._thread: threading.Thread | None = None

        # Latest context
        self._app_name: str = ""
        self._window_title: str = ""
        self._lock = threading.Lock()

        # Check if pyobjc is available
        try:
            from AppKit import NSWorkspace  # noqa: F401
            self._enabled = True
        except ImportError:
            print("[SCREEN] pyobjc not installed — screen context disabled")
            print("[SCREEN] Install with: pip install pyobjc-framework-Cocoa")

    @property
    def context(self) -> str:
        """Get the current screen context as a human-readable string."""
        with self._lock:
            if not self._app_name:
                return ""
            return self._app_name

    def start(self) -> None:
        """Start the screen context polling thread."""
        if not self._enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print(f"[SCREEN] Started (interval={self._interval}s)")

    def _poll_loop(self) -> None:
        last_app = ""
        while self._running:
            try:
                app_name = self._get_active_app()
                with self._lock:
                    self._app_name = app_name

                if app_name and app_name != last_app:
                    print(f"[SCREEN] Active app: {app_name}")
                    last_app = app_name

                    # Push to commentator
                    if self._commentator and hasattr(self._commentator, "set_screen_context"):
                        self._commentator.set_screen_context(app_name)

            except Exception as e:
                print(f"[SCREEN] Error: {type(e).__name__}: {e}")

            time.sleep(self._interval)

    @staticmethod
    def _get_active_app() -> str:
        """Get the name of the currently active application (macOS)."""
        try:
            from AppKit import NSWorkspace
            active = NSWorkspace.sharedWorkspace().frontmostApplication()
            if active:
                return active.localizedName() or ""
        except Exception:
            pass
        return ""

    def stop(self) -> None:
        """Stop the screen context thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
