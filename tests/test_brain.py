import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from patch.brain import Brain, RuleBasedFactExtractor
from patch.config import AppConfig
from patch.contracts import MemoryFact, ModelProfile, ProviderResponse
from patch.memory.episodic import KeywordEpisodicIndex
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

    def supports_reasoning_toggle(self, model_profile):
        return False


def build_config(tmp_path: Path) -> AppConfig:
    profile = ModelProfile(
        name="default",
        provider="llama_cpp",
        model="fake-model",
        model_path="models/fake-model.gguf",
        system_prompt="You are PATCH.",
    )
    return AppConfig(
        name="PATCH",
        data_dir=tmp_path,
        benchmark_prompt_path=tmp_path / "benchmarks.json",
        debug=False,
        default_profile="default",
        runtime_mode="fast",
        display_enabled=False,
        camera_enabled=False,
        recent_turn_limit=6,
        max_fact_hits=5,
        summary_turn_window=2,
        max_episodic_hits=3,
        episodic_enabled=True,
        episodic_backend="keyword",
        active_provider="llama_cpp",
        llama_cpp_base_url="http://127.0.0.1:8080",
        llama_cpp_timeout_seconds=30,
        llama_cpp_external_server=True,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_timeout_seconds=30,
        audio_input_device="default",
        audio_output_device="default",
        voice_record_seconds=5,
        stt_engine="whisper_cpp",
        vosk_model_path="stt-models/test-model",
        whisper_cpp_binary="whisper-cli",
        whisper_model_path="stt-models/test-whisper.bin",
        piper_voice_dir="voices",
        piper_voice_name="test-voice",
        model_profiles={"default": profile},
        stream_responses=False,
    )


class BrainTests(unittest.TestCase):
    def test_rule_based_fact_extractor(self) -> None:
        facts = RuleBasedFactExtractor().extract("My name is Janis and I like coffee.", "")
        predicates = {fact.predicate for fact in facts}
        self.assertIn("name", predicates)
        self.assertIn("likes", predicates)

    def test_brain_generates_reply_and_updates_summary(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": FakeProvider()},
                persona="You are PATCH.",
            )
            session_id = store.create_session()
            user_turn_id = store.save_turn(session_id, "user", "My name is Janis")
            store.save_turn(session_id, "assistant", "Hello Janis")

            reply, debug_info = brain.generate_reply("I like coffee", config.model_profiles["default"], "fast")
            self.assertEqual(reply, "Test reply")
            self.assertEqual(debug_info["profile"], "default")
            self.assertEqual(debug_info["turn_type"], "memory_related")
            self.assertIn("retrieval_ms", debug_info)
            self.assertIn("prompt_build_ms", debug_info)
            self.assertIn("total_ms", debug_info)

            task = brain.create_memory_task(
                session_id=session_id,
                user_turn_id=user_turn_id,
                user_text="I like coffee",
                assistant_text="Nice",
                active_profile=config.model_profiles["default"],
            )
            brain.process_memory_task(task)
            self.assertIsNotNone(store.get_latest_summary())
            self.assertTrue(any(fact["predicate"] == "likes" for fact in store.get_facts()))
            store.close()

    def test_benchmark_profile_records_runs_without_reply_column(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": FakeProvider()},
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

    def test_memory_update_records_background_performance_logs(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": FakeProvider()},
                persona="You are PATCH.",
            )
            session_id = store.create_session()
            user_turn_id = store.save_turn(session_id, "user", "I like tea")
            store.save_turn(session_id, "assistant", "Noted.")

            task = brain.create_memory_task(
                session_id=session_id,
                user_turn_id=user_turn_id,
                user_text="I like tea",
                assistant_text="Noted.",
                active_profile=config.model_profiles["default"],
            )
            brain.process_memory_task(task)

            rows = store.get_recent_performance_logs()
            phases = {row["phase"] for row in rows}
            self.assertIn("background.memory.fact_extraction", phases)
            self.assertIn("background.memory.summary", phases)
            store.close()

    def test_episodic_memory_indexed_and_retrieved(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            index = KeywordEpisodicIndex(store)
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": FakeProvider()},
                persona="You are PATCH.",
                episodic_index=index,
            )
            session_id = store.create_session()
            # Old exchange that should be retrievable later.
            index.add(
                user_text="I planted tomatoes in the garden last spring",
                assistant_text="Tomatoes love sun, nice choice.",
                session_id=session_id,
            )
            # Padding so the tomato episode is outside the excluded latest window.
            for i in range(4):
                index.add(user_text=f"filler chat {i}", assistant_text="ok", session_id=session_id)

            episodes = index.search("how are my tomatoes doing in the garden", limit=3)
            self.assertTrue(episodes)
            self.assertIn("tomatoes", episodes[0].user_text)

            _, debug_info = brain.generate_reply(
                "do you remember my garden tomatoes?",
                config.model_profiles["default"],
                "fast",
            )
            self.assertTrue(debug_info["turn_plan"]["include_episodes"])
            self.assertTrue(debug_info["memory_bundle"]["episodes"])
            store.close()

    def test_auto_thinking_resolves_per_turn(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            profile = config.model_profiles["default"]
            profile.options["think"] = "auto"

            captured = {}

            class CapturingProvider(FakeProvider):
                def supports_reasoning_toggle(self, model_profile):
                    return True

                def generate_reply(self, messages, model_profile):
                    captured["think"] = model_profile.options.get("think")
                    return super().generate_reply(messages, model_profile)

            store = SQLiteMemoryStore(tmp_path / "patch.db")
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": CapturingProvider()},
                persona="You are PATCH.",
            )

            brain.generate_reply("hi there", profile, "fast")
            self.assertFalse(captured["think"])

            brain.generate_reply("compare these two architecture designs and analyze why", profile, "fast")
            self.assertTrue(captured["think"])

            # The stored profile itself must keep its "auto" marker.
            self.assertEqual(profile.options["think"], "auto")
            store.close()

    def test_fast_mode_omits_summary_and_facts_for_smalltalk(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            session_id = store.create_session()
            store.save_summary(session_id, "User likes tea.", turn_count=2)
            store.upsert_fact(MemoryFact(subject="user", predicate="likes", value="tea"), source_turn_id=None)
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": FakeProvider()},
                persona="You are PATCH.",
            )

            _, debug_info = brain.generate_reply("hi", config.model_profiles["default"], "fast")

            self.assertEqual(debug_info["turn_type"], "smalltalk")
            self.assertFalse(debug_info["turn_plan"]["include_summary"])
            self.assertFalse(debug_info["turn_plan"]["include_facts"])
            self.assertEqual(debug_info["memory_bundle"]["facts"], [])
            self.assertIsNone(debug_info["memory_bundle"]["latest_summary"])
            store.close()


if __name__ == "__main__":
    unittest.main()
