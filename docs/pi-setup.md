# Pi Setup

## Goal

Use your PC for development, then deploy the same project onto the Raspberry Pi for testing. The Pi should be treated as a target machine, not the main development environment.

## Recommended Pi baseline for V1

- Raspberry Pi 4 with 8 GB RAM
- Raspberry Pi OS 64-bit
- SSH enabled
- camera enabled later when hardware arrives
- reliable power supply
- Wi-Fi or Ethernet

## 1. Flash the OS

Use Raspberry Pi Imager and choose:

- `Raspberry Pi OS (64-bit)`

Before writing the SD card, open the advanced options and set:

- hostname: `patch-pi`
- username
- password
- Wi-Fi SSID and password if needed
- enable SSH
- locale and keyboard layout

## 2. First boot checks

After the Pi starts, connect from your PC:

```powershell
ssh <your-user>@patch-pi.local
```

Then update the Pi:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Reconnect and verify:

```bash
uname -a
python3 --version
free -h
```

## 3. Enable core Pi features

Open Raspberry Pi configuration:

```bash
sudo raspi-config
```

Recommended settings:

- enable camera interface when you have the camera
- confirm SSH is enabled
- set timezone and locale correctly
- set hostname if not already done

## 4. Install system packages

Install the base packages PATCH will need:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git sqlite3 curl
```

Optional but useful later:

```bash
sudo apt install -y libcamera-apps
```

## 5. Create app directories

Recommended layout on the Pi:

```bash
mkdir -p ~/patch
mkdir -p ~/patch/logs
mkdir -p ~/patch/data
```

## 6. Install Ollama on the Pi

Do this only if the Pi itself should run the local model.

Check current Raspberry Pi support and install instructions from Ollama before relying on this for V1. If Pi performance is too limited, keep PATCH on the Pi but move heavier inference to a stronger machine later.

After installation, verify:

```bash
ollama list
```

Pull a small model first:

```bash
ollama pull gemma4:e2b
```

## 7. Prepare for future hardware

When your hardware arrives, add and test these one at a time:

- display
- microphone
- speaker
- camera

Do not connect all peripherals and debug everything at once. Bring up one subsystem at a time.

## Practical advice

- Develop on your PC.
- Keep the Pi as the integration target.
- Start with text mode on the Pi too before adding voice or vision.
- If SD card performance becomes annoying later, move models or app data to a USB SSD.
- Use one local model first and optimize that path before adding cloud, camera loops, or always-on voice features.
