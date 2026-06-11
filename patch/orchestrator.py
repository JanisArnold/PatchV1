from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from pathlib import Path

from patch.adapters.display import NoOpDisplayAdapter
from patch.adapters.text import TextInputAdapter, TextOutputAdapter
from patch.adapters.vision import NoOpVisionAdapter
from patch.background import MemoryMaintenanceWorker
from patch.brain import Brain, render_debug_info
from patch.config import AppConfig
from patch.contracts import DisplayAdapter, ModelProfile, VisionAdapter
from patch.memory.store import SQLiteMemoryStore
from patch.perf import PerfLogger
from patch.streaming import SentenceAssembler
from patch.system_metrics import collect_system_snapshot, render_system_snapshot


class Orchestrator:
    def __init__(
        self,
        *,
        config: AppConfig,
        brain: Brain,
        memory_store: SQLiteMemoryStore,
        input_adapter: TextInputAdapter,
        output_adapter: TextOutputAdapter,
        background_worker: MemoryMaintenanceWorker,
        perf_logger: PerfLogger | None = None,
        idle_event: threading.Event | None = None,
        display_adapter: DisplayAdapter | None = None,
        vision_adapter: VisionAdapter | None = None,
    ) -> None:
        self.config = config
        self.brain = brain
        self.memory_store = memory_store
        self.input_adapter = input_adapter
        self.output_adapter = output_adapter
        self.display_adapter = display_adapter or NoOpDisplayAdapter()
        self.vision_adapter = vision_adapter or NoOpVisionAdapter()
        self.background_worker = background_worker
        self.perf_logger = perf_logger or PerfLogger(config.data_dir / "perf.jsonl")
        self.idle_event = idle_event or threading.Event()
        self.idle_event.set()
        self.debug_enabled = config.debug
        self.active_profile = self._default_profile()
        self.runtime_mode = config.runtime_mode
        self.session_id = self.memory_store.create_session()

    def run(self) -> None:
        self.output_adapter.emit(
            f"{self.config.name} is online. Active profile: {self.active_profile.name}. Runtime mode: {self.runtime_mode}. Type /exit to quit."
        )
        self._emit_state("idle")
        while True:
            try:
                user_text = self.input_adapter.get_input()
            except (EOFError, KeyboardInterrupt):
                self.output_adapter.emit("Shutting down.")
                break

            if not user_text:
                continue
            if user_text.startswith("/"):
                if self._handle_command(user_text):
                    break
                continue

            # handle_text_turn emits the reply itself (streamed or whole).
            self.handle_text_turn(user_text)

        self.memory_store.end_session(self.session_id)

    def close(self) -> None:
        self.background_worker.close()
        self.memory_store.close()

    def handle_text_turn(self, user_text: str, on_sentence=None) -> str | None:
        """Run one turn. The user turn is saved only after generation so the
        current message does not also appear in retrieved recent turns.

        When streaming is enabled, tokens flow to the output adapter as they
        generate, or to ``on_sentence`` sentence-by-sentence (the TTS path).

        While generating, ``idle_event`` is cleared so the background worker
        holds its LLM work instead of competing for the llama-server.
        """
        turn_started = time.perf_counter()
        self._emit_state("thinking")
        self.idle_event.clear()

        streaming = self.config.stream_responses
        assembler = SentenceAssembler() if streaming else None
        stream_state = {"started": False, "first_token_ms": None}

        def handle_token(token: str) -> None:
            if not stream_state["started"]:
                stream_state["started"] = True
                stream_state["first_token_ms"] = int((time.perf_counter() - turn_started) * 1000)
                self._emit_state("speaking")
                if on_sentence is None:
                    self.output_adapter.begin_stream()
            if on_sentence is not None:
                for sentence in assembler.feed(token):
                    on_sentence(sentence)
            else:
                self.output_adapter.emit_token(token)

        try:
            reply, debug_info = self.brain.generate_reply(
                user_text,
                self.active_profile,
                self.runtime_mode,
                on_token=handle_token if streaming else None,
            )
        except RuntimeError as exc:
            if stream_state["started"] and on_sentence is None:
                self.output_adapter.end_stream()
            self._emit_state("error")
            self.output_adapter.emit(f"Model error: {exc}")
            self._emit_state("idle")
            self.idle_event.set()
            return None

        if stream_state["started"]:
            if on_sentence is None:
                self.output_adapter.end_stream()
            else:
                for sentence in assembler.flush():
                    on_sentence(sentence)
        else:
            # Provider did not stream (or streaming disabled): emit whole reply.
            self._emit_state("speaking")
            if on_sentence is not None:
                on_sentence(reply)
            else:
                self.output_adapter.emit(reply)

        user_turn_id = self.memory_store.save_turn_pair(self.session_id, user_text, reply)
        self.idle_event.set()
        self.background_worker.submit(
            self.brain.create_memory_task(
                session_id=self.session_id,
                user_turn_id=user_turn_id,
                user_text=user_text,
                assistant_text=reply,
                active_profile=self.active_profile,
            )
        )
        self.perf_logger.log(
            {
                "phase": "turn",
                "profile": self.active_profile.name,
                "model": self.active_profile.model,
                "runtime_mode": self.runtime_mode,
                "turn_type": debug_info.get("turn_type"),
                "classification_ms": debug_info.get("classification_ms"),
                "retrieval_ms": debug_info.get("retrieval_ms"),
                "prompt_build_ms": debug_info.get("prompt_build_ms"),
                "llm_ms": debug_info.get("latency_ms"),
                "first_token_ms": stream_state["first_token_ms"],
                "total_ms": int((time.perf_counter() - turn_started) * 1000),
                "prompt_tokens": debug_info.get("prompt_tokens_estimate"),
                "response_tokens": debug_info.get("response_tokens_estimate"),
            }
        )
        if self.debug_enabled:
            self.output_adapter.emit(render_debug_info(debug_info))
        self._emit_state("idle")
        return reply

    def _handle_command(self, command_text: str) -> bool:
        command, _, argument = command_text.partition(" ")
        command = command.lower()
        argument = argument.strip()

        if command == "/exit":
            self.output_adapter.emit("Goodbye.")
            return True
        if command == "/help":
            self._show_help()
            return False
        if command == "/models":
            self._show_models()
            return False
        if command == "/mode":
            self._switch_mode(argument)
            return False
        if command == "/use":
            self._switch_profile(argument)
            return False
        if command in {"/reasoning", "/think"}:
            self._toggle_reasoning(argument)
            return False
        if command == "/memory":
            rows = self.memory_store.get_recent_memory_rows()
            self.output_adapter.emit(json.dumps(rows, indent=2, ensure_ascii=True))
            return False
        if command == "/facts":
            facts = self.memory_store.get_facts()
            self.output_adapter.emit(json.dumps(facts, indent=2, ensure_ascii=True))
            return False
        if command == "/summary":
            summaries = self.memory_store.get_recent_summaries()
            self.output_adapter.emit(json.dumps(summaries, indent=2, ensure_ascii=True))
            return False
        if command == "/perf":
            self.output_adapter.emit(json.dumps(self.perf_logger.tail(20), indent=2, ensure_ascii=True))
            return False
        if command == "/system":
            self._show_system()
            return False
        if command == "/debug":
            self._toggle_debug(argument)
            return False
        if command == "/stream":
            self._toggle_streaming(argument)
            return False
        if command == "/episodes":
            if argument:
                episodes = self.memory_store.search_episodes(argument, limit=5)
                payload = [
                    {"user": ep.user_text, "assistant": ep.assistant_text, "at": ep.created_at, "score": ep.score}
                    for ep in episodes
                ]
                self.output_adapter.emit(json.dumps(payload, indent=2, ensure_ascii=True))
            else:
                self.output_adapter.emit("Usage: /episodes <query>")
            return False
        if command == "/benchmark":
            self._run_benchmark()
            return False

        self.output_adapter.emit(f"Unknown command: {command_text}")
        return False

    def _show_models(self) -> None:
        lines = ["Configured profiles:"]
        for name, profile in self.config.model_profiles.items():
            active_marker = " (active)" if name == self.active_profile.name else ""
            extras: list[str] = []
            if profile.model_path:
                extras.append(f"path={profile.model_path}")
            think_value = profile.options.get("think")
            if think_value is not None:
                extras.append(f"think={'on' if bool(think_value) else 'off'}")
            suffix = f" ({', '.join(extras)})" if extras else ""
            lines.append(f"- {name}: {profile.model}{suffix}{active_marker}")

        provider = self.brain.provider_registry[self.active_profile.provider]
        ok, message = provider.healthcheck()
        lines.append("")
        lines.append(f"Runtime mode: {self.runtime_mode}")
        lines.append(f"Provider health: {message}")
        if ok:
            lines.append(f"Available {self.active_profile.provider} models:")
            for model_name in provider.list_models():
                lines.append(f"- {model_name}")
        self.output_adapter.emit("\n".join(lines))

    def _show_help(self) -> None:
        lines = [
            "Available commands:",
            "/help - Show this command list.",
            "/models - List configured profiles and provider-visible models.",
            "/mode [fast|balanced|vision_test] - Show or switch the runtime mode.",
            "/use <profile-or-model> - Switch the active model/profile.",
            "/reasoning on|off - Toggle thinking mode for this session (alias: /think).",
            "/stream on|off - Toggle token streaming output.",
            "/memory - Show recent stored conversation rows.",
            "/facts - Show extracted durable facts.",
            "/episodes <query> - Search episodic memory.",
            "/summary - Show recent rolling summaries.",
            "/perf - Show recent per-turn performance records.",
            "/system - Capture and print a fresh system snapshot.",
            "/debug on|off - Enable or disable debug output.",
            "/benchmark - Run benchmark prompts across configured profiles.",
            "/exit - Exit PATCH cleanly.",
        ]
        self.output_adapter.emit("\n".join(lines))

    def _show_system(self) -> None:
        snapshot = collect_system_snapshot()
        self.perf_logger.log({"phase": "system_snapshot", "source": "manual", **snapshot})
        self.output_adapter.emit(render_system_snapshot(snapshot))

    def _switch_profile(self, argument: str) -> None:
        if not argument:
            self.output_adapter.emit("Usage: /use <profile-or-model>")
            return
        if argument in self.config.model_profiles:
            self.active_profile = self.config.model_profiles[argument]
            self.output_adapter.emit(f"Active profile set to {argument} ({self.active_profile.model}).")
            return
        current = self.active_profile
        self.active_profile = ModelProfile(
            name=f"ad_hoc:{argument}",
            provider=self.config.active_provider,
            model=argument,
            system_prompt=current.system_prompt,
            temperature=current.temperature,
            top_p=current.top_p,
            num_ctx=current.num_ctx,
            options=dict(current.options),
        )
        self.output_adapter.emit(f"Using ad-hoc model {argument} with current profile settings.")

    def _switch_mode(self, argument: str) -> None:
        if not argument:
            self.output_adapter.emit(f"Runtime mode: {self.runtime_mode}")
            return
        if argument not in {"fast", "balanced", "vision_test"}:
            self.output_adapter.emit("Usage: /mode fast|balanced|vision_test")
            return
        self.runtime_mode = argument
        self.output_adapter.emit(f"Runtime mode set to {self.runtime_mode}.")

    def _toggle_debug(self, argument: str) -> None:
        if argument.lower() in {"on", "true", "1"}:
            self.debug_enabled = True
        elif argument.lower() in {"off", "false", "0"}:
            self.debug_enabled = False
        else:
            self.output_adapter.emit("Usage: /debug on|off")
            return
        self.output_adapter.emit(f"Debug mode {'enabled' if self.debug_enabled else 'disabled'}.")

    def _toggle_reasoning(self, argument: str) -> None:
        value = argument.lower()
        if value in {"off", "false", "0", "nothink"}:
            think = False
        elif value in {"on", "true", "1", "think"}:
            think = True
        else:
            self.output_adapter.emit("Usage: /reasoning on|off")
            return
        # Work on a copy so the session toggle never mutates the shared
        # profile object from config; /use <profile> restores the configured value.
        options = dict(self.active_profile.options)
        options["think"] = think
        self.active_profile = replace(self.active_profile, options=options)
        self.output_adapter.emit(
            f"Reasoning {'enabled' if think else 'disabled'} for {self.active_profile.name} ({self.active_profile.model})."
        )

    def _toggle_streaming(self, argument: str) -> None:
        value = argument.lower()
        if value in {"on", "true", "1"}:
            self.config.stream_responses = True
        elif value in {"off", "false", "0"}:
            self.config.stream_responses = False
        else:
            self.output_adapter.emit(f"Streaming is {'on' if self.config.stream_responses else 'off'}. Usage: /stream on|off")
            return
        self.output_adapter.emit(f"Streaming {'enabled' if self.config.stream_responses else 'disabled'}.")

    def _run_benchmark(self) -> None:
        prompt_path = Path(self.config.benchmark_prompt_path)
        prompts = json.loads(prompt_path.read_text(encoding="utf-8"))
        self.output_adapter.emit(f"Running benchmark using {len(prompts)} prompt(s).")
        for profile in self.config.model_profiles.values():
            try:
                results = self.brain.benchmark_profile(profile, prompts)
            except RuntimeError as exc:
                self.output_adapter.emit(f"Benchmark failed for {profile.name}: {exc}")
                continue
            for result in results:
                record = {key: value for key, value in result.items() if key != "reply"}
                self.perf_logger.log({"phase": "benchmark", **record})
            avg_latency = int(sum(item["latency_ms"] for item in results) / max(1, len(results)))
            self.output_adapter.emit(
                f"- {profile.name} ({profile.model}) completed {len(results)} prompt(s), avg latency {avg_latency} ms."
            )
        snapshot = collect_system_snapshot()
        self.perf_logger.log({"phase": "system_snapshot", "source": "benchmark", **snapshot})

    def _default_profile(self) -> ModelProfile:
        if self.config.default_profile in self.config.model_profiles:
            return self.config.model_profiles[self.config.default_profile]
        return next(iter(self.config.model_profiles.values()))

    def _emit_state(self, state: str) -> None:
        self.display_adapter.on_state_change(state)
        if self.debug_enabled:
            self.output_adapter.emit(f"[state] {state}")
