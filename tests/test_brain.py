import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from patch.brain import Brain, MemoryDistiller
from patch.config import AppConfig
from patch.contracts import MemoryFact, ModelProfile, ProviderResponse
from patch.memory.episodic import KeywordEpisodicIndex
from patch.memory.store import SQLiteMemoryStore


class FakeProvider:
    def __init__(self, reply_text: str = "Test reply") -> None:
        self.reply_text = reply_text
        self.captured_profiles = []

    def generate_reply(self, messages, model_profile):
        self.captured_profiles.append(model_profile)
        return ProviderResponse(
            text=self.reply_text,
            prompt_tokens_estimate=12,
            response_tokens_estimate=2,
            raw={"messages": len(messages), "model": model_profile.model},
        )

    def healthcheck(self):
        return True, "ok"

    def list_models(self):
        return ["fake-model"]


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


class MemoryDistillerTests(unittest.TestCase):
    def test_parses_summary_and_fact_lines(self) -> None:
        text = (
            "User is Janis, likes coffee, planning a Pi build.\n"
            "FACT: user | name | Janis\n"
            "FACT: user | likes | coffee\n"
            "FACT: malformed line without pipes\n"
        )
        summary, facts = MemoryDistiller()._parse(text)
        self.assertEqual(summary, "User is Janis, likes coffee, planning a Pi build.")
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0].predicate, "name")
        self.assertEqual(facts[1].value, "coffee")

    def test_fallback_without_provider_returns_no_facts(self) -> None:
        from patch.contracts import ChatMessage

        summary, facts = MemoryDistiller().distill(
            [ChatMessage(role="user", content="hello")],
            previous_summary="Old summary.",
        )
        self.assertIn("Old summary.", summary)
        self.assertEqual(facts, [])


class BrainTests(unittest.TestCase):
    def test_brain_generates_reply(self) -> None:
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
            store.save_turn(session_id, "user", "My name is Janis")
            store.save_turn(session_id, "assistant", "Hello Janis")

            reply, debug_info = brain.generate_reply("I like coffee", config.model_profiles["default"], "fast")
            self.assertEqual(reply, "Test reply")
            self.assertEqual(debug_info["profile"], "default")
            self.assertEqual(debug_info["turn_type"], "memory_related")
            self.assertIn("retrieval_ms", debug_info)
            self.assertIn("prompt_build_ms", debug_info)
            self.assertIn("total_ms", debug_info)
            # memory_bundle export is debug-only.
            self.assertNotIn("memory_bundle", debug_info)
            store.close()

    def test_memory_task_distills_summary_and_facts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            provider = FakeProvider(
                reply_text="Janis likes coffee.\nFACT: user | likes | coffee"
            )
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": provider},
                persona="You are PATCH.",
            )
            session_id = store.create_session()
            user_turn_id = store.save_turn(session_id, "user", "I like coffee")
            store.save_turn(session_id, "assistant", "Nice")

            task = brain.create_memory_task(
                session_id=session_id,
                user_turn_id=user_turn_id,
                user_text="I like coffee",
                assistant_text="Nice",
                active_profile=config.model_profiles["default"],
            )
            timings = brain.process_memory_task(task)
            self.assertEqual(store.get_latest_summary(), "Janis likes coffee.")
            self.assertTrue(any(fact["predicate"] == "likes" for fact in store.get_facts()))
            self.assertEqual(timings["facts_extracted"], 1)
            self.assertIsNotNone(timings["distill_ms"])
            store.close()

    def test_memory_task_skips_distill_below_window(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            provider = FakeProvider()
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": provider},
                persona="You are PATCH.",
            )
            session_id = store.create_session()
            user_turn_id = store.save_turn(session_id, "user", "hi")

            task = brain.create_memory_task(
                session_id=session_id,
                user_turn_id=user_turn_id,
                user_text="hi",
                assistant_text="hello",
                active_profile=config.model_profiles["default"],
            )
            timings = brain.process_memory_task(task)
            self.assertIsNone(timings["distill_ms"])
            self.assertIsNone(store.get_latest_summary())
            self.assertEqual(provider.captured_profiles, [])
            store.close()

    def test_episodic_memory_indexed_and_retrieved(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            config.debug = True
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

    def test_thinking_passes_through_profile_unchanged(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = build_config(tmp_path)
            profile = config.model_profiles["default"]
            profile.options["think"] = False

            provider = FakeProvider()
            store = SQLiteMemoryStore(tmp_path / "patch.db")
            brain = Brain(
                config=config,
                memory_store=store,
                provider_registry={"llama_cpp": provider},
                persona="You are PATCH.",
            )

            brain.generate_reply("hi there", profile, "fast")
            self.assertIs(provider.captured_profiles[0], profile)
            self.assertFalse(provider.captured_profiles[0].options["think"])
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
            store.close()

    def test_long_messages_classified_complex_get_retrieval(self) -> None:
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
            long_text = "could you help me figure out the best way to organize my week around training and work"
            _, debug_info = brain.generate_reply(long_text, config.model_profiles["default"], "fast")
            self.assertEqual(debug_info["turn_type"], "complex")
            self.assertTrue(debug_info["turn_plan"]["include_summary"])
            store.close()


if __name__ == "__main__":
    unittest.main()
