# Pi Setup

## Goal

Use your PC for development and the Pi as the target integration machine. The current Pi-first runtime assumes:

- Raspberry Pi OS Lite 64-bit
- `llama.cpp` as the local inference runtime
- ALSA for first audio bring-up
- Vosk for STT
- Piper for TTS

## Recommended baseline

- Raspberry Pi 4 with 8 GB RAM
- Raspberry Pi OS Lite 64-bit
- SSH enabled
- reliable power supply
- active cooling if possible

## 1. Flash and boot

Use Raspberry Pi Imager and choose:

- `Raspberry Pi OS Lite (64-bit)`

Before writing the SD card, set:

- hostname: `patch-pi`
- username and password
- Wi-Fi if needed
- SSH enabled

If `patch-pi.local` does not resolve on your PC later, use the Pi IP address instead.

## 2. Base packages

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3 python3-venv python3-pip git sqlite3 curl alsa-utils ffmpeg unzip
```

## 3. Clone PATCH

```bash
git clone <your-repo-url> ~/patch
cd ~/patch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/settings.example.json config/settings.json
```

## 4. Install `llama.cpp`

PATCH V1 assumes you start `llama-server` yourself.

A typical flow is:

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build
cmake --build build --config Release -j4
```

Then start the server with your chosen GGUF model and tuned flags. Keep the model ID aligned with the PATCH profile names in `config/settings.json`.

Example shape:

```bash
~/llama.cpp/build/bin/llama-server -m /home/<your-user>/models/gemma4-e2b-q4.gguf --host 127.0.0.1 --port 8080
```

PATCH expects the server to stay running while it is active.

## 5. First PATCH startup

```bash
cd ~/patch
source .venv/bin/activate
python3 -m patch.cli
```

First checks inside PATCH:

```text
/help
/models
/mode
/system
```

## 6. Audio bring-up

List devices:

```bash
arecord -l
aplay -l
```

Typical USB mic test:

```bash
arecord -D plughw:3,0 -vv -f cd -d 10 /dev/null
arecord -D plughw:3,0 -d 5 -f cd test-mic.wav
aplay -D plughw:0,0 test-mic.wav
```

If levels are too low, use:

```bash
alsamixer -c 3
```

For a simple mono speech output path, a clear single-speaker result is good enough for PATCH.

## 7. Install Pi voice dependencies

PATCH’s standalone voice loop needs extra Pi packages that are not part of the base Python requirements yet.

Inside the PATCH venv:

```bash
python3 -m pip install piper-tts vosk
```

Download a Vosk model and a Piper voice into the configured paths.

## 8. First voice-loop test

After Vosk and Piper are installed:

```bash
python3 -m patch.voice_loop_test
```

This gives you:

- mic capture
- STT
- PATCH reply generation
- TTS
- speaker playback
- stage-level performance logs

## 9. Performance and temperature checks

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

If your fan is helping, repeated `/system` snapshots should show lower temperature and fewer throttling events during reply generation.

## Practical advice

- keep one model loaded and warm
- use `fast` mode on the Pi first
- keep context small
- keep camera disabled until the audio loop feels good
- treat the screen as an event-driven state consumer later, not part of the reply bottleneck
