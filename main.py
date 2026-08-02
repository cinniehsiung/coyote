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

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import cv2
from ultralytics import YOLO

from camera import Camera
from relay import BOARD_ID, RelayBoard
from speaker import Speaker

# Model identification classes
CAT_CLASS = 15  # COCO class IDs used by standard Ultralytics models
DOG_CLASS = 16
PERSON_CLASS = 0

# Time zone info
SAN_FRANCISCO_TZ = ZoneInfo("America/Los_Angeles")

# Camera IP addresses
CAMERA_IP_1 = "192.168.1.109"
CAMERA_IP_2 = "192.168.1.108"

# Sound deterrants
bark_file = Path(__file__).resolve().parent / "sounds" / "dog_bark.wav"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect animals in an EmpireTech RTSP stream")
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
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--snapshots", default="events")
    parser.add_argument("--window", action="store_true",
                        help="Run without displaying a video window")
    parser.add_argument("--debug", action="store_true",
                        help="Run with the coyote detector firing for humans")
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
    url = rtsp_url(CAMERA_IP_1, args.username, args.password, args.subtype)
    # Force RTSP over TCP before camera.py opens the stream.
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    try:
        camera = Camera(url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(f"Check camera IP, password and RTSP settings for {CAMERA_IP_1}.", file=sys.stderr)
        return 1

    last_event = 0.0

    # Setup deterants
    relay = RelayBoard(BOARD_ID, debug=False)
    speaker = Speaker(sound_file=bark_file)
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
                        label, color = f"LARGE DOG {confidence:.2f}", (0, 0, 255)
                    else:
                        saw_small_dog = True
                        label, color = f"SMALL DOG {confidence:.2f}", (0, 200, 255)

                elif class_id == CAT_CLASS:
                    saw_cat = True
                    label, color = f"CAT {confidence:.2f}", (0, 200, 255)

                elif class_id == PERSON_CLASS:
                    saw_person = True
                    label, color = f"PERSON {confidence:.2f}", (0, 200, 255)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, max(25, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            enough_time_delay = now - last_event >= args.cooldown
            event_time = datetime.now(SAN_FRANCISCO_TZ)

            if saw_large_dog or (args.debug and saw_person):
                last_event = now
                if not relay.is_all_on:
                    cv2.putText(frame, f"COYOTE DETECTED {" DEBUG MODE" if args.debug else ""}", (25, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                    timestamp = event_time.strftime("%Y-%m-%d_%H-%M-%S")
                    filename = snapshot_dir / f"{timestamp}_coyote.jpg"
                    cv2.imwrite(str(filename), frame)
                    print(f"[{event_time:%F %T %Z}] {"COYOTE" if saw_large_dog else "PERSON"} DETECTED;")
                    relay.all_on()
                    speaker.play(repeat=100)

            elif enough_time_delay and (saw_small_dog or saw_cat):
                last_event = now
                timestamp = event_time.strftime("%Y-%m-%d_%H-%M-%S")
                filename = snapshot_dir / f"{timestamp}_not_coyote.jpg"
                cv2.imwrite(str(filename), frame)

            elif enough_time_delay and relay.is_all_on:
                print(f"[{event_time:%F %T %Z}] ALL CLEAR;")
                relay.all_off()
                speaker.stop()


            if args.window:
                cv2.imshow("Coyote detector - q to quit", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        relay.all_off()
        camera.close()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())