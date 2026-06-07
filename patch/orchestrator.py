from __future__ import annotations

import json
import time
from pathlib import Path

from patch.adapters.text import TextInputAdapter, TextOutputAdapter
from patch.brain import Brain, render_debug_info
from patch.config import AppConfig
from patch.contracts import ModelProfile
from patch.memory.store import SQLiteMemoryStore
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
    ) -> None:
        self.config = config
        self.brain = brain
        self.memory_store = memory_store
        self.input_adapter = input_adapter
        self.output_adapter = output_adapter
        self.debug_enabled = config.debug
        self.active_profile = self._default_profile()
        self.session_id = self.memory_store.create_session()

    def run(self) -> None:
        self.output_adapter.emit(
            f"{self.config.name} is online. Active profile: {self.active_profile.name}. Type /exit to quit."
        )
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

            turn_started = time.perf_counter()
            user_turn_id = self.memory_store.save_turn(self.session_id, "user", user_text)
            try:
                reply, debug_info = self.brain.generate_reply(user_text, self.active_profile)
            except RuntimeError as exc:
                self.output_adapter.emit(f"Model error: {exc}")
                continue

            self.memory_store.save_turn(self.session_id, "assistant", reply)
            self.brain.update_memory(
                session_id=self.session_id,
                user_turn_id=user_turn_id,
                user_text=user_text,
                assistant_text=reply,
                active_profile=self.active_profile,
            )
            turn_total_ms = int((time.perf_counter() - turn_started) * 1000)
            self.memory_store.record_performance_log(
                session_id=self.session_id,
                phase="turn.total",
                latency_ms=turn_total_ms,
                metadata_json=json.dumps(
                    {
                        "profile": self.active_profile.name,
                        "model": self.active_profile.model,
                        "retrieval_ms": debug_info.get("retrieval_ms"),
                        "prompt_build_ms": debug_info.get("prompt_build_ms"),
                        "llm_ms": debug_info.get("latency_ms"),
                        "total_ms": debug_info.get("total_ms"),
                    }
                ),
            )
            self._record_system_snapshot(source="turn")
            self.output_adapter.emit(reply)
            if self.debug_enabled:
                self.output_adapter.emit(render_debug_info(debug_info))

        self.memory_store.end_session(self.session_id)

    def _handle_command(self, command_text: str) -> bool:
        command, _, argument = command_text.partition(" ")
        command = command.lower()
        argument = argument.strip()

        if command == "/exit":
            self.output_adapter.emit("Goodbye.")
            return True
        if command == "/models":
            self._show_models()
            return False
        if command == "/use":
            self._switch_profile(argument)
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
            self._show_performance()
            return False
        if command == "/system":
            self._show_system()
            return False
        if command == "/debug":
            self._toggle_debug(argument)
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
            lines.append(f"- {name}: {profile.model}{active_marker}")

        provider = self.brain.provider_registry[self.config.active_provider]
        ok, message = provider.healthcheck()
        lines.append("")
        lines.append(f"Provider health: {message}")
        if ok:
            lines.append("Available Ollama models:")
            for model_name in provider.list_models():
                lines.append(f"- {model_name}: {provider.estimate_capabilities(model_name)}")
        self.output_adapter.emit("\n".join(lines))

    def _show_performance(self) -> None:
        logs = self.memory_store.get_recent_performance_logs()
        snapshots = self.memory_store.get_recent_system_snapshots(limit=5)
        payload = {
            "performance_logs": logs,
            "system_snapshots": snapshots,
        }
        self.output_adapter.emit(json.dumps(payload, indent=2, ensure_ascii=True))

    def _show_system(self) -> None:
        snapshot = collect_system_snapshot()
        self.memory_store.record_system_snapshot(
            session_id=self.session_id,
            source="manual",
            temperature_c=snapshot.get("temperature_c"),
            throttled_hex=snapshot.get("throttled_hex"),
            arm_clock_hz=snapshot.get("arm_clock_hz"),
            metadata_json=json.dumps(snapshot),
        )
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

    def _toggle_debug(self, argument: str) -> None:
        if argument.lower() in {"on", "true", "1"}:
            self.debug_enabled = True
        elif argument.lower() in {"off", "false", "0"}:
            self.debug_enabled = False
        else:
            self.output_adapter.emit("Usage: /debug on|off")
            return
        self.output_adapter.emit(f"Debug mode {'enabled' if self.debug_enabled else 'disabled'}.")

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
            avg_latency = int(sum(item["latency_ms"] for item in results) / max(1, len(results)))
            self.output_adapter.emit(
                f"- {profile.name} ({profile.model}) completed {len(results)} prompt(s), avg latency {avg_latency} ms."
            )
        self._record_system_snapshot(source="benchmark")

    def _default_profile(self) -> ModelProfile:
        if self.config.default_profile in self.config.model_profiles:
            return self.config.model_profiles[self.config.default_profile]
        return next(iter(self.config.model_profiles.values()))

    def _record_system_snapshot(self, source: str) -> None:
        snapshot = collect_system_snapshot()
        self.memory_store.record_system_snapshot(
            session_id=self.session_id,
            source=source,
            temperature_c=snapshot.get("temperature_c"),
            throttled_hex=snapshot.get("throttled_hex"),
            arm_clock_hz=snapshot.get("arm_clock_hz"),
            metadata_json=json.dumps(snapshot),
        )
