from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from patch.contracts import ChatMessage, ModelProfile, ProviderResponse


class OllamaChatProvider:
    def __init__(self, base_url: str, timeout_seconds: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def healthcheck(self) -> tuple:
        try:
            models = self.list_models()
        except RuntimeError as exc:
            return False, str(exc)
        return True, f"Ollama reachable with {len(models)} model(s)."

    def list_models(self) -> List[str]:
        payload = self._request_json("GET", "/api/tags")
        models = payload.get("models", [])
        return [item["name"] for item in models if "name" in item]

    def estimate_capabilities(self, model_name: str) -> str:
        lower = model_name.lower()
        if "7b" in lower or "8b" in lower:
            return "Balanced local reasoning on desktop-class hardware."
        if "2b" in lower or "3b" in lower:
            return "Fast lightweight chat with lower reasoning depth."
        return "Capability estimate unknown; test with /benchmark."

    def generate_reply(self, messages: List[ChatMessage], model_profile: ModelProfile) -> ProviderResponse:
        body = {
            "model": model_profile.model,
            "stream": False,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {
                "temperature": model_profile.temperature,
                "top_p": model_profile.top_p,
                "num_ctx": model_profile.num_ctx,
                **model_profile.options,
            },
        }
        payload = self._request_json("POST", "/api/chat", body)
        message = payload.get("message", {})
        text = str(message.get("content", "")).strip()
        prompt_tokens = _estimate_tokens(" ".join(item.content for item in messages))
        response_tokens = _estimate_tokens(text)
        return ProviderResponse(
            text=text,
            prompt_tokens_estimate=prompt_tokens,
            response_tokens_estimate=response_tokens,
            raw=payload,
        )

    def _request_json(self, method: str, path: str, body: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise RuntimeError(
                f"Ollama request to {self.base_url}{path} timed out after {self.timeout_seconds} seconds."
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(
                f"Ollama request to {self.base_url}{path} timed out after {self.timeout_seconds} seconds."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to reach Ollama at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned invalid JSON.") from exc


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))
