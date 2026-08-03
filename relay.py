import subprocess

BOARD_ID = "6QMBS"
CHANNEL_LIGHTS = 4
CHANNEL_SPRINKLERS = 3

USBRELAY_PATH = "/usr/bin/usbrelay"


class RelayBoard:
    def __init__(self, board_id: str, debug: bool = False):
        self.board_id = board_id
        self.debug = debug
        self.is_all_on = False

    def set_relay(self, channel: int, on: bool) -> None:
        if not 1 <= channel <= 8:
            raise ValueError(
                f"Relay channel must be between 1 and 8, got {channel}"
            )

        state = 1 if on else 0

        cmd = [
            "/usr/bin/sudo",
            "-n",
            USBRELAY_PATH,
            f"{self.board_id}_{channel}={state}",
        ]

        if self.debug:
            print("Running:", " ".join(cmd))

        result = subprocess.run(
            cmd,
            text=True,
            stdout=None if self.debug else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Unknown usbrelay error"
            raise RuntimeError(
                f"Failed to set relay channel {channel} "
                f"to {state}: {error}"
            )

    def lights_on(self) -> None:
        self.set_relay(CHANNEL_LIGHTS, True)

    def lights_off(self) -> None:
        self.set_relay(CHANNEL_LIGHTS, False)

    def sprinklers_on(self) -> None:
        self.set_relay(CHANNEL_SPRINKLERS, True)

    def sprinklers_off(self) -> None:
        self.set_relay(CHANNEL_SPRINKLERS, False)

    def all_on(self) -> None:
        self.lights_on()
        self.sprinklers_on()
        self.is_all_on = True

    def all_off(self) -> None:
        errors = []

        try:
            self.lights_off()
        except Exception as exc:
            errors.append(f"lights: {exc}")

        try:
            self.sprinklers_off()
        except Exception as exc:
            errors.append(f"sprinklers: {exc}")

        self.is_all_on = False

        if errors:
            raise RuntimeError(
                "Could not turn off all relays: " + "; ".join(errors)
            )