from __future__ import annotations

import json
import time
from typing import Callable, Dict, List, Optional, Tuple

from patch.config import AppConfig
from patch.contracts import ChatMessage, MemoryFact, MemoryTask, ModelProfile, ProviderResponse, TurnPlan
from patch.memory.store import SQLiteMemoryStore


class MemoryDistiller:
    """One background LLM call that updates the rolling summary AND extracts
    durable facts. Folding both into a single prompt halves the background
    load on the shared llama-server, and the LLM extracts far cleaner facts
    than the old regex patterns ever did.
    """

    FACT_PREFIX = "FACT:"

    def __init__(self, fallback_limit: int = 8) -> None:
        self.fallback_limit = fallback_limit

    def distill(
        self,
        turns: List[ChatMessage],
        previous_summary: Optional[str] = None,
        provider=None,
        profile: Optional[ModelProfile] = None,
    ) -> Tuple[str, List[MemoryFact]]:
        if provider is not None and profile is not None:
            prompt = self._build_prompt(turns, previous_summary)
            try:
                response = provider.generate_reply(prompt, profile)
                if response.text:
                    return self._parse(response.text)
            except RuntimeError:
                pass
        snippets = [f"{turn.role}: {turn.content}" for turn in turns[-self.fallback_limit :]]
        if previous_summary:
            return f"{previous_summary}\nRecent updates: " + " | ".join(snippets), []
        return "Recent updates: " + " | ".join(snippets), []

    def _build_prompt(self, turns: List[ChatMessage], previous_summary: Optional[str]) -> List[ChatMessage]:
        transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
        content = (
            "Update the rolling memory summary of this conversation. "
            "Keep names, preferences, ongoing goals, and unresolved threads.\n\n"
        )
        if previous_summary:
            content += f"Previous summary:\n{previous_summary}\n\n"
        content += (
            f"New transcript:\n{transcript}\n\n"
            "Return the updated summary first. Then list durable facts about the "
            "user worth remembering long-term (names, preferences, places, goals), "
            "one per line, exactly in this form:\n"
            "FACT: subject | predicate | value\n"
            "Only list facts actually stated. If there are none, list none."
        )
        return [
            ChatMessage(role="system", content="You maintain compact long-term memory for an assistant."),
            ChatMessage(role="user", content=content),
        ]

    def _parse(self, text: str) -> Tuple[str, List[MemoryFact]]:
        summary_lines: List[str] = []
        facts: List[MemoryFact] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith(self.FACT_PREFIX):
                parts = [part.strip() for part in stripped[len(self.FACT_PREFIX):].split("|")]
                if len(parts) == 3 and all(parts):
                    facts.append(
                        MemoryFact(
                            subject=parts[0].lower(),
                            predicate=parts[1].lower().replace(" ", "_"),
                            value=parts[2],
                            confidence=0.7,
                        )
                    )
            else:
                summary_lines.append(line)
        summary = "\n".join(summary_lines).strip()
        return summary, facts


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
        self.distiller = MemoryDistiller()

    def classify_turn(self, user_text: str) -> str:
        """Decide how much memory to retrieve. This no longer controls
        thinking: on Pi-class hardware reasoning tokens cost more when the
        heuristic is wrong than they gain when it is right, so thinking is a
        profile/command setting only."""
        lowered = user_text.lower()
        vision_keywords = ("what do you see", "look at", "camera", "image", "photo", "scene")
        memory_keywords = ("remember", "what do you know", "what did i say", "my name", "i like", "i prefer")
        if any(keyword in lowered for keyword in vision_keywords):
            return "vision_requested"
        if any(keyword in lowered for keyword in memory_keywords):
            return "memory_related"
        if len(tokenize_words(user_text)) > 12:
            return "complex"
        return "smalltalk"

    def build_turn_plan(self, user_text: str, runtime_mode: str) -> tuple:
        started = time.perf_counter()
        turn_type = self.classify_turn(user_text)
        if turn_type == "smalltalk":
            plan = TurnPlan(
                turn_type=turn_type,
                recent_turn_limit=3 if runtime_mode == "fast" else 4,
                include_summary=False, include_facts=False,
                include_episodes=False,
            )
        else:
            plan = TurnPlan(
                turn_type=turn_type,
                recent_turn_limit=4 if runtime_mode == "fast" else 6,
                include_summary=True, include_facts=True,
                include_episodes=True,
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
        started = time.perf_counter()
        if on_token is not None and hasattr(provider, "generate_stream"):
            response: ProviderResponse = provider.generate_stream(messages, profile, on_token)
        else:
            response = provider.generate_reply(messages, profile)
        latency_ms = int((time.perf_counter() - started) * 1000)
        total_ms = int((time.perf_counter() - started_total) * 1000)
        debug_info: Dict[str, object] = {
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
            },
        }
        if self.config.debug:
            debug_info["memory_bundle"] = self.memory_store.export_bundle_dict(bundle)
        return response.text, debug_info

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

    def process_memory_task(self, task: MemoryTask) -> Dict[str, object]:
        """Index the exchange; every summary_turn_window turns, run one LLM
        call that refreshes the summary and extracts facts. Returns timing
        metadata for the caller to log."""
        result: Dict[str, object] = {"episodic_ms": None, "distill_ms": None, "facts_extracted": 0}
        if self.episodic_index is not None:
            episodic_started = time.perf_counter()
            self.episodic_index.add(
                user_text=task.user_text,
                assistant_text=task.assistant_text,
                session_id=task.session_id,
            )
            result["episodic_ms"] = int((time.perf_counter() - episodic_started) * 1000)

        if self.memory_store.count_turns_since_last_summary() < self.config.summary_turn_window:
            return result

        active_profile = self.config.model_profiles.get(task.active_profile_name)
        if active_profile is None:
            active_profile = next(iter(self.config.model_profiles.values()))
        distill_started = time.perf_counter()
        turns = self.memory_store.get_recent_turns(limit=self.config.summary_turn_window)
        previous_summary = self.memory_store.get_latest_summary()
        provider = self.provider_registry.get(active_profile.provider)
        summary_text, facts = self.distiller.distill(
            turns,
            previous_summary=previous_summary,
            provider=provider,
            profile=active_profile,
        )
        self.memory_store.save_summary(
            session_id=task.session_id,
            summary_text=summary_text,
            turn_count=self.memory_store.get_turn_count(task.session_id),
            last_turn_id=self.memory_store.get_max_turn_id(),
        )
        for fact in facts:
            self.memory_store.upsert_fact(fact, source_turn_id=task.user_turn_id)
        result["distill_ms"] = int((time.perf_counter() - distill_started) * 1000)
        result["facts_extracted"] = len(facts)
        return result

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
            results.append(
                {
                    "prompt_name": prompt["name"],
                    "profile_name": profile.name,
                    "provider": profile.provider,
                    "model_name": profile.model,
                    "prompt_size": response.prompt_tokens_estimate,
                    "response_size": response.response_tokens_estimate,
                    "latency_ms": latency_ms,
                    "reply": response.text,
                }
            )
        return results


def tokenize_words(text: str) -> List[str]:
    return text.split()


def render_debug_info(debug_info: Dict[str, object]) -> str:
    return json.dumps(debug_info, indent=2, ensure_ascii=True)
