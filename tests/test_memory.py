import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from patch.contracts import MemoryFact
from patch.memory.store import SQLiteMemoryStore


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

    def test_summary_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            store.save_summary(session_id, "User likes coffee.", turn_count=6)

            self.assertEqual(store.get_latest_summary(), "User likes coffee.")
            store.close()


if __name__ == "__main__":
    unittest.main()
