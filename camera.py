import threading
import time

import cv2


class Camera:
    def __init__(self, source: str):
        self.capture = cv2.VideoCapture(source)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open camera: {source}")

        self._frame: object | None = None
        self._lock = threading.Lock()
        self._running = True

        self._thread = threading.Thread(
            target=self._reader,
            daemon=True,
        )
        self._thread.start()

    def _reader(self) -> None:
        while self._running:
            ok, frame = self.capture.read()

            if not ok:
                time.sleep(0.05)
                continue

            # Replace the previous frame. Never build a backlog.
            with self._lock:
                self._frame = frame

    def latest(self):
        with self._lock:
            frame = self._frame

        if frame is None:
            return None

        return frame.copy()

    def close(self) -> None:
        self._running = False
        self._thread.join(timeout=2)
        self.capture.release()