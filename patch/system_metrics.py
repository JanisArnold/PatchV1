from __future__ import annotations

import json
import shutil
import subprocess
from typing import Dict, Optional


def collect_system_snapshot() -> Dict[str, object]:
    snapshot: Dict[str, object] = {
        "platform": "unknown",
        "temperature_c": None,
        "throttled_hex": None,
        "arm_clock_hz": None,
        "vcgencmd_available": False,
    }

    vcgencmd = shutil.which("vcgencmd")
    if not vcgencmd:
        return snapshot

    snapshot["platform"] = "raspberry_pi"
    snapshot["vcgencmd_available"] = True
    snapshot["temperature_c"] = _parse_temperature(_run_command([vcgencmd, "measure_temp"]))
    snapshot["throttled_hex"] = _parse_throttled(_run_command([vcgencmd, "get_throttled"]))
    snapshot["arm_clock_hz"] = _parse_clock(_run_command([vcgencmd, "measure_clock", "arm"]))
    return snapshot


def render_system_snapshot(snapshot: Dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, ensure_ascii=True)


def _run_command(command: list[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (completed.stdout or "").strip()
    return output or None


def _parse_temperature(raw: Optional[str]) -> Optional[float]:
    if not raw or "temp=" not in raw:
        return None
    try:
        value = raw.split("temp=", 1)[1].split("'C", 1)[0]
        return float(value)
    except (IndexError, ValueError):
        return None


def _parse_throttled(raw: Optional[str]) -> Optional[str]:
    if not raw or "throttled=" not in raw:
        return None
    try:
        return raw.split("throttled=", 1)[1].strip()
    except IndexError:
        return None


def _parse_clock(raw: Optional[str]) -> Optional[int]:
    if not raw or "=" not in raw:
        return None
    try:
        return int(raw.split("=", 1)[1].strip())
    except ValueError:
        return None
