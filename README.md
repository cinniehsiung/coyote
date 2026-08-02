# Coyote Defense System Notes

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