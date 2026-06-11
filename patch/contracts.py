from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ModelProfile:
    name: str
    provider: str
    model: str
    system_prompt: str
    model_path: Optional[str] = None
    temperature: float = 0.4
    top_p: float = 0.9
    num_ctx: int = 4096
    options: Dict[str, object] = field(default_factory=dict)


@dataclass
class MemoryFact:
    subject: str
    predicate: str
    value: str
    confidence: float = 0.5


@dataclass
class EpisodicMemory:
    user_text: str
    assistant_text: str
    created_at: str
    score: float = 0.0


@dataclass
class MemoryBundle:
    recent_turns: List[ChatMessage]
    latest_summary: Optional[str]
    facts: List[MemoryFact]
    episodes: List[EpisodicMemory] = field(default_factory=list)


@dataclass
class ProviderResponse:
    text: str
    prompt_tokens_estimate: int
    response_tokens_estimate: int
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass
class TurnPlan:
    turn_type: str
    recent_turn_limit: int
    include_summary: bool
    include_facts: bool
    include_episodes: bool = False
    # None = leave the profile setting alone; True/False = per-turn override.
    think: Optional[bool] = None


@dataclass
class MemoryTask:
    session_id: int
    user_turn_id: int
    user_text: str
    assistant_text: str
    active_profile_name: str


class ChatProvider(Protocol):
    def generate_reply(self, messages: List[ChatMessage], model_profile: ModelProfile) -> ProviderResponse:
        ...

    def generate_stream(
        self,
        messages: List[ChatMessage],
        model_profile: ModelProfile,
        on_token,
    ) -> ProviderResponse:
        ...

    def healthcheck(self) -> tuple:
        ...

    def list_models(self) -> List[str]:
        ...

    def estimate_capabilities(self, model_name: str) -> str:
        ...

    def supports_reasoning_toggle(self, model_profile: ModelProfile) -> bool:
        ...


class MemoryStore(Protocol):
    def create_session(self) -> int:
        ...


class FactExtractor(Protocol):
    def extract(self, user_text: str, assistant_text: str) -> List[MemoryFact]:
        ...


class SummaryGenerator(Protocol):
    def summarize(self, turns: List[ChatMessage], previous_summary: Optional[str] = None) -> str:
        ...


class InputAdapter(Protocol):
    def get_input(self) -> str:
        ...


class OutputAdapter(Protocol):
    def emit(self, text: str) -> None:
        ...


class DisplayAdapter(Protocol):
    def on_state_change(self, state: str) -> None:
        ...


class VisionAdapter(Protocol):
    def capture_scene_description(self, prompt: Optional[str] = None) -> Optional[str]:
        ...


class EpisodicIndex(Protocol):
    def add(self, *, user_text: str, assistant_text: str, session_id: int) -> None:
        ...

    def search(self, query: str, limit: int) -> List[EpisodicMemory]:
        ...
