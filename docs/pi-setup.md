# Pi Setup

## Goal

Use your PC for development, then deploy the same project onto the Raspberry Pi for testing. The Pi should be treated as a target machine, not the main development environment.

## Recommended Pi baseline for V1

- Raspberry Pi 4 with 8 GB RAM
- Raspberry Pi OS Lite 64-bit
- SSH enabled
- camera enabled later when hardware arrives
- reliable power supply
- Wi-Fi or Ethernet

For the current PATCH phase, `Lite 64-bit` is the recommended choice because:

- PATCH is still terminal-first
- the Pi should stay as lean as possible
- you do not need the desktop environment yet
- the Pi 4 benefits from the 64-bit OS for heavier local compute tasks

## 1. Flash the OS

Use Raspberry Pi Imager and choose:

- `Raspberry Pi OS Lite (64-bit)`

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

If `patch-pi.local` does not resolve on your PC, use the Pi's current IP address instead. This is commonly a local hostname resolution issue on the client machine or network, not a Pi problem.

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
sudo apt install -y libcamera-apps alsa-utils ffmpeg
```

## 5. Get PATCH onto the Pi

The recommended workflow is to clone the repository directly on the Pi.

```bash
git clone <your-repo-url> ~/patch
cd ~/patch
```

Why this is the preferred path:

- easiest to keep the Pi updated
- avoids copying local desktop artifacts
- cleanest public-repo workflow
- matches the contributor documentation

After cloning:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/settings.example.json config/settings.json
```

The `~/patch` directory will be created by the clone step. Runtime files such as the SQLite database will be created automatically later when PATCH starts.

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

## 7. First PATCH startup on the Pi

Start in terminal mode first:

```bash
cd ~/patch
source .venv/bin/activate
python3 -m patch.cli
```

Before adding any hardware features, confirm:

1. PATCH starts successfully
2. Ollama is reachable
3. SQLite memory is created
4. `/models` works
5. `/facts` works
6. `/benchmark` works

Only after that should you move on to audio, camera, or display integration.

## 8. Prepare for future hardware

When your hardware arrives, add and test these one at a time:

- display
- microphone
- speaker
- camera

Do not connect all peripherals and debug everything at once. Bring up one subsystem at a time.

## 9. First audio hardware test

Before integrating speech into PATCH, test the microphone and speaker directly with ALSA.

List audio devices:

```bash
arecord -l
aplay -l
```

For a USB microphone, the capture device may appear as something like:

- `card 3, device 0`
- `USB PnP Sound Device`

Test live microphone levels:

```bash
arecord -D plughw:3,0 -vv -f cd -d 10 /dev/null
```

Test recording:

```bash
arecord -D plughw:3,0 -d 5 -f cd test-mic.wav
```

Then test playback:

```bash
aplay -D plughw:0,0 test-mic.wav
```

For small single-speaker output, mono-style playback is often clearer than stereo channel tests. If `speaker-test -c 2` sounds uneven between left and right, that is not necessarily a blocker for PATCH.

Mic gain can be adjusted with:

```bash
alsamixer -c 3
```

Useful controls for many USB mics:

- `Mic`
- `Auto Gain Control`

If close-range speech becomes understandable with `Mic` at a high level, the microphone is good enough for first PATCH integration.

## 10. First voice software test

After raw audio devices work, test text-to-speech outside PATCH first.

Inside the PATCH virtual environment:

```bash
cd ~/patch
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install piper-tts vosk
```

Create a local voice folder:

```bash
mkdir -p ~/patch/voices
```

Download a first Piper voice:

```bash
python3 -m piper.download_voices --data-dir ~/patch/voices en_US-lessac-medium
```

Generate a WAV file:

```bash
python3 -m piper --data-dir ~/patch/voices -m en_US-lessac-medium -f test-tts.wav -- "Hello, I am Patch. This is my first voice test on the Raspberry Pi."
```

Play it back through the working output:

```bash
aplay -D plughw:0,0 test-tts.wav
```

This validates the Pi TTS path before integrating it into PATCH.

For speech-to-text, the recommended first path is `Vosk` because it is lighter than Whisper-based options on a Pi 4.

Recommended next STT step after TTS succeeds:

- record one mic sample with `arecord`
- run a minimal Vosk transcription test
- only then integrate STT into PATCH

## 11. Performance and temperature checks

When testing on the Pi, use both PATCH-level and shell-level checks.

Inside PATCH:

```text
/perf
/system
```

In the shell:

```bash
vcgencmd measure_temp
vcgencmd get_throttled
vcgencmd measure_clock arm
```

What to watch:

- temperature while idle
- temperature during model replies
- whether throttling flags appear
- whether total PATCH turn time is much larger than pure model time

If a fan meaningfully lowers temperature and throttling disappears, that should also show up in your repeated `/system` snapshots and faster interaction timings.

## Practical advice

- Develop on your PC.
- Keep the Pi as the integration target.
- Start with text mode on the Pi too before adding voice or vision.
- If SD card performance becomes annoying later, move models or app data to a USB SSD.
- Use one local model first and optimize that path before adding cloud, camera loops, or always-on voice features.
- Treat `git clone` on the Pi as the default deployment path unless you have a specific reason to copy files manually.
- On Pi OS Lite, expect ALSA tools such as `arecord`, `aplay`, and `alsamixer` to be the first useful audio test tools before any higher-level audio stack is added.
