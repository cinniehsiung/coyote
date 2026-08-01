#!/usr/bin/env python3
"""Local RTSP animal detector for the AI coyote-deterrent project.

Install once:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install ultralytics opencv-python

Run (substream recommended for testing):
    export CAMERA_PASSWORD='your-camera-password'
    python coyote_detector.py --camera-ip 192.168.1.108 --username admin

YOLO's standard COCO model has cat and dog classes, but no coyote class.
This program therefore reports a persistent, sufficiently large dog detection
as POSSIBLE COYOTE. It activates the configured light relay when a dog-like animal is detected.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import cv2
from ultralytics import YOLO

from camera import Camera
from relay import BOARD_ID, RelayBoard

CAT_CLASS = 15  # COCO class IDs used by standard Ultralytics models
DOG_CLASS = 16
PERSON_CLASS = 0
SAN_FRANCISCO_TZ = ZoneInfo("America/Los_Angeles")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect animals in an EmpireTech RTSP stream")
    parser.add_argument("--camera-ip", default="192.168.1.108")
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password",
        default=os.environ.get("CAMERA_PASSWORD"),
        help="Camera password; CAMERA_PASSWORD is safer than typing it here",
    )
    parser.add_argument("--subtype", type=int, choices=(0, 1), default=1,
                        help="0=main stream, 1=lower-resolution substream")
    parser.add_argument("--model", default="yolo11x.pt",
                        help="Ultralytics model file; downloaded once if absent")
    parser.add_argument("--confidence", type=float, default=0.45)
    parser.add_argument("--min-area", type=float, default=0.025,
                        help="Minimum dog box area as fraction of the image")
    parser.add_argument("--window-seconds", type=float, default=3.0)
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--snapshots", default="events")
    parser.add_argument("--no-window", action="store_true",
                        help="Run without displaying a video window")
    return parser.parse_args()


def rtsp_url(ip: str, username: str, password: str, subtype: int) -> str:
    user = quote(username, safe="")
    secret = quote(password, safe="")
    return (
        f"rtsp://{user}:{secret}@{ip}:554/cam/realmonitor"
        f"?channel=1&subtype={subtype}"
    )



def main() -> int:
    args = arguments()
    if not args.password:
        print("Set the camera password first: export CAMERA_PASSWORD='your-password'", file=sys.stderr)
        return 2

    snapshot_dir = Path(args.snapshots)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.model} ...")
    model = YOLO(args.model)
    url = rtsp_url(args.camera_ip, args.username, args.password, args.subtype)
    # Force RTSP over TCP before camera.py opens the stream.
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    try:
        camera = Camera(url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(f"Check camera IP, password and RTSP settings for {args.camera_ip}.", file=sys.stderr)
        return 1

    last_event = 0.0

    # Setup deterants
    relay = RelayBoard(BOARD_ID, debug=False)
    print("Detector running. Press q in the video window to stop.")

    try:
        while True:
            # camera.py continuously reads the RTSP stream in a background
            # thread and keeps only the newest frame. Old frames never queue up.
            frame = camera.latest()
            if frame is None:
                time.sleep(0.01)
                continue

            height, width = frame.shape[:2]
            image_area = float(height * width)
            result = model.predict(
                frame,
                conf=args.confidence,
                classes=[CAT_CLASS, DOG_CLASS, PERSON_CLASS],
                verbose=False,
            )[0]

            now = time.monotonic()
            saw_large_dog = False
            saw_small_dog = False
            saw_cat = False
            saw_person = False

            for box in result.boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                area_fraction = max(0, x2 - x1) * max(0, y2 - y1) / image_area

                if class_id == DOG_CLASS:
                    if area_fraction >= args.min_area:
                        saw_large_dog = True
                        label, color = f"DOG-LIKE candidate {confidence:.2f}", (0, 0, 255)
                    else:
                        saw_small_dog = True
                        label, color = f"small DOG-LIKE {confidence:.2f}", (0, 200, 255)

                elif class_id == CAT_CLASS:
                    saw_cat = True
                    label, color = f"CAT-LIKE candidate {confidence:.2f}", (0, 200, 255)

                elif class_id == PERSON_CLASS:
                    saw_person = True
                    label, color = f"PERSON-LIKE candidate {confidence:.2f}", (0, 200, 255)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, max(25, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if saw_large_dog:
                cv2.putText(frame, "COYOTE_DETECTED", (25, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                event_time = datetime.now(SAN_FRANCISCO_TZ)
                timestamp = event_time.strftime("%Y-%m-%d_%H-%M-%S")
                filename = snapshot_dir / f"coyote_{timestamp}.jpg"
                cv2.imwrite(str(filename), frame)
                print(f"[{event_time:%F %T %Z}] COYOTE DETECTED;")
                last_event = now
                relay.lights_on()

            if saw_small_dog or saw_cat or saw_person:
                event_time = datetime.now(SAN_FRANCISCO_TZ)
                timestamp = event_time.strftime("%Y-%m-%d_%H-%M-%S")
                filename = snapshot_dir / f"not_coyote_{timestamp}.jpg"
                cv2.imwrite(str(filename), frame)

            if now - last_event >= args.cooldown:
               relay.lights_off()

            if not args.no_window:
                cv2.imshow("Coyote detector - q to quit", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        relay.lights_off()
        camera.close()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())