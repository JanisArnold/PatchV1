# Deployment

## Goal

The simplest workflow is:

1. code on your PC
2. test locally on your PC
3. copy the project to the Pi
4. create a Python environment on the Pi
5. run PATCH there in terminal mode first
6. later add `systemd` for auto-start

This page is only about getting the code onto the Pi and running it there. For Pi provisioning, use [Pi Setup](pi-setup.md). For model behavior and commands, use [Testing Guide](testing.md).

## Option 1: Copy the project folder manually

This is the easiest first deployment path.

From your PC, copy the repo to the Pi with `scp`:

```powershell
scp -r . <your-user>@patch-pi.local:~/patch/
```

Then SSH into the Pi:

```powershell
ssh <your-user>@patch-pi.local
```

Set up the Python environment:

```bash
cd ~/patch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/settings.example.json config/settings.json
python3 -m patch.cli
```

## Option 2: Use Git

Once you want a cleaner workflow, use a Git repository and clone it on the Pi:

```bash
git clone <your-repo-url> ~/patch
cd ~/patch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/settings.example.json config/settings.json
python3 -m patch.cli
```

For updates later:

```bash
cd ~/patch
git pull
source .venv/bin/activate
pip install -r requirements.txt
python3 -m patch.cli
```

## What should be copied to the Pi

Copy:

- source code
- `config/settings.json`
- persona file if you customize it

Usually do not copy:

- local `.venv`
- `__pycache__`
- large desktop-only test artifacts

Decide case by case for:

- `data/patch.db`

If you want PATCH to keep its memory when moving from PC to Pi, copy the database file too. If you want the Pi to start fresh, do not copy it.

## Recommended first Pi test

Before voice, display, or camera work, verify this exact flow on the Pi:

1. PATCH starts in terminal mode
2. PATCH can talk to Ollama
3. PATCH can save memory in SQLite
4. `/models` works
5. `/facts` works
6. `/benchmark` works

If those pass, your core brain platform is working on the Pi.

## Later: run PATCH automatically with systemd

Create a service file like:

```ini
[Unit]
Description=PATCH Brain
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/pi/patch
ExecStart=/home/pi/patch/.venv/bin/python3 -m patch.cli
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo cp patch.service /etc/systemd/system/patch.service
sudo systemctl daemon-reload
sudo systemctl enable patch.service
sudo systemctl start patch.service
sudo systemctl status patch.service
```

This should come after terminal-mode validation, not before.
