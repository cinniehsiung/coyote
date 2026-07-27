import subprocess

BOARD_ID = "6QMBS"  # ID printed by `sudo usbrelay`


class RelayBoard:
    def __init__(self, board_id, debug=False):
        self.board_id = board_id
        self.debug = debug

    def set_relay(self, channel, on):
        state = 1 if on else 0

        cmd = [
            "sudo",
            "usbrelay",
            f"{self.board_id}_{channel}={state}"
        ]

        if self.debug:
            print("Running:", " ".join(cmd))
            subprocess.run(cmd, check=True)
        else:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    def lights_on(self):
        self.set_relay(1, True)

    def lights_off(self):
        self.set_relay(1, False)