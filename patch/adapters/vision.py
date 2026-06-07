from __future__ import annotations

from typing import Optional


class NoOpVisionAdapter:
    def capture_scene_description(self, prompt: Optional[str] = None) -> Optional[str]:
        del prompt
        return None
