from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from typing import Callable, Dict, List, Optional

from patch.config import AppConfig
from patch.contracts import ChatMessage, MemoryFact, MemoryTask, ModelProfile, ProviderResponse, TurnPlan
from patch.memory.store import SQLiteMemoryStore


class RuleBasedFactExtractor:
    PATTERNS = [
        (re.compile(r"\bmy name is ([A-Za-z][A-Za-z0-9_-]+)", re.IGNORECASE), "name"),
        (re.compile(r"\bi live in ([A-Za-z][A-Za-z ,'-]+)", re.IGNORECASE), "location"),
        (re.compile(r"\bi like ([A-Za-z0-9 ,'-]+)", re.IGNORECASE), "likes"),
        (re.compile(r"\bmy favorite ([A-Za-z ]+) is ([A-Za-z0-9 ,'-]+)", re.IGNORECASE), "favorite"),
        (re.compile(r"\bi work as ([A-Za-z0-9 ,'-]+)", re.IGNORECASE), "occupation"),
    ]

    def extract(self, user_text: str, assistant_text: str) -> List[MemoryFact]:
        del assistant_text
        facts: List[MemoryFact] = []
        for pattern, predicate in self.PATTERNS:
            match = pattern.search(user_text)
            if not match:
                continue
            if predicate == "favorite":
                key = match.group(1).strip().lower().replace(" ", "_")
                value = match.group(2).strip()
                facts.append(MemoryFact(subject="user", predicate=f"favorite_{key}", value=value, confidence=0.85))
            else:
                facts.append(
                    MemoryFact(
                        subject="user",
                        predicate=predicate,
                        value=match.group(1).strip().rstrip(".!?"),
                        confidence=0.8,
                    )
                )
        return facts


class SummaryService:
    def __init__(self, fallback_limit: int = 8) -> None:
        self.fallback_limit = fallback_limit

    def summarize(
        self,
        turns: List[ChatMessage],
        previous_summary: Optional[str] = None,
        provider=None,
        profile: Optional[ModelProfile] = None,
    ) -> str:
        if provider is not None and profile is not None:
            prompt = self._build_prompt(turns, previous_summary)
            try:
                response = provider.generate_reply(prompt, profile)
                if response.text:
                    return response.text.strip()
            except RuntimeError:
                pass
        snippets = [f"{turn.role}: {turn.content}" for turn in turns[-self.fallback_limit :]]
        if previous_summary:
            return f"{previous_summary}\nRecent updates: " + " | ".join(snippets)
        return "Recent updates: " + " | ".join(snippets)

    def _build_prompt(self, turns: List[ChatMessage], previous_summary: Optional[str]) -> List[ChatMessage]:
        transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
        content = (
            "Create a compact rolling memory summary of the conversation. "
            "Keep names, preferences, ongoing goals, and unresolved threads.\n\n"
        )
        if previous_summary:
            content += f"Previous summary:\n{previous_summary}\n\n"
        content += f"New transcript:\n{transcript}\n\nReturn only the updated summary."
        return [ChatMessage(role="system", content="You create compact memory summaries."), ChatMessage(role="user", content=content)]


class Brain:
    def __init__(
        self,
        *,
        config: AppConfig,
        memory_store: SQLiteMemoryStore,
        provider_registry: Dict[str, object],
        persona: str,
        episodic_index=None,
    ) -> None:
        self.config = config
        self.memory_store = memory_store
        self.provider_registry = provider_registry
        self.persona = persona
        self.episodic_index = episodic_index
        self.fact_extractor = RuleBasedFactExtractor()
        self.summary_service = SummaryService()

    def classify_turn(self, user_text: str) -> str:
        lowered = user_text.lower()
        vision_keywords = ("what do you see", "look at", "camera", "image", "photo", "scene")
        memory_keywords = ("remember", "what do you know", "what did i say", "my ", "i like", "i prefer", "my name")
        complex_keywords = ("plan", "design", "compare", "analyze", "why", "how should", "architecture")
        if any(keyword in lowered for keyword in vision_keywords):
            return "vision_requested"
        if any(keyword in lowered for keyword in memory_keywords):
            return "memory_related"
        if any(keyword in lowered for keyword in complex_keywords):
            return "complex"
        return "smalltalk"

    def build_turn_plan(self, user_text: str, runtime_mode: str) -> tuple[TurnPlan, int]:
        started = time.perf_counter()
        turn_type = self.classify_turn(user_text)
        # Spec rule: thinking mode burns tokens, so it stays off for casual
        # chat and only turns on for genuinely complex turns.
        think = True if turn_type == "complex" else False
        if runtime_mode == "fast":
            if turn_type == "smalltalk":
                plan = TurnPlan(
                    turn_type=turn_type, recent_turn_limit=3,
                    include_summary=False, include_facts=False,
                    include_episodes=False, think=think,
                )
            else:
                plan = TurnPlan(
                    turn_type=turn_type, recent_turn_limit=4,
                    include_summary=True, include_facts=True,
                    include_episodes=True, think=think,
                )
        elif runtime_mode == "vision_test":
            plan = TurnPlan(
                turn_type=turn_type, recent_turn_limit=5,
                include_summary=True, include_facts=True,
                include_episodes=True, think=think,
            )
        else:
            if turn_type == "smalltalk":
                plan = TurnPlan(
                    turn_type=turn_type, recent_turn_limit=4,
                    include_summary=False, include_facts=False,
                    include_episodes=False, think=think,
                )
            else:
                plan = TurnPlan(
                    turn_type=turn_type, recent_turn_limit=6,
                    include_summary=True, include_facts=True,
                    include_episodes=True, think=think,
                )
        classification_ms = int((time.perf_counter() - started) * 1000)
        return plan, classification_ms

    def generate_reply(
        self,
        user_text: str,
        profile: ModelProfile,
        runtime_mode: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> tuple:
        started_total = time.perf_counter()
        turn_plan, classification_ms = self.build_turn_plan(user_text, runtime_mode)
        retrieval_started = time.perf_counter()
        bundle = self.memory_store.build_memory_bundle(
            query=user_text,
            recent_turn_limit=min(turn_plan.recent_turn_limit, self.config.recent_turn_limit),
            max_fact_hits=self.config.max_fact_hits,
            include_summary=turn_plan.include_summary,
            include_facts=turn_plan.include_facts,
            include_episodes=turn_plan.include_episodes and self.config.episodic_enabled,
            max_episodic_hits=self.config.max_episodic_hits,
            episodic_index=self.episodic_index,
        )
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)
        prompt_started = time.perf_counter()
        messages = self._build_messages(user_text, profile, bundle)
        prompt_build_ms = int((time.perf_counter() - prompt_started) * 1000)
        provider = self.provider_registry[profile.provider]
        effective_profile = self._apply_turn_thinking(profile, turn_plan, provider)
        started = time.perf_counter()
        if on_token is not None and hasattr(provider, "generate_stream"):
            response: ProviderResponse = provider.generate_stream(messages, effective_profile, on_token)
        else:
            response = provider.generate_reply(messages, effective_profile)
        latency_ms = int((time.perf_counter() - started) * 1000)
        total_ms = int((time.perf_counter() - started_total) * 1000)
        debug_info: Dict[str, object] = {
            "memory_bundle": self.memory_store.export_bundle_dict(bundle),
            "prompt_tokens_estimate": response.prompt_tokens_estimate,
            "response_tokens_estimate": response.response_tokens_estimate,
            "latency_ms": latency_ms,
            "classification_ms": classification_ms,
            "retrieval_ms": retrieval_ms,
            "prompt_build_ms": prompt_build_ms,
            "total_ms": total_ms,
            "profile": profile.name,
            "model": profile.model,
            "runtime_mode": runtime_mode,
            "turn_type": turn_plan.turn_type,
            "turn_plan": {
                "recent_turn_limit": turn_plan.recent_turn_limit,
                "include_summary": turn_plan.include_summary,
                "include_facts": turn_plan.include_facts,
                "include_episodes": turn_plan.include_episodes,
                "think": turn_plan.think,
            },
        }
        return response.text, debug_info

    def _apply_turn_thinking(self, profile: ModelProfile, turn_plan: TurnPlan, provider) -> ModelProfile:
        """Resolve a per-turn thinking override when the profile uses think="auto"."""
        if profile.options.get("think") != "auto" or turn_plan.think is None:
            return profile
        if not provider.supports_reasoning_toggle(profile):
            return profile
        options = dict(profile.options)
        options["think"] = turn_plan.think
        return replace(profile, options=options)

    def create_memory_task(
        self,
        *,
        session_id: int,
        user_turn_id: int,
        user_text: str,
        assistant_text: str,
        active_profile: ModelProfile,
    ) -> MemoryTask:
        return MemoryTask(
            session_id=session_id,
            user_turn_id=user_turn_id,
            user_text=user_text,
            assistant_text=assistant_text,
            active_profile_name=active_profile.name,
        )

    def process_memory_task(self, task: MemoryTask) -> None:
        active_profile = self.config.model_profiles.get(task.active_profile_name)
        if active_profile is None:
            active_profile = next(iter(self.config.model_profiles.values()))
        fact_started = time.perf_counter()
        for fact in self.fact_extractor.extract(task.user_text, task.assistant_text):
            self.memory_store.upsert_fact(fact, source_turn_id=task.user_turn_id)
        fact_extraction_ms = int((time.perf_counter() - fact_started) * 1000)
        self.memory_store.record_performance_log(
            session_id=task.session_id,
            phase="background.memory.fact_extraction",
            latency_ms=fact_extraction_ms,
            metadata_json=json.dumps({"profile": active_profile.name}),
        )

        if self.episodic_index is not None:
            episodic_started = time.perf_counter()
            self.episodic_index.add(
                user_text=task.user_text,
                assistant_text=task.assistant_text,
                session_id=task.session_id,
            )
            episodic_ms = int((time.perf_counter() - episodic_started) * 1000)
            self.memory_store.record_performance_log(
                session_id=task.session_id,
                phase="background.memory.episodic_index",
                latency_ms=episodic_ms,
                metadata_json=json.dumps({"backend": self.config.episodic_backend}),
            )

        turns_since_summary = self.memory_store.count_turns_since_last_summary()
        if turns_since_summary < self.config.summary_turn_window:
            return

        total_turns = self.memory_store.get_turn_count(task.session_id)
        summary_started = time.perf_counter()
        turns = self.memory_store.get_recent_turns(limit=self.config.summary_turn_window)
        previous_summary = self.memory_store.get_latest_summary()
        summary_profile = self.config.model_profiles.get("memory_extraction", active_profile)
        summary_provider = self.provider_registry.get(summary_profile.provider)
        summary_text = self.summary_service.summarize(
            turns,
            previous_summary=previous_summary,
            provider=summary_provider,
            profile=summary_profile,
        )
        self.memory_store.save_summary(
            session_id=task.session_id,
            summary_text=summary_text,
            turn_count=total_turns,
            last_turn_id=self.memory_store.get_max_turn_id(),
        )
        summary_ms = int((time.perf_counter() - summary_started) * 1000)
        self.memory_store.record_performance_log(
            session_id=task.session_id,
            phase="background.memory.summary",
            latency_ms=summary_ms,
            metadata_json=json.dumps(
                {
                    "profile": active_profile.name,
                    "summary_profile": summary_profile.name,
                    "turn_count": total_turns,
                }
            ),
        )

    def _build_messages(self, user_text: str, profile: ModelProfile, bundle) -> List[ChatMessage]:
        system_parts = [self.persona.strip(), profile.system_prompt.strip()]
        if bundle.latest_summary:
            system_parts.append(f"Conversation summary:\n{bundle.latest_summary}")
        if bundle.facts:
            fact_lines = [f"- {fact.subject} {fact.predicate}: {fact.value}" for fact in bundle.facts]
            system_parts.append("Relevant remembered facts:\n" + "\n".join(fact_lines))
        if bundle.episodes:
            episode_lines = [
                f"- [{episode.created_at}] user said: {episode.user_text} / you replied: {episode.assistant_text}"
                for episode in bundle.episodes
            ]
            system_parts.append("Relevant past exchanges:\n" + "\n".join(episode_lines))
        messages = [ChatMessage(role="system", content="\n\n".join(part for part in system_parts if part))]
        messages.extend(bundle.recent_turns)
        messages.append(ChatMessage(role="user", content=user_text))
        return messages

    def benchmark_profile(self, profile: ModelProfile, prompts: List[Dict[str, str]]) -> List[Dict[str, object]]:
        provider = self.provider_registry[profile.provider]
        results: List[Dict[str, object]] = []
        for prompt in prompts:
            messages = [
                ChatMessage(role="system", content=self.persona),
                ChatMessage(role="user", content=prompt["prompt"]),
            ]
            started = time.perf_counter()
            response = provider.generate_reply(messages, profile)
            latency_ms = int((time.perf_counter() - started) * 1000)
            result = {
                "prompt_name": prompt["name"],
                "profile_name": profile.name,
                "provider": profile.provider,
                "model_name": profile.model,
                "prompt_size": response.prompt_tokens_estimate,
                "response_size": response.response_tokens_estimate,
                "latency_ms": latency_ms,
                "reply": response.text,
            }
            self.memory_store.record_model_run(
                run_type="benchmark",
                profile_name=result["profile_name"],
                provider=result["provider"],
                model_name=result["model_name"],
                prompt_name=result["prompt_name"],
                prompt_size=result["prompt_size"],
                response_size=result["response_size"],
                latency_ms=result["latency_ms"],
                notes=None,
            )
            results.append(result)
        return results


def render_debug_info(debug_info: Dict[str, object]) -> str:
    return json.dumps(debug_info, indent=2, ensure_ascii=True)
