import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from patch.contracts import MemoryFact
from patch.memory.store import SQLiteMemoryStore
from patch.perf import PerfLogger


class MemoryStoreTests(unittest.TestCase):
    def test_memory_store_persists_turns_and_facts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            turn_id = store.save_turn(session_id, "user", "My name is Janis")
            store.save_turn(session_id, "assistant", "Nice to meet you.")
            store.upsert_fact(MemoryFact(subject="user", predicate="name", value="Janis", confidence=0.9), turn_id)

            bundle = store.build_memory_bundle("Janis", recent_turn_limit=4, max_fact_hits=3)

            self.assertEqual(len(bundle.recent_turns), 2)
            self.assertEqual(bundle.facts[0].value, "Janis")
            store.close()

    def test_save_turn_pair_returns_user_turn_id(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            user_turn_id = store.save_turn_pair(session_id, "hello", "hi there")

            turns = store.get_recent_turns(limit=2)
            self.assertEqual(turns[0].role, "user")
            self.assertEqual(turns[1].role, "assistant")
            self.assertEqual(user_turn_id + 1, store.get_max_turn_id())
            store.close()

    def test_summary_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            store.save_summary(session_id, "User likes coffee.", turn_count=6, last_turn_id=6)

            self.assertEqual(store.get_latest_summary(), "User likes coffee.")
            store.close()

    def test_fact_relevance_prefers_matching_tokens(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            store.upsert_fact(MemoryFact(subject="user", predicate="name", value="Janis", confidence=0.9))
            store.upsert_fact(MemoryFact(subject="user", predicate="likes", value="hiking in the alps", confidence=0.8))
            store.upsert_fact(MemoryFact(subject="user", predicate="favorite_drink", value="espresso", confidence=0.8))

            facts = store.get_relevant_facts("should I go hiking this weekend?", limit=1)

            self.assertEqual(facts[0].predicate, "likes")
            store.close()

    def test_fact_upsert_keeps_fts_in_sync(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            fact = MemoryFact(subject="user", predicate="likes", value="climbing", confidence=0.6)
            store.upsert_fact(fact)
            store.upsert_fact(MemoryFact(subject="user", predicate="likes", value="climbing", confidence=0.9))

            facts = store.get_relevant_facts("climbing", limit=5)
            self.assertEqual(len(facts), 1)
            self.assertAlmostEqual(facts[0].confidence, 0.9)
            store.close()

    def test_count_turns_since_last_summary(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            store.save_turn(session_id, "user", "one")
            last_id = store.save_turn(session_id, "assistant", "two")
            store.save_summary(session_id, "summary", turn_count=2, last_turn_id=last_id)
            store.save_turn(session_id, "user", "three")

            self.assertEqual(store.count_turns_since_last_summary(), 1)
            store.close()

    def test_episode_search_excludes_latest_and_ranks_matches(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            store.add_episode(session_id=session_id, user_text="my dog is called Rex", assistant_text="Rex is a great name")
            for i in range(3):
                store.add_episode(session_id=session_id, user_text=f"filler {i}", assistant_text="ok")

            episodes = store.search_episodes("what is my dog called", limit=3)
            self.assertEqual(len(episodes), 1)
            self.assertIn("Rex", episodes[0].user_text)

            # The three filler episodes are the latest ones and stay excluded.
            filler = store.search_episodes("filler", limit=3)
            self.assertEqual(filler, [])
            store.close()

    def test_fts_query_handles_special_characters(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            # Must not raise an FTS5 syntax error.
            self.assertEqual(store.get_relevant_facts('what about "quotes" AND (parens)?', limit=3), [])
            self.assertEqual(store.search_episodes("***", limit=3), [])
            store.close()


class PerfLoggerTests(unittest.TestCase):
    def test_log_and_tail_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            logger = PerfLogger(Path(tmp_dir) / "perf.jsonl")
            for i in range(5):
                logger.log({"phase": "turn", "total_ms": i})

            records = logger.tail(limit=3)
            self.assertEqual(len(records), 3)
            self.assertEqual(records[-1]["total_ms"], 4)
            self.assertIn("ts", records[0])

    def test_tail_on_missing_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            logger = PerfLogger(Path(tmp_dir) / "missing.jsonl")
            self.assertEqual(logger.tail(), [])

    def test_tail_skips_corrupt_lines(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "perf.jsonl"
            logger = PerfLogger(path)
            logger.log({"phase": "turn"})
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("not json\n")
            logger.log({"phase": "turn"})

            records = logger.tail()
            self.assertEqual(len(records), 2)


class MigrationTests(unittest.TestCase):
    def test_opens_v2_database_and_backfills_fts(self) -> None:
        import sqlite3

        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "patch.db"
            # Minimal v2-style database: episodes with tokens column, no FTS.
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES ('schema_version', '2');
                CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ended_at TEXT);
                CREATE TABLE turns (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE summaries (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER, summary_text TEXT NOT NULL, turn_count INTEGER NOT NULL,
                    last_turn_id INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE episodes (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER, user_text TEXT NOT NULL, assistant_text TEXT NOT NULL,
                    tokens TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO episodes (session_id, user_text, assistant_text, tokens)
                    VALUES (1, 'I planted tomatoes', 'nice', 'planted tomatoes');
                CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL,
                    confidence REAL NOT NULL, source_turn_id INTEGER,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(subject, predicate, value));
                INSERT INTO facts (subject, predicate, value, confidence)
                    VALUES ('user', 'likes', 'tomatoes', 0.8);
                """
            )
            connection.commit()
            connection.close()

            store = SQLiteMemoryStore(db_path)
            # Old rows must be searchable through the new FTS index.
            facts = store.get_relevant_facts("tomatoes", limit=3)
            self.assertEqual(len(facts), 1)
            episodes = store.search_episodes("tomatoes", limit=3, exclude_latest=0)
            self.assertEqual(len(episodes), 1)
            # And new inserts must work regardless of the legacy tokens column.
            store.add_episode(session_id=1, user_text="new episode about hiking", assistant_text="ok")
            store.close()


if __name__ == "__main__":
    unittest.main()
