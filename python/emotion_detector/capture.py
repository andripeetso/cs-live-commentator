"""Threaded webcam capture — runs in a daemon thread, puts frames into a queue."""

import queue
import threading

import cv2

from . import config


class WebcamCapture:
    """Producer: captures frames from webcam and puts them in a queue.

    Uses a "drop oldest" pattern — when the queue is full, the oldest frame
    is discarded so the consumer always gets the most recent frame.

    IMPORTANT: On macOS, cv2.VideoCapture must be opened on the main thread
    for camera authorization to work. Call open_camera() from main thread
    before calling start().
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
        self._cap: cv2.VideoCapture | None = None

    def open_camera(self) -> bool:
        """Open the camera on the current thread (must be main thread on macOS).

        Returns True if camera opened successfully.
        """
        print(f"[CAPTURE] Opening camera {self.camera_index}...")
        self._cap = cv2.VideoCapture(self.camera_index)

        if not self._cap.isOpened():
            print("[CAPTURE] ERROR: Camera failed to open!")
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[CAPTURE] Camera opened: {actual_w}x{actual_h}")
        return True

    def start(self) -> None:
        """Start the capture thread (daemon). Call open_camera() first."""
        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError("Call open_camera() on main thread before start()")
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print("[CAPTURE] Capture thread started")

    def _capture_loop(self) -> None:
        frame_count = 0
        try:
            while self._running:
                ret, frame = self._cap.read()
                if not ret:
                    print("[CAPTURE] Camera read failed, stopping")
                    break

                # Drop oldest frame if queue is full
                if self.queue.full():
                    try:
                        self.queue.get_nowait()
                    except queue.Empty:
                        pass
                self.queue.put(frame)
                frame_count += 1

                if frame_count == 1:
                    print("[CAPTURE] First frame captured")
                elif frame_count % 300 == 0:
                    print(f"[CAPTURE] {frame_count} frames captured")
        finally:
            self._cap.release()
            print(f"[CAPTURE] Camera released after {frame_count} frames")

    def stop(self) -> None:
        """Signal the capture thread to stop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
