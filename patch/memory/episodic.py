"""Episodic memory backends.

The spec's target on the Pi is LanceDB + all-MiniLM-L6-v2 embeddings: disk-based
vectors that never compete with the LLM for RAM. The keyword backend is the
zero-dependency default so the three-tier memory design works everywhere; swap
to the LanceDB backend once `lancedb` and `sentence-transformers` are installed.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from patch.contracts import EpisodicMemory
from patch.memory.store import SQLiteMemoryStore


class KeywordEpisodicIndex:
    """Token-overlap retrieval over the SQLite `episodes` table."""

    def __init__(self, store: SQLiteMemoryStore) -> None:
        self._store = store

    def add(self, *, user_text: str, assistant_text: str, session_id: int) -> None:
        self._store.add_episode(
            session_id=session_id,
            user_text=user_text,
            assistant_text=assistant_text,
        )

    def search(self, query: str, limit: int) -> List[EpisodicMemory]:
        return self._store.search_episodes(query, limit)


class LanceDbEpisodicIndex:
    """Vector retrieval via LanceDB and sentence-transformers.

    Requires: pip install lancedb sentence-transformers
    Embedding happens on whichever thread calls add()/search(), so writes should
    stay on the background memory worker to keep the hot path clean.
    """

    TABLE_NAME = "episodes"
    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, data_dir: Path) -> None:
        try:
            import lancedb
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Episodic backend 'lancedb' needs optional dependencies: "
                "pip install lancedb sentence-transformers"
            ) from exc
        self._db = lancedb.connect(str(data_dir / "lancedb"))
        self._encoder = SentenceTransformer(self.EMBEDDING_MODEL)
        self._table = None
        if self.TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(self.TABLE_NAME)

    def add(self, *, user_text: str, assistant_text: str, session_id: int) -> None:
        import datetime

        vector = self._encoder.encode(f"{user_text}\n{assistant_text}").tolist()
        record = {
            "vector": vector,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "session_id": session_id,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if self._table is None:
            self._table = self._db.create_table(self.TABLE_NAME, data=[record])
        else:
            self._table.add([record])

    def search(self, query: str, limit: int) -> List[EpisodicMemory]:
        if self._table is None:
            return []
        vector = self._encoder.encode(query).tolist()
        rows = self._table.search(vector).limit(limit).to_list()
        return [
            EpisodicMemory(
                user_text=row["user_text"],
                assistant_text=row["assistant_text"],
                created_at=row["created_at"],
                score=float(row.get("_distance", 0.0)),
            )
            for row in rows
        ]


def build_episodic_index(*, backend: str, store: SQLiteMemoryStore, data_dir: Path):
    if backend == "lancedb":
        return LanceDbEpisodicIndex(data_dir)
    return KeywordEpisodicIndex(store)
