import unittest
from pathlib import Path

from patch.brain import Brain, RuleBasedFactExtractor
from patch.config import AppConfig
from patch.contracts import ModelProfile, ProviderResponse
from patch.memory.store import SQLiteMemoryStore


class FakeProvider:
    def generate_reply(self, messages, model_profile):
        return ProviderResponse(
            text="Test reply",
            prompt_tokens_estimate=12,
            response_tokens_estimate=2,
            raw={"messages": len(messages), "model": model_profile.model},
        )

    def healthcheck(self):
        return True, "ok"

    def list_models(self):
        return ["fake-model"]

    def estimate_capabilities(self, model_name):
        return "fake"


def build_config(tmp_path: Path) -> AppConfig:
    profile = ModelProfile(
        name="default",
        provider="ollama",
        model="fake-model",
        system_prompt="You are PATCH.",
    )
    return AppConfig(
        name="PATCH",
        data_dir=tmp_path,
        benchmark_prompt_path=tmp_path / "benchmarks.json",
        debug=False,
        default_profile="default",
        recent_turn_limit=6,
        max_fact_hits=5,
        summary_turn_window=2,
        active_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_timeout_seconds=30,
        model_profiles={"default": profile},
    )


class BrainTests(unittest.TestCase):
    def test_rule_based_fact_extractor(self) -> None:
        facts = RuleBasedFactExtractor().extract("My name is Janis and I like coffee.", "")
        predicates = {fact.predicate for fact in facts}
        self.assertIn("name", predicates)
        self.assertIn("likes", predicates)

    def test_brain_generates_reply_and_updates_summary(self) -> None:
        tmp_path = Path(self._testMethodName)
        tmp_path.mkdir(exist_ok=True)
        config = build_config(tmp_path)
        store = SQLiteMemoryStore(tmp_path / "patch.db")
        brain = Brain(
            config=config,
            memory_store=store,
            provider_registry={"ollama": FakeProvider()},
            persona="You are PATCH.",
        )
        session_id = store.create_session()
        user_turn_id = store.save_turn(session_id, "user", "My name is Janis")
        store.save_turn(session_id, "assistant", "Hello Janis")

        reply, debug_info = brain.generate_reply("I like coffee", config.model_profiles["default"])
        self.assertEqual(reply, "Test reply")
        self.assertEqual(debug_info["profile"], "default")

        brain.update_memory(
            session_id=session_id,
            user_turn_id=user_turn_id,
            user_text="I like coffee",
            assistant_text="Nice",
            active_profile=config.model_profiles["default"],
        )
        self.assertIsNotNone(store.get_latest_summary())
        self.assertTrue(any(fact["predicate"] == "likes" for fact in store.get_facts()))
        store.close()

    def test_benchmark_profile_records_runs_without_reply_column(self) -> None:
        tmp_path = Path(f"{self._testMethodName}_data")
        tmp_path.mkdir(exist_ok=True)
        config = build_config(tmp_path)
        store = SQLiteMemoryStore(tmp_path / "patch.db")
        brain = Brain(
            config=config,
            memory_store=store,
            provider_registry={"ollama": FakeProvider()},
            persona="You are PATCH.",
        )

        results = brain.benchmark_profile(
            config.model_profiles["default"],
            [{"name": "smoke", "prompt": "Say hello."}],
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["reply"], "Test reply")
        rows = store.connection.execute(
            "SELECT profile_name, model_name, prompt_name FROM model_runs"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prompt_name"], "smoke")
        store.close()


if __name__ == "__main__":
    unittest.main()
