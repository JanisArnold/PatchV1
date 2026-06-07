from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional

from patch.config import AppConfig
from patch.contracts import ChatMessage, MemoryFact, ModelProfile, ProviderResponse
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
    ) -> None:
        self.config = config
        self.memory_store = memory_store
        self.provider_registry = provider_registry
        self.persona = persona
        self.fact_extractor = RuleBasedFactExtractor()
        self.summary_service = SummaryService()

    def generate_reply(self, user_text: str, profile: ModelProfile) -> tuple:
        started_total = time.perf_counter()
        retrieval_started = time.perf_counter()
        bundle = self.memory_store.build_memory_bundle(
            query=user_text,
            recent_turn_limit=self.config.recent_turn_limit,
            max_fact_hits=self.config.max_fact_hits,
        )
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)
        prompt_started = time.perf_counter()
        messages = self._build_messages(user_text, profile, bundle)
        prompt_build_ms = int((time.perf_counter() - prompt_started) * 1000)
        provider = self.provider_registry[profile.provider]
        started = time.perf_counter()
        response: ProviderResponse = provider.generate_reply(messages, profile)
        latency_ms = int((time.perf_counter() - started) * 1000)
        total_ms = int((time.perf_counter() - started_total) * 1000)
        debug_info: Dict[str, object] = {
            "memory_bundle": self.memory_store.export_bundle_dict(bundle),
            "prompt_tokens_estimate": response.prompt_tokens_estimate,
            "response_tokens_estimate": response.response_tokens_estimate,
            "latency_ms": latency_ms,
            "retrieval_ms": retrieval_ms,
            "prompt_build_ms": prompt_build_ms,
            "total_ms": total_ms,
            "profile": profile.name,
            "model": profile.model,
        }
        return response.text, debug_info

    def update_memory(
        self,
        *,
        session_id: int,
        user_turn_id: int,
        user_text: str,
        assistant_text: str,
        active_profile: ModelProfile,
    ) -> None:
        fact_started = time.perf_counter()
        for fact in self.fact_extractor.extract(user_text, assistant_text):
            self.memory_store.upsert_fact(fact, source_turn_id=user_turn_id)
        fact_extraction_ms = int((time.perf_counter() - fact_started) * 1000)
        self.memory_store.record_performance_log(
            session_id=session_id,
            phase="memory.fact_extraction",
            latency_ms=fact_extraction_ms,
            metadata_json=json.dumps({"profile": active_profile.name}),
        )

        total_turns = self.memory_store.get_turn_count(session_id)
        if total_turns % self.config.summary_turn_window != 0:
            return

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
            session_id=session_id,
            summary_text=summary_text,
            turn_count=total_turns,
        )
        summary_ms = int((time.perf_counter() - summary_started) * 1000)
        self.memory_store.record_performance_log(
            session_id=session_id,
            phase="memory.summary",
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
