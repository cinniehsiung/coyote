import threading
import time

import cv2


class Camera:
    def __init__(
        self,
        source: str,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
    ):
        self.source = source

        # Create the capture object first so we can pass timeout
        # parameters when opening the RTSP stream.
        self.capture = cv2.VideoCapture()

        params = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            open_timeout_ms,

            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            read_timeout_ms,
        ]

        opened = self.capture.open(
            source,
            cv2.CAP_FFMPEG,
            params,
        )

        if not opened or not self.capture.isOpened():
            self.capture.release()

            raise RuntimeError(
                f"Could not open camera within "
                f"{open_timeout_ms / 1000:.1f} seconds: "
                f"{source}"
            )

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
                # read() can return False after the configured
                # read timeout. Wait briefly and try again.
                time.sleep(0.05)
                continue

            # Replace the previous frame.
            # Never build a backlog.
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

        self._thread.join(
            timeout=2
        )

        self.capture.release()