"""Sentence-level streaming support.

On a Pi the LLM generates a few tokens per second, so waiting for the full
reply before speaking adds many seconds of dead air. The assembler turns a
token stream into complete sentences so TTS can start speaking the first
sentence while the rest is still generating.
"""
from __future__ import annotations

import re
from typing import List

_SENTENCE_END = re.compile(r"([.!?]+[\"')\]]?)(\s|$)")
# Don't speak fragments like "Dr." or "1." as complete sentences.
_MIN_SENTENCE_CHARS = 12


class SentenceAssembler:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, token: str) -> List[str]:
        """Add a token; return any sentences completed by it."""
        self._buffer += token
        sentences: List[str] = []
        search_from = 0
        while True:
            match = _SENTENCE_END.search(self._buffer, search_from)
            if match is None:
                break
            end = match.end(1)
            candidate = self._buffer[:end].strip()
            if len(candidate) < _MIN_SENTENCE_CHARS:
                # Probably an abbreviation or a very short fragment; merge it
                # into the next sentence instead of speaking it alone.
                search_from = end
                continue
            sentences.append(candidate)
            self._buffer = self._buffer[end:].lstrip()
            search_from = 0
        return sentences

    def flush(self) -> List[str]:
        """Return whatever is left after the stream ends."""
        remainder = self._buffer.strip()
        self._buffer = ""
        return [remainder] if remainder else []
