from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from patch.contracts import ChatMessage, EpisodicMemory, MemoryBundle, MemoryFact


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "for", "from",
    "have", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "so",
    "that", "the", "this", "to", "was", "we", "what", "when", "with", "you", "your",
}


def tokenize(text: str) -> List[str]:
    return [token for token in _TOKEN_PATTERN.findall(text.lower()) if token not in _STOPWORDS]


def _fts_query(text: str) -> str:
    """Build an OR-of-terms FTS5 query; quoting keeps user text from being
    parsed as FTS syntax."""
    return " OR ".join(f'"{token}"' for token in tokenize(text))


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    summary_text TEXT NOT NULL,
    turn_count INTEGER NOT NULL,
    last_turn_id INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_turn_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subject, predicate, value),
    FOREIGN KEY (source_turn_id) REFERENCES turns(id)
);
"""

# External-content FTS5 indexes kept in sync by triggers. BM25 ranking
# replaces the old load-everything-and-score-in-Python retrieval.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    subject, predicate, value,
    content='facts', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS facts_fts_insert AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, subject, predicate, value)
    VALUES (new.id, new.subject, new.predicate, new.value);
END;

CREATE TRIGGER IF NOT EXISTS facts_fts_delete AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, subject, predicate, value)
    VALUES ('delete', old.id, old.subject, old.predicate, old.value);
END;

CREATE TRIGGER IF NOT EXISTS facts_fts_update AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, subject, predicate, value)
    VALUES ('delete', old.id, old.subject, old.predicate, old.value);
    INSERT INTO facts_fts(rowid, subject, predicate, value)
    VALUES (new.id, new.subject, new.predicate, new.value);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    user_text, assistant_text,
    content='episodes', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS episodes_fts_insert AFTER INSERT ON episodes BEGIN
    INSERT INTO episodes_fts(rowid, user_text, assistant_text)
    VALUES (new.id, new.user_text, new.assistant_text);
END;
"""

SCHEMA_VERSION = 3


class SQLiteMemoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        # WAL lets the hot path and the background memory worker write through
        # separate connections without blocking each other.
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        # Old DBs may keep a legacy NOT NULL episodes.tokens column that
        # SQLite cannot drop; inserts then need to fill it.
        self._episodes_need_tokens = False
        self._ensure_schema()

    def close(self) -> None:
        self.connection.close()

    def _ensure_schema(self) -> None:
        self.connection.executescript(SCHEMA)
        previous_version = self._read_schema_version()
        self._migrate_schema()
        self.connection.executescript(FTS_SCHEMA)
        if previous_version < SCHEMA_VERSION:
            # Backfill the FTS indexes from pre-FTS rows.
            self.connection.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
            self.connection.execute("INSERT INTO episodes_fts(episodes_fts) VALUES('rebuild')")
        self.connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        self.connection.commit()

    def _read_schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return SCHEMA_VERSION  # fresh database, no backfill needed
        try:
            return int(row["value"])
        except ValueError:
            return 0

    def _migrate_schema(self) -> None:
        summary_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(summaries)").fetchall()
        }
        if "last_turn_id" not in summary_columns:
            self.connection.execute(
                "ALTER TABLE summaries ADD COLUMN last_turn_id INTEGER NOT NULL DEFAULT 0"
            )
        episode_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(episodes)").fetchall()
        }
        if "tokens" in episode_columns:
            try:
                self.connection.execute("ALTER TABLE episodes DROP COLUMN tokens")
            except sqlite3.OperationalError:
                self._episodes_need_tokens = True

    def create_session(self) -> int:
        cursor = self.connection.execute("INSERT INTO sessions DEFAULT VALUES")
        self.connection.commit()
        return int(cursor.lastrowid)

    def end_session(self, session_id: int) -> None:
        self.connection.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        self.connection.commit()

    def save_turn(self, session_id: int, speaker: str, text: str) -> int:
        cursor = self.connection.execute(
            "INSERT INTO turns(session_id, speaker, text) VALUES (?, ?, ?)",
            (session_id, speaker, text),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def save_turn_pair(self, session_id: int, user_text: str, assistant_text: str) -> int:
        """Save a user/assistant exchange in one transaction; returns the user turn id."""
        cursor = self.connection.execute(
            "INSERT INTO turns(session_id, speaker, text) VALUES (?, 'user', ?)",
            (session_id, user_text),
        )
        user_turn_id = int(cursor.lastrowid)
        self.connection.execute(
            "INSERT INTO turns(session_id, speaker, text) VALUES (?, 'assistant', ?)",
            (session_id, assistant_text),
        )
        self.connection.commit()
        return user_turn_id

    def get_recent_turns(self, limit: int) -> List[ChatMessage]:
        rows = self.connection.execute(
            "SELECT speaker, text FROM turns ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [ChatMessage(role=row["speaker"], content=row["text"]) for row in reversed(rows)]

    def get_latest_summary(self) -> Optional[str]:
        row = self.connection.execute(
            "SELECT summary_text FROM summaries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return None if row is None else str(row["summary_text"])

    def save_summary(self, session_id: int, summary_text: str, turn_count: int, last_turn_id: int = 0) -> None:
        self.connection.execute(
            "INSERT INTO summaries(session_id, summary_text, turn_count, last_turn_id) VALUES (?, ?, ?, ?)",
            (session_id, summary_text, turn_count, last_turn_id),
        )
        self.connection.commit()

    def get_turn_count(self, session_id: int) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["count"])

    def get_max_turn_id(self) -> int:
        row = self.connection.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM turns").fetchone()
        return int(row["max_id"])

    def count_turns_since_last_summary(self) -> int:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM turns
            WHERE id > COALESCE((SELECT MAX(last_turn_id) FROM summaries), 0)
            """
        ).fetchone()
        return int(row["count"])

    def upsert_fact(self, fact: MemoryFact, source_turn_id: Optional[int] = None) -> None:
        self.connection.execute(
            """
            INSERT INTO facts(subject, predicate, value, confidence, source_turn_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(subject, predicate, value)
            DO UPDATE SET
                confidence = excluded.confidence,
                source_turn_id = COALESCE(excluded.source_turn_id, facts.source_turn_id),
                updated_at = CURRENT_TIMESTAMP
            """,
            (fact.subject, fact.predicate, fact.value, fact.confidence, source_turn_id),
        )
        self.connection.commit()

    def get_relevant_facts(self, query: str, limit: int) -> List[MemoryFact]:
        match = _fts_query(query)
        if not match:
            return []
        rows = self.connection.execute(
            """
            SELECT f.subject, f.predicate, f.value, f.confidence
            FROM facts_fts
            JOIN facts f ON f.id = facts_fts.rowid
            WHERE facts_fts MATCH ?
            ORDER BY bm25(facts_fts)
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [
            MemoryFact(
                subject=row["subject"],
                predicate=row["predicate"],
                value=row["value"],
                confidence=float(row["confidence"]),
            )
            for row in rows
        ]

    def build_memory_bundle(
        self,
        query: str,
        recent_turn_limit: int,
        max_fact_hits: int,
        include_summary: bool = True,
        include_facts: bool = True,
        include_episodes: bool = False,
        max_episodic_hits: int = 3,
        episodic_index=None,
    ) -> MemoryBundle:
        episodes: List[EpisodicMemory] = []
        if include_episodes and episodic_index is not None:
            episodes = episodic_index.search(query, max_episodic_hits)
        return MemoryBundle(
            recent_turns=self.get_recent_turns(recent_turn_limit),
            latest_summary=self.get_latest_summary() if include_summary else None,
            facts=self.get_relevant_facts(query=query, limit=max_fact_hits) if include_facts else [],
            episodes=episodes,
        )

    def get_facts(self, limit: int = 20) -> List[Dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT id, subject, predicate, value, confidence, updated_at
            FROM facts
            ORDER BY updated_at DESC, confidence DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_memory_rows(self, limit: int = 12) -> List[Dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT id, session_id, speaker, text, timestamp
            FROM turns
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_summaries(self, limit: int = 5) -> List[Dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT id, session_id, summary_text, turn_count, created_at
            FROM summaries
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_episode(self, *, session_id: int, user_text: str, assistant_text: str) -> int:
        if self._episodes_need_tokens:
            cursor = self.connection.execute(
                "INSERT INTO episodes(session_id, user_text, assistant_text, tokens) VALUES (?, ?, ?, '')",
                (session_id, user_text, assistant_text),
            )
        else:
            cursor = self.connection.execute(
                "INSERT INTO episodes(session_id, user_text, assistant_text) VALUES (?, ?, ?)",
                (session_id, user_text, assistant_text),
            )
        self.connection.commit()
        return int(cursor.lastrowid)

    def search_episodes(self, query: str, limit: int, exclude_latest: int = 3) -> List[EpisodicMemory]:
        match = _fts_query(query)
        if not match:
            return []
        max_id_row = self.connection.execute(
            "SELECT COALESCE(MAX(id), 0) AS max_id FROM episodes"
        ).fetchone()
        cutoff_id = int(max_id_row["max_id"]) - exclude_latest
        rows = self.connection.execute(
            """
            SELECT e.user_text, e.assistant_text, e.created_at,
                   bm25(episodes_fts) AS rank
            FROM episodes_fts
            JOIN episodes e ON e.id = episodes_fts.rowid
            WHERE episodes_fts MATCH ? AND e.id <= ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, cutoff_id, limit),
        ).fetchall()
        # bm25() returns smaller-is-better (negative) ranks; flip the sign so
        # callers get a familiar higher-is-better score.
        return [
            EpisodicMemory(
                user_text=row["user_text"],
                assistant_text=row["assistant_text"],
                created_at=row["created_at"],
                score=-float(row["rank"]),
            )
            for row in rows
        ]

    def export_bundle_dict(self, bundle: MemoryBundle) -> Dict[str, object]:
        return {
            "recent_turns": [asdict(turn) for turn in bundle.recent_turns],
            "latest_summary": bundle.latest_summary,
            "facts": [asdict(fact) for fact in bundle.facts],
            "episodes": [asdict(episode) for episode in bundle.episodes],
        }
