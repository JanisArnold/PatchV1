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

    def test_episode_search_excludes_latest_and_scores_overlap(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
