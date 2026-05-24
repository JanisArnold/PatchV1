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
class MemoryBundle:
    recent_turns: List[ChatMessage]
    latest_summary: Optional[str]
    facts: List[MemoryFact]


@dataclass
class ProviderResponse:
    text: str
    prompt_tokens_estimate: int
    response_tokens_estimate: int
    raw: Dict[str, object] = field(default_factory=dict)


class ChatProvider(Protocol):
    def generate_reply(self, messages: List[ChatMessage], model_profile: ModelProfile) -> ProviderResponse:
        ...

    def healthcheck(self) -> tuple:
        ...

    def list_models(self) -> List[str]:
        ...

    def estimate_capabilities(self, model_name: str) -> str:
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
