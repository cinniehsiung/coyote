# Coyote Defense System Notes

The startup procedure is as follows:
```
ssh coyote
coyote_setup
python3 main.py
```

For the systemc route:
```
# To start the service:
sudo systemctl start coyote.service
# To restart the service after changing code:
sudo systemctl restart coyote.service
# To get recent logs:
sudo journalctl -u coyote.service -n 80 --no-pager
# To inspect the process:
sudo systemctl status coyote.service --no-pager
```

## Camera Notes
ip addr: 192.168.1.108
ip addr: 192.168.1.109
username: admin
pw: CAMERA_PASSWORD

Forward IP through remote:
```
ssh -N -L 8080:192.168.1.108:80 coyote
```

Then access through:
```
http://localhost:8080
```

// To make the thing work, need to add it.
sudo ip addr add 192.168.1.10/24 dev eno1

## USB Relay Notes
```
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="05df", MODE="0666"' | sudo tee /etc/udev/rules.d/99-usbrelay.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```
## YOLO Model notes
yolo11m -- seems to be standard
yolo11n -- chatgpt started with this but apparently it is the most shitty for low memory devices
yolo11x -- apparently the most accurate but largest as well

there are apparently also the 8 variations, need to test it

## Linux Desktop Settings
sudo cpupower frequency-set -g performance

```
# Contents of /etc/systemd/system/coyote.service

[Unit]
Description=Coyote AI Detection and Deterrent
Wants=network-online.target
After=network-online.target

[Service]
Type=simple

User=coyoteaiedge1-0
Group=coyoteaiedge1-0

WorkingDirectory=/home/coyoteaiedge1-0/coyote

ExecStartPre=-/usr/sbin/ip addr add 192.168.1.10/24 dev eno1

EnvironmentFile=/etc/coyote.env
Environment=PYTHONUNBUFFERED=1
Environment=HOME=/home/coyoteaiedge1-0

# Connect to the user's existing PipeWire/PulseAudio session.
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
Environment=PULSE_SERVER=unix:/run/user/1000/pulse/native

ExecStart=/home/coyoteaiedge1-0/coyote/.venv/bin/python -u /home/coyoteaiedge1-0/coyote/main.py

Restart=on-failure
RestartSec=5

KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

```
# Contents of /etc/coyote.env

CAMERA_PASSWORD=PUT_YOUR_REAL_CAMERA_PASSWORD_HERE
```