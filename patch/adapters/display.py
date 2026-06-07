from __future__ import annotations


class NoOpDisplayAdapter:
    def on_state_change(self, state: str) -> None:
        del state
