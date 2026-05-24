from __future__ import annotations

from pathlib import Path


DEFAULT_PERSONA = """You are PATCH, a warm and practical desktop AI companion.
Keep replies helpful, grounded, and concise.
Use remembered information when it is relevant, but do not force it into unrelated replies.
If you are uncertain, say so clearly.
"""


def load_persona() -> str:
    persona_path = Path("config/persona.md")
    if persona_path.exists():
        return persona_path.read_text(encoding="utf-8").strip()
    example_path = Path("config/persona.example.md")
    if example_path.exists():
        return example_path.read_text(encoding="utf-8").strip()
    return DEFAULT_PERSONA.strip()
