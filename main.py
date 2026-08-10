#!/usr/bin/env python3
"""Local RTSP animal detector for the AI coyote-deterrent project.

Install once:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install ultralytics opencv-python

Run:
    export CAMERA_PASSWORD='your-camera-password'
    python3 main.py

YOLO's standard COCO model has cat and dog classes, but no coyote class.
This program therefore reports a sufficiently large dog detection as
POSSIBLE COYOTE and activates the configured deterrents.
"""

from __future__ import annotations

import argparse
import os
import signal
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

# ----------------------------------------------------------------------
# Model identification classes
# ----------------------------------------------------------------------

CAT_CLASS = 15
DOG_CLASS = 16
PERSON_CLASS = 0
NOTHING = -1


# ----------------------------------------------------------------------
# Time zone
# ----------------------------------------------------------------------

SAN_FRANCISCO_TZ = ZoneInfo("America/Los_Angeles")


# ----------------------------------------------------------------------
# Cameras
# ----------------------------------------------------------------------

CAMERA_IP_1 = "192.168.1.109"
CAMERA_IP_2 = "192.168.1.108"


# ----------------------------------------------------------------------
# Sound deterrent
# ----------------------------------------------------------------------

bark_file = (
    Path(__file__).resolve().parent
    / "sounds"
    / "dog_bark.wav"
)


# ======================================================================
# COMMAND LINE ARGUMENTS
# ======================================================================

def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect animals in EmpireTech RTSP streams"
    )

    parser.add_argument(
        "--username",
        default="admin",
    )

    parser.add_argument(
        "--password",
        default=os.environ.get("CAMERA_PASSWORD"),
        help="Camera password; CAMERA_PASSWORD is safer than typing it here",
    )

    parser.add_argument(
        "--subtype",
        type=int,
        choices=(0, 1),
        default=1,
        help="0=main stream, 1=lower-resolution substream",
    )

    parser.add_argument(
        "--model",
        default="yolo11x.pt",
        help="Ultralytics model file; downloaded once if absent",
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=0.45,
    )

    parser.add_argument(
        "--min-area",
        type=float,
        default=0.025,
        help="Minimum dog box area as fraction of the image",
    )

    parser.add_argument(
        "--cooldown",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--snapshots",
        default="events",
    )

    parser.add_argument(
        "--window",
        action="store_true",
        help="Display video windows",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Fire the coyote deterrent for humans during testing",
    )

    return parser.parse_args()


# ======================================================================
# CAMERA URL
# ======================================================================

def rtsp_url(
    ip: str,
    username: str,
    password: str,
    subtype: int,
) -> str:

    user = quote(username, safe="")
    secret = quote(password, safe="")

    return (
        f"rtsp://{user}:{secret}@{ip}:554/cam/realmonitor"
        f"?channel=1&subtype={subtype}"
    )


# ======================================================================
# COYOTE DETECTION
# ======================================================================

def coyote_detection(model, frame, args):
    """Run YOLO inference on one frame.

    The input frame is not modified.

    Returns a dictionary containing:

        frame
            Annotated frame with bounding boxes.

        clean_frame
            Original frame without bounding boxes. Useful for fine-tuning.

        saw_large_dog
        saw_small_dog
        saw_cat
        saw_person

        detections
            Raw detections in the format:

            {
                "class_id": int,
                "confidence": float,
                "x1": int,
                "y1": int,
                "x2": int,
                "y2": int,
                "area_fraction": float,
            }
    """

    # Preserve an untouched copy for future fine-tuning.
    clean_frame = frame.copy()

    # Work on a separate image because we draw boxes on it.
    annotated_frame = frame.copy()

    height, width = annotated_frame.shape[:2]
    image_area = float(height * width)

    # --------------------------------------------------------------
    # YOLO inference
    # --------------------------------------------------------------

    result = model.predict(
        annotated_frame,
        conf=args.confidence,
        classes=[
            CAT_CLASS,
            DOG_CLASS,
            PERSON_CLASS,
        ],
        verbose=False,
    )[0]

    saw_large_dog = False
    saw_small_dog = False
    saw_cat = False
    saw_person = False

    detections = []

    # --------------------------------------------------------------
    # Process YOLO results
    # --------------------------------------------------------------

    for box in result.boxes:

        class_id = int(box.cls[0])
        confidence = float(box.conf[0])

        x1, y1, x2, y2 = (
            int(v)
            for v in box.xyxy[0].tolist()
        )

        area_fraction = (
            max(0, x2 - x1)
            * max(0, y2 - y1)
            / image_area
        )

        # Save the raw detection.
        # This will also be useful later for finetune.py.
        detections.append(
            {
                "class_id": class_id,
                "confidence": confidence,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "area_fraction": area_fraction,
            }
        )

        # ----------------------------------------------------------
        # Interpret class
        # ----------------------------------------------------------

        if class_id == DOG_CLASS:

            if area_fraction >= args.min_area:

                saw_large_dog = True

                label = (
                    f"LARGE DOG {confidence:.2f}"
                )

                color = (0, 0, 255)

            else:

                saw_small_dog = True

                label = (
                    f"SMALL DOG {confidence:.2f}"
                )

                color = (0, 200, 255)

        elif class_id == CAT_CLASS:

            saw_cat = True

            label = (
                f"CAT {confidence:.2f}"
            )

            color = (0, 200, 255)

        elif class_id == PERSON_CLASS:

            saw_person = True

            label = (
                f"PERSON {confidence:.2f}"
            )

            color = (0, 200, 255)

        else:
            continue

        # ----------------------------------------------------------
        # Draw detection
        # ----------------------------------------------------------

        cv2.rectangle(
            annotated_frame,
            (x1, y1),
            (x2, y2),
            color,
            2,
        )

        cv2.putText(
            annotated_frame,
            label,
            (x1, max(25, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

    # --------------------------------------------------------------
    # Return everything main/run_deterrants may need
    # --------------------------------------------------------------

    return {
        "frame": annotated_frame,
        "clean_frame": clean_frame,

        "saw_large_dog": saw_large_dog,
        "saw_small_dog": saw_small_dog,
        "saw_cat": saw_cat,
        "saw_person": saw_person,

        "detections": detections,
    }


# ======================================================================
# RUN DETERRENTS
# ======================================================================

def run_deterrants(
    camera_results,
    relay,
    speaker,
    args,
    snapshot_dir,
    last_event,
    last_detection,
):
    """Make one deterrent decision based on ALL camera results.

    camera_results is:

        {
            "camera1": result_from_coyote_detection,
            "camera2": result_from_coyote_detection,
        }

    Returns:

        last_event, last_detection
    """

    now = time.monotonic()

    event_time = datetime.now(
        SAN_FRANCISCO_TZ
    )

    enough_time_delay = (
        now - last_event >= args.cooldown
    )

    # --------------------------------------------------------------
    # Combine detections from every camera
    # --------------------------------------------------------------

    saw_large_dog = any(
        result["saw_large_dog"]
        for result in camera_results.values()
    )

    saw_small_dog = any(
        result["saw_small_dog"]
        for result in camera_results.values()
    )

    saw_cat = any(
        result["saw_cat"]
        for result in camera_results.values()
    )

    saw_person = any(
        result["saw_person"]
        for result in camera_results.values()
    )

    # ==============================================================
    # LARGE DOG / POSSIBLE COYOTE
    # ==============================================================

    if saw_large_dog or (
        args.debug and saw_person
    ):

        # Keep extending the event while the animal is still visible.
        last_event = now
        last_detection = DOG_CLASS

        # Only start deterrents once.
        if not relay.is_all_on:

            timestamp = event_time.strftime(
                "%Y-%m-%d_%H-%M-%S"
            )

            # ------------------------------------------------------
            # Save snapshots from cameras which actually triggered
            # ------------------------------------------------------

            for camera_name, result in camera_results.items():

                is_coyote_trigger = (
                    result["saw_large_dog"]
                )

                is_debug_person_trigger = (
                    args.debug
                    and result["saw_person"]
                )

                if not (
                    is_coyote_trigger
                    or is_debug_person_trigger
                ):
                    continue

                frame = result["frame"]

                detected_name = (
                    "COYOTE"
                    if is_coyote_trigger
                    else "PERSON"
                )

                debug_text = (
                    " DEBUG MODE"
                    if (
                        args.debug
                        and not is_coyote_trigger
                    )
                    else ""
                )

                cv2.putText(
                    frame,
                    f"COYOTE DETECTED{debug_text}",
                    (25, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 0, 255),
                    3,
                )

                filename = (
                    snapshot_dir
                    / (
                        f"{timestamp}_"
                        f"{camera_name}_"
                        f"coyote.jpg"
                    )
                )

                cv2.imwrite(
                    str(filename),
                    frame,
                )

                print(
                    f"[{event_time:%F %T %Z}] "
                    f"{detected_name} DETECTED "
                    f"on {camera_name};"
                )

                # --------------------------------------------------
                # Later we can add:
                #
                # save_training_sample(
                #     clean_frame=result["clean_frame"],
                #     preview_frame=result["frame"],
                #     detections=result["detections"],
                #     ...
                # )
                #
                # right here.
                # --------------------------------------------------

            relay.all_on()

            speaker.play(
                repeat=100
            )

    # ==============================================================
    # SMALL DOG OR CAT
    # ==============================================================

    elif (
        enough_time_delay
        and (saw_small_dog or saw_cat)
    ):

        last_event = now

        timestamp = event_time.strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        for camera_name, result in camera_results.items():

            if not (
                result["saw_small_dog"]
                or result["saw_cat"]
            ):
                continue

            filename = (
                snapshot_dir
                / (
                    f"{timestamp}_"
                    f"{camera_name}_"
                    f"not_coyote.jpg"
                )
            )

            cv2.imwrite(
                str(filename),
                result["frame"],
            )

        if last_detection != CAT_CLASS:

            print(
                f"CAT/SMALL DOG DETECTED "
                f"at {timestamp}"
            )

        last_detection = CAT_CLASS

    # ==============================================================
    # PERSON
    # ==============================================================

    elif (
        saw_person
        and last_detection != PERSON_CLASS
    ):

        timestamp = event_time.strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        person_cameras = [
            camera_name
            for camera_name, result
            in camera_results.items()
            if result["saw_person"]
        ]

        print(
            f"PERSON DETECTED "
            f"at {timestamp} "
            f"on {', '.join(person_cameras)}"
        )

        last_detection = PERSON_CLASS

    # ==============================================================
    # ALL CLEAR
    # ==============================================================

    elif (
        enough_time_delay
        and relay.is_all_on
    ):

        print(
            f"[{event_time:%F %T %Z}] "
            "ALL CLEAR;"
        )

        relay.all_off()

        speaker.stop()

        last_detection = NOTHING

    return (
        last_event,
        last_detection,
    )


# ======================================================================
# MAIN
# ======================================================================
paused = False


def toggle_pause(signum, frame):
    global paused
    paused = not paused

    if paused:
        print("PAUSE requested")
    else:
        print("RESUME requested")


def main() -> int:
    global paused
    signal.signal(signal.SIGUSR1, toggle_pause)
    args = arguments()

    if not args.password:

        print(
            "Set the camera password first: "
            "export CAMERA_PASSWORD='your-password'",
            file=sys.stderr,
        )

        return 2

    # ------------------------------------------------------------------
    # Snapshot folder
    # ------------------------------------------------------------------

    snapshot_dir = Path(
        args.snapshots
    )

    snapshot_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------
    # Load YOLO once
    # ------------------------------------------------------------------

    print(
        f"Loading {args.model} ..."
    )

    model = YOLO(
        args.model
    )

    # ------------------------------------------------------------------
    # Camera definitions
    # ------------------------------------------------------------------

    camera_ips = {
        "camera1": CAMERA_IP_1,
        "camera2": CAMERA_IP_2,
    }

    cameras = {}

    # ------------------------------------------------------------------
    # Open cameras
    # ------------------------------------------------------------------

    try:

        for camera_name, camera_ip in camera_ips.items():

            url = rtsp_url(
                camera_ip,
                args.username,
                args.password,
                args.subtype,
            )

            print(
                f"Connecting {camera_name}: "
                f"{camera_ip}"
            )

            cameras[camera_name] = Camera(
                url
            )

            print(
                f"{camera_name} connected."
            )

    except RuntimeError as exc:

        print(
            str(exc),
            file=sys.stderr,
        )

        for camera in cameras.values():
            camera.close()

        return 1

    # ------------------------------------------------------------------
    # Deterrents
    # ------------------------------------------------------------------

    relay = RelayBoard(
        BOARD_ID,
        debug=False,
    )

    speaker = Speaker(
        sound_file=bark_file
    )

    last_event = 0.0
    last_detection = NOTHING

    print(
        f"Detector running on "
        f"{len(cameras)} cameras."
    )

    try:

        while True:
            if paused:
                if relay.is_all_on:
                    relay.all_off()
                    speaker.stop()

                time.sleep(0.1)
                continue

            # ==========================================================
            # STEP 1
            #
            # Get newest frame from ALL cameras.
            # ==========================================================

            frames = {}

            for camera_name, camera in cameras.items():

                frame = camera.latest()

                if frame is not None:

                    frames[camera_name] = frame

            if not frames:

                time.sleep(0.01)
                continue

            # ==========================================================
            # STEP 2
            #
            # Run coyote_detection() on EACH camera frame.
            # ==========================================================

            camera_results = {}

            for camera_name, frame in frames.items():

                camera_results[camera_name] = (
                    coyote_detection(
                        model,
                        frame,
                        args,
                    )
                )

            # ==========================================================
            # STEP 3
            #
            # Make ONE deterrent decision using all camera results.
            # ==========================================================

            (
                last_event,
                last_detection,
            ) = run_deterrants(
                camera_results,
                relay,
                speaker,
                args,
                snapshot_dir,
                last_event,
                last_detection,
            )

            # ==========================================================
            # Optional display
            # ==========================================================

            if args.window:

                for (
                    camera_name,
                    result,
                ) in camera_results.items():

                    cv2.imshow(
                        f"Coyote detector - {camera_name}",
                        result["frame"],
                    )

                if (
                    cv2.waitKey(1) & 0xFF
                    == ord("q")
                ):
                    break

    except KeyboardInterrupt:

        print(
            "\nStopped."
        )

    finally:

        # Make sure deterrents are always left off.
        relay.all_off()

        speaker.stop()

        # Close every camera.
        for camera in cameras.values():
            camera.close()

        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())