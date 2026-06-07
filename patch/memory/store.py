from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from patch.contracts import ChatMessage, MemoryBundle, MemoryFact


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

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    prompt_name TEXT,
    prompt_size INTEGER NOT NULL,
    response_size INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS performance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    phase TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS system_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    source TEXT NOT NULL,
    temperature_c REAL,
    throttled_hex TEXT,
    arm_clock_hz INTEGER,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
"""


class SQLiteMemoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.connection.close()

    def _ensure_schema(self) -> None:
        self.connection.executescript(SCHEMA)
        self.connection.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
        self.connection.commit()

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

    def save_summary(self, session_id: int, summary_text: str, turn_count: int) -> None:
        self.connection.execute(
            "INSERT INTO summaries(session_id, summary_text, turn_count) VALUES (?, ?, ?)",
            (session_id, summary_text, turn_count),
        )
        self.connection.commit()

    def get_turn_count(self, session_id: int) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM turns WHERE session_id = ?",
            (session_id,),
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
        like = f"%{query.lower()}%"
        rows = self.connection.execute(
            """
            SELECT subject, predicate, value, confidence
            FROM facts
            WHERE LOWER(subject || ' ' || predicate || ' ' || value) LIKE ?
            ORDER BY updated_at DESC, confidence DESC
            LIMIT ?
            """,
            (like, limit),
        ).fetchall()
        if rows:
            return [
                MemoryFact(
                    subject=row["subject"],
                    predicate=row["predicate"],
                    value=row["value"],
                    confidence=float(row["confidence"]),
                )
                for row in rows
            ]
        fallback = self.connection.execute(
            """
            SELECT subject, predicate, value, confidence
            FROM facts
            ORDER BY updated_at DESC, confidence DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            MemoryFact(
                subject=row["subject"],
                predicate=row["predicate"],
                value=row["value"],
                confidence=float(row["confidence"]),
            )
            for row in fallback
        ]

    def build_memory_bundle(
        self,
        query: str,
        recent_turn_limit: int,
        max_fact_hits: int,
        include_summary: bool = True,
        include_facts: bool = True,
    ) -> MemoryBundle:
        return MemoryBundle(
            recent_turns=self.get_recent_turns(recent_turn_limit),
            latest_summary=self.get_latest_summary() if include_summary else None,
            facts=self.get_relevant_facts(query=query, limit=max_fact_hits) if include_facts else [],
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

    def record_model_run(
        self,
        *,
        run_type: str,
        profile_name: str,
        provider: str,
        model_name: str,
        prompt_name: Optional[str],
        prompt_size: int,
        response_size: int,
        latency_ms: int,
        notes: Optional[str] = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO model_runs(
                run_type, profile_name, provider, model_name, prompt_name,
                prompt_size, response_size, latency_ms, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_type,
                profile_name,
                provider,
                model_name,
                prompt_name,
                prompt_size,
                response_size,
                latency_ms,
                notes,
            ),
        )
        self.connection.commit()

    def record_performance_log(
        self,
        *,
        session_id: Optional[int],
        phase: str,
        latency_ms: int,
        metadata_json: Optional[str] = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO performance_logs(session_id, phase, latency_ms, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, phase, latency_ms, metadata_json),
        )
        self.connection.commit()

    def record_system_snapshot(
        self,
        *,
        session_id: Optional[int],
        source: str,
        temperature_c: Optional[float],
        throttled_hex: Optional[str],
        arm_clock_hz: Optional[int],
        metadata_json: Optional[str] = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO system_snapshots(
                session_id, source, temperature_c, throttled_hex, arm_clock_hz, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, source, temperature_c, throttled_hex, arm_clock_hz, metadata_json),
        )
        self.connection.commit()

    def get_recent_performance_logs(self, limit: int = 20) -> List[Dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT id, session_id, phase, latency_ms, metadata_json, created_at
            FROM performance_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_system_snapshots(self, limit: int = 10) -> List[Dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT id, session_id, source, temperature_c, throttled_hex, arm_clock_hz, metadata_json, created_at
            FROM system_snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_turns_since_last_summary(self, session_id: int) -> int:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM turns
            WHERE session_id = ?
              AND id > COALESCE(
                  (SELECT MAX(id) FROM turns WHERE id <= (
                      SELECT COALESCE(MAX(turn_count), 0) FROM summaries WHERE session_id = ?
                  )),
                  0
              )
            """,
            (session_id, session_id),
        ).fetchone()
        return int(row["count"])

    def export_bundle_dict(self, bundle: MemoryBundle) -> Dict[str, object]:
        return {
            "recent_turns": [asdict(turn) for turn in bundle.recent_turns],
            "latest_summary": bundle.latest_summary,
            "facts": [asdict(fact) for fact in bundle.facts],
        }
