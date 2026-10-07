#!/usr/bin/env python3

from __future__ import annotations

import html
import json
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo


HOST = "127.0.0.1"
PORT = 8765

COYOTE_SERVICE = "coyote.service"

ROOT = Path(__file__).resolve().parent
SCHEDULE_FILE = ROOT / "coyote_schedule.json"

TIME_ZONE = ZoneInfo("America/Los_Angeles")

DEFAULT_SCHEDULE = {
    "enabled": False,
    "arm_time": "18:00",
    "pause_time": "07:00",
}

schedule_lock = threading.Lock()


# ======================================================================
# SYSTEMD CONTROL
# ======================================================================

def service_is_running() -> bool:
    result = subprocess.run(
        [
            "/usr/bin/systemctl",
            "is-active",
            "--quiet",
            COYOTE_SERVICE,
        ],
        check=False,
    )

    return result.returncode == 0


def start_coyote() -> None:
    subprocess.run(
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/systemctl",
            "start",
            COYOTE_SERVICE,
        ],
        check=True,
    )


def stop_coyote() -> None:
    subprocess.run(
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/systemctl",
            "stop",
            COYOTE_SERVICE,
        ],
        check=True,
    )


def toggle_coyote() -> bool:
    if service_is_running():
        stop_coyote()
        return False

    start_coyote()
    return True


# ======================================================================
# SCHEDULE
# ======================================================================

def load_schedule() -> dict:
    with schedule_lock:

        if not SCHEDULE_FILE.exists():
            return DEFAULT_SCHEDULE.copy()

        try:
            data = json.loads(
                SCHEDULE_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            return DEFAULT_SCHEDULE.copy()

        return {
            "enabled": bool(
                data.get("enabled", False)
            ),
            "arm_time": str(
                data.get("arm_time", "18:00")
            ),
            "pause_time": str(
                data.get("pause_time", "07:00")
            ),
        }


def save_schedule(schedule: dict) -> None:
    with schedule_lock:

        SCHEDULE_FILE.write_text(
            json.dumps(
                schedule,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def valid_time(value: str) -> bool:
    try:
        datetime.strptime(
            value,
            "%H:%M",
        )
        return True

    except ValueError:
        return False


def schedule_worker() -> None:
    """Execute schedule transitions.

    Manual ARM/PAUSE overrides remain in effect until the next
    scheduled transition.
    """

    last_processed_minute = None

    while True:

        try:
            now = datetime.now(
                TIME_ZONE
            )

            current_minute = now.strftime(
                "%Y-%m-%d %H:%M"
            )

            # Only process each clock minute once.
            if current_minute != last_processed_minute:

                last_processed_minute = current_minute

                schedule = load_schedule()

                if schedule["enabled"]:

                    current_time = now.strftime(
                        "%H:%M"
                    )

                    if (
                        current_time
                        == schedule["arm_time"]
                    ):
                        if not service_is_running():
                            print(
                                "Schedule: ARMING "
                                f"at {current_time}"
                            )
                            start_coyote()

                    elif (
                        current_time
                        == schedule["pause_time"]
                    ):
                        if service_is_running():
                            print(
                                "Schedule: PAUSING "
                                f"at {current_time}"
                            )
                            stop_coyote()

        except Exception as exc:
            print(
                f"Schedule error: {exc}"
            )

        time.sleep(5)


# ======================================================================
# HTML
# ======================================================================

def page_html() -> str:
    schedule = load_schedule()

    checked = (
        "checked"
        if schedule["enabled"]
        else ""
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>
<title>Coyote Deterrent</title>

<style>

body {{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    margin: 0;
    background: #f3f4f6;
    color: #111827;
}}

.container {{
    max-width: 700px;
    margin: 40px auto;
    padding: 20px;
}}

.card {{
    background: white;
    border-radius: 20px;
    padding: 28px;
    margin-bottom: 24px;

    box-shadow:
        0 4px 20px
        rgba(0,0,0,0.08);
}}

h1 {{
    margin-top: 0;
    font-size: 32px;
}}

.status {{
    text-align: center;
    margin: 30px 0;
}}

.status-text {{
    font-size: 42px;
    font-weight: 800;
    margin-bottom: 20px;
}}

.status-running {{
    color: #15803d;
}}

.status-paused {{
    color: #b91c1c;
}}

.status-offline {{
    color: #b91c1c;
}}

.offline-button {{
    background: #6b7280;
    cursor: not-allowed;
}}

.big-button {{
    width: 100%;
    min-height: 100px;

    border: none;
    border-radius: 18px;

    font-size: 30px;
    font-weight: 800;

    cursor: pointer;

    color: white;
}}

.arm-button {{
    background: #15803d;
}}

.pause-button {{
    background: #b91c1c;
}}

.schedule-grid {{
    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 18px;

    margin-top: 20px;
}}

label {{
    display: block;
    font-weight: 600;
    margin-bottom: 8px;
}}

input[type="time"] {{
    width: 100%;
    box-sizing: border-box;

    padding: 12px;

    font-size: 18px;

    border:
        1px solid #d1d5db;

    border-radius: 10px;
}}

.save-button {{
    margin-top: 24px;

    width: 100%;
    min-height: 52px;

    border: none;
    border-radius: 12px;

    background: #374151;
    color: white;

    font-size: 18px;
    font-weight: 700;

    cursor: pointer;
}}

.switch-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;

    gap: 20px;
}}

.switch {{
    width: 70px;
    height: 38px;
}}

.small {{
    color: #6b7280;
    margin-top: 12px;
}}

#error {{
    color: #b91c1c;
    font-weight: 600;
    margin-top: 15px;
}}

@media (max-width: 600px) {{

    .container {{
        margin: 10px auto;
        padding: 12px;
    }}

    .schedule-grid {{
        grid-template-columns: 1fr;
    }}

    .status-text {{
        font-size: 34px;
    }}
}}

</style>
</head>

<body>

<div class="container">

    <div class="card">

        <h1>Coyote Deterrent</h1>

        <div class="status">

            <div
                id="status"
                class="status-text"
            >
                Checking...
            </div>

            <button
                id="toggle"
                class="big-button"
                type="button"
            >
                Please wait
            </button>

            <div id="error"></div>

        </div>

    </div>


    <div class="card">

        <div class="switch-row">

            <div>
                <h2>Automatic Schedule</h2>

                <div class="small">
                    Schedule uses Cupertino / Pacific time.
                </div>
            </div>

            <input
                id="enabled"
                class="switch"
                type="checkbox"
                {checked}
            >

        </div>


        <div class="schedule-grid">

            <div>
                <label for="arm_time">
                    Arm system at
                </label>

                <input
                    id="arm_time"
                    type="time"
                    value="{html.escape(schedule["arm_time"])}"
                >
            </div>


            <div>
                <label for="pause_time">
                    Pause system at
                </label>

                <input
                    id="pause_time"
                    type="time"
                    value="{html.escape(schedule["pause_time"])}"
                >
            </div>

        </div>


        <button
            id="save_schedule"
            class="save-button"
            type="button"
        >
            Save Schedule
        </button>

        <div
            id="schedule_message"
            class="small"
        ></div>

    </div>

</div>


<script>

const statusElement =
    document.getElementById("status");

const toggleButton =
    document.getElementById("toggle");

const errorElement =
    document.getElementById("error");

const scheduleEnabled =
    document.getElementById("enabled");

const armTimeInput =
    document.getElementById("arm_time");

const pauseTimeInput =
    document.getElementById("pause_time");

const saveScheduleButton =
    document.getElementById("save_schedule");


function setControlsAvailable(available) {{
    scheduleEnabled.disabled = !available;
    armTimeInput.disabled = !available;
    pauseTimeInput.disabled = !available;
    saveScheduleButton.disabled = !available;
}}


function showOffline(message) {{
    statusElement.textContent =
        "⚠ CONNECTION LOST";

    statusElement.className =
        "status-text status-offline";

    toggleButton.textContent =
        "COYOTE COMPUTER UNREACHABLE";

    toggleButton.className =
        "big-button offline-button";

    toggleButton.disabled = true;

    setControlsAvailable(false);

    errorElement.textContent =
        message ||
        "Cannot communicate with the Coyote control system.";
}}


async function refreshStatus() {{

    try {{

        const response =
            await fetch(
                "/api/status",
                {{
                    cache: "no-store"
                }}
            );

        if (!response.ok) {{
            throw new Error(
                "Coyote control service returned an error"
            );
        }}

        const data =
            await response.json();

        errorElement.textContent = "";

        setControlsAvailable(true);
        toggleButton.disabled = false;

        if (data.running) {{

            statusElement.textContent =
                "ARMED";

            statusElement.className =
                "status-text status-running";

            toggleButton.textContent =
                "PAUSE SYSTEM";

            toggleButton.className =
                "big-button pause-button";

        }} else {{

            statusElement.textContent =
                "PAUSED";

            statusElement.className =
                "status-text status-paused";

            toggleButton.textContent =
                "ARM SYSTEM";

            toggleButton.className =
                "big-button arm-button";
        }}

    }} catch (error) {{

        showOffline(
            "Cannot communicate with the Coyote computer."
        );
    }}
}}


toggleButton.addEventListener(
    "click",
    async () => {{

        toggleButton.disabled = true;

        try {{

            const response =
                await fetch(
                    "/api/toggle",
                    {{
                        method: "POST"
                    }}
                );

            if (!response.ok) {{
                let message = "Toggle failed";

                try {{
                    const data =
                        await response.json();

                    message =
                        data.error
                        || message;

                }} catch (ignored) {{
                    // Keep the default message.
                }}

                throw new Error(message);
            }}

            await refreshStatus();

        }} catch (error) {{

            showOffline(
                "The command could not reach the Coyote control system."
            );
        }}
    }}
);


document
    .getElementById("save_schedule")
    .addEventListener(
        "click",
        async () => {{

            const enabled =
                document
                .getElementById("enabled")
                .checked;

            const armTime =
                document
                .getElementById("arm_time")
                .value;

            const pauseTime =
                document
                .getElementById("pause_time")
                .value;

            const body =
                new URLSearchParams();

            body.set(
                "enabled",
                enabled ? "1" : "0"
            );

            body.set(
                "arm_time",
                armTime
            );

            body.set(
                "pause_time",
                pauseTime
            );

            const message =
                document.getElementById(
                    "schedule_message"
                );

            try {{

                const response =
                    await fetch(
                        "/api/schedule",
                        {{
                            method: "POST",

                            headers: {{
                                "Content-Type":
                                    "application/x-www-form-urlencoded"
                            }},

                            body
                        }}
                    );

                const data =
                    await response.json();

                if (response.ok) {{

                    message.textContent =
                        "Schedule saved.";

                }} else {{

                    message.textContent =
                        data.error
                        || "Could not save schedule.";
                }}

            }} catch (error) {{

                message.textContent =
                    "Connection lost. Schedule was not saved.";

                showOffline(
                    "Cannot communicate with the Coyote computer."
                );
            }}
        }}
    );


refreshStatus();

setInterval(
    refreshStatus,
    2000
);

</script>

</body>
</html>
"""


# ======================================================================
# HTTP SERVER
# ======================================================================

class Handler(BaseHTTPRequestHandler):

    def send_json(
        self,
        data,
        status=200,
    ):

        body = json.dumps(
            data
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(body)


    def do_GET(self):

        if self.path == "/":

            body = page_html().encode(
                "utf-8"
            )

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8",
            )

            self.send_header(
                "Content-Length",
                str(len(body)),
            )

            self.end_headers()

            self.wfile.write(body)

            return


        if self.path == "/api/status":

            self.send_json(
                {
                    "running":
                        service_is_running()
                }
            )

            return


        self.send_error(404)


    def do_POST(self):

        if self.path == "/api/toggle":

            try:

                running = toggle_coyote()

                self.send_json(
                    {
                        "running":
                            running
                    }
                )

            except Exception as exc:

                self.send_json(
                    {
                        "error":
                            str(exc)
                    },
                    status=500,
                )

            return


        if self.path == "/api/schedule":

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            body = self.rfile.read(
                length
            ).decode("utf-8")

            data = parse_qs(body)

            enabled = (
                data.get(
                    "enabled",
                    ["0"],
                )[0]
                == "1"
            )

            arm_time = data.get(
                "arm_time",
                [""],
            )[0]

            pause_time = data.get(
                "pause_time",
                [""],
            )[0]

            if not valid_time(arm_time):
                self.send_json(
                    {
                        "error":
                            "Invalid arm time."
                    },
                    status=400,
                )
                return

            if not valid_time(pause_time):
                self.send_json(
                    {
                        "error":
                            "Invalid pause time."
                    },
                    status=400,
                )
                return

            if arm_time == pause_time:
                self.send_json(
                    {
                        "error":
                            "Arm and pause times "
                            "must be different."
                    },
                    status=400,
                )
                return

            schedule = {
                "enabled":
                    enabled,

                "arm_time":
                    arm_time,

                "pause_time":
                    pause_time,
            }

            save_schedule(
                schedule
            )

            self.send_json(
                {
                    "ok": True
                }
            )

            return


        self.send_error(404)


    def log_message(
        self,
        format,
        *args,
    ):
        # Avoid filling the journal with
        # status-poll messages.
        pass


# ======================================================================
# MAIN
# ======================================================================

def main():

    print(
        f"Coyote control UI listening on "
        f"{HOST}:{PORT}"
    )

    scheduler = threading.Thread(
        target=schedule_worker,
        daemon=True,
    )

    scheduler.start()

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
