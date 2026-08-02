import subprocess

BOARD_ID = "6QMBS"  # ID printed by `sudo usbrelay`
CHANNEL_LIGHTS = 4
CHANNEL_SPRINKLERS = 3


class RelayBoard:
    def __init__(self, board_id, debug=False):
        self.board_id = board_id
        self.debug = debug
        self.is_all_on = False

    def set_relay(self, channel, on):
        state = 1 if on else 0

        cmd = [
            "sudo",
            "-n",
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
        self.set_relay(CHANNEL_LIGHTS, True)

    def lights_off(self):
        self.set_relay(CHANNEL_LIGHTS, False)

    def sprinklers_on(self):
        self.set_relay(CHANNEL_SPRINKLERS, True)

    def sprinklers_off(self):
        self.set_relay(CHANNEL_SPRINKLERS, False)

    def all_on(self):
        self.lights_on()
        self.sprinklers_on()
        self.is_all_on = True

    def all_off(self):
        self.lights_off()
        self.sprinklers_off()
        self.is_all_on = False
