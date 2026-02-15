"""Threaded webcam capture — runs in a daemon thread, puts frames into a queue."""

import queue
import threading

import cv2

from . import config


class WebcamCapture:
    """Producer: captures frames from webcam and puts them in a queue.

    Uses a "drop oldest" pattern — when the queue is full, the oldest frame
    is discarded so the consumer always gets the most recent frame.
    """

    def __init__(
        self,
        camera_index: int = config.CAMERA_INDEX,
        frame_queue: queue.Queue | None = None,
        width: int = config.FRAME_WIDTH,
        height: int = config.FRAME_HEIGHT,
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.queue = frame_queue or queue.Queue(maxsize=config.CAPTURE_QUEUE_SIZE)
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the capture thread (daemon)."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    break

                # Drop oldest frame if queue is full
                if self.queue.full():
                    try:
                        self.queue.get_nowait()
                    except queue.Empty:
                        pass
                self.queue.put(frame)
        finally:
            cap.release()

    def stop(self) -> None:
        """Signal the capture thread to stop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
