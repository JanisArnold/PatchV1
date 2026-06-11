from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

from patch.contracts import ChatMessage, ModelProfile, ProviderResponse


class LlamaCppChatProvider:
    def __init__(self, base_url: str, timeout_seconds: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def healthcheck(self) -> tuple:
        try:
            models = self.list_models()
        except RuntimeError as exc:
            return False, str(exc)
        return True, f"llama.cpp server reachable with {len(models)} model(s)."

    def list_models(self) -> List[str]:
        payload = self._request_json("GET", "/v1/models")
        models = payload.get("data", [])
        return [item["id"] for item in models if isinstance(item, dict) and "id" in item]

    def estimate_capabilities(self, model_name: str) -> str:
        lower = model_name.lower()
        if "9b" in lower or "8b" in lower or "7b" in lower:
            return "Stronger local reasoning with a higher Pi/desktop cost."
        if "4b" in lower or "e4b" in lower:
            return "Balanced local chat that may still be heavy on a Pi 4."
        if "2b" in lower or "3b" in lower or "e2b" in lower:
            return "Pi-friendly local chat if the GGUF quantization is efficient."
        return "Capability estimate unknown; test with /benchmark and /perf."

    def supports_reasoning_toggle(self, model_profile: ModelProfile) -> bool:
        del model_profile
        # Forwarded as chat_template_kwargs.enable_thinking; models without a
        # thinking channel simply ignore it.
        return True

    def generate_reply(self, messages: List[ChatMessage], model_profile: ModelProfile) -> ProviderResponse:
        body = self._build_body(messages, model_profile, stream=False)
        payload = self._request_json("POST", "/v1/chat/completions", body)
        choices = payload.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
        text = str(message.get("content", "")).strip()
        usage = payload.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", _estimate_tokens(" ".join(item.content for item in messages))))
        response_tokens = int(usage.get("completion_tokens", _estimate_tokens(text)))
        return ProviderResponse(
            text=text,
            prompt_tokens_estimate=prompt_tokens,
            response_tokens_estimate=response_tokens,
            raw=payload,
        )

    def generate_stream(
        self,
        messages: List[ChatMessage],
        model_profile: ModelProfile,
        on_token: Callable[[str], None],
    ) -> ProviderResponse:
        """Stream tokens via SSE, invoking on_token per content delta."""
        body = self._build_body(messages, model_profile, stream=True)
        request = urllib.request.Request(
            url=f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        pieces: List[str] = []
        usage: Dict[str, object] = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]
                    choices = chunk.get("choices", [])
                    delta = choices[0].get("delta", {}) if choices else {}
                    token = delta.get("content")
                    if token:
                        pieces.append(token)
                        on_token(token)
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(
                f"llama.cpp stream timed out after {self.timeout_seconds} seconds."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to reach llama.cpp at {self.base_url}: {exc}") from exc

        text = "".join(pieces).strip()
        prompt_tokens = int(usage.get("prompt_tokens", _estimate_tokens(" ".join(item.content for item in messages))))
        response_tokens = int(usage.get("completion_tokens", _estimate_tokens(text)))
        return ProviderResponse(
            text=text,
            prompt_tokens_estimate=prompt_tokens,
            response_tokens_estimate=response_tokens,
            raw={"usage": usage, "streamed": True},
        )

    def _build_body(
        self,
        messages: List[ChatMessage],
        model_profile: ModelProfile,
        stream: bool,
    ) -> Dict[str, object]:
        body: Dict[str, object] = {
            "model": model_profile.model,
            "stream": stream,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": model_profile.temperature,
            "top_p": model_profile.top_p,
            # Reuse the cached prefix (persona + facts stay stable between
            # turns), which cuts prompt-eval time on the Pi.
            "cache_prompt": True,
        }
        max_tokens = model_profile.options.get("max_tokens")
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        think = model_profile.options.get("think")
        if isinstance(think, bool):
            body["chat_template_kwargs"] = {"enable_thinking": think}
            # Keep any reasoning channel out of the spoken/displayed content.
            body["reasoning_format"] = "auto"
        return body

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
                f"llama.cpp request to {self.base_url}{path} timed out after {self.timeout_seconds} seconds."
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(
                f"llama.cpp request to {self.base_url}{path} timed out after {self.timeout_seconds} seconds."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to reach llama.cpp at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("llama.cpp returned invalid JSON.") from exc


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))
