"""Small OpenAI-compatible DeepSeek client using the official HTTPS API."""

from __future__ import annotations

import http.client
import json
import re
import socket
import ssl
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit


class DeepSeekError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelInfo:
    id: str
    input_modalities: tuple[str, ...] = ("text",)
    context_window: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    usage: dict[str, int]


class DeepSeekClient:
    def __init__(self, endpoint: str, api_key: str, timeout: float = 75.0):
        self.endpoint = endpoint.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self._connection_lock = threading.Lock()
        self._active_connection: http.client.HTTPConnection | None = None
        self._cancelled = threading.Event()
        if not self.api_key:
            raise DeepSeekError("Add your DeepSeek API key in AI Settings first.")

    def cancel(self) -> None:
        self._cancelled.set()
        with self._connection_lock:
            connection = self._active_connection
        if connection:
            try:
                connection.close()
            except OSError:
                pass

    def _request(self, path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
        if self._cancelled.is_set():
            raise DeepSeekError("AI request cancelled.")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        parts = urlsplit(self.endpoint)
        request_path = f"{parts.path.rstrip('/')}{path}"
        if parts.query:
            request_path += f"?{parts.query}"
        try:
            connection_type = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
            kwargs = {"timeout": self.timeout}
            if parts.scheme == "https":
                kwargs["context"] = ssl.create_default_context()
            connection = connection_type(parts.hostname, parts.port, **kwargs)
        except (ValueError, OSError) as error:
            raise DeepSeekError("The configured AI endpoint URL is invalid.") from error
        with self._connection_lock:
            if self._cancelled.is_set():
                connection.close()
                raise DeepSeekError("AI request cancelled.")
            self._active_connection = connection
        try:
            connection.request(
                method,
                request_path,
                body=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "EazyFix-AI-Video-Studio/0.2",
                },
            )
            response = connection.getresponse()
            response_body = response.read()
            if response.status >= 400:
                detail = self._error_detail(response_body)
                if response.status in {401, 403}:
                    raise DeepSeekError("DeepSeek rejected the API key. Check it in AI Settings.")
                raise DeepSeekError(f"DeepSeek API returned HTTP {response.status}: {detail}")
            if self._cancelled.is_set():
                raise DeepSeekError("AI request cancelled.")
            result = json.loads(response_body.decode("utf-8"))
        except (socket.timeout, TimeoutError):
            raise DeepSeekError("The AI provider did not respond before the timeout. Retry the request.") from None
        except http.client.HTTPException as error:
            if self._cancelled.is_set():
                raise DeepSeekError("AI request cancelled.") from None
            raise DeepSeekError(f"The AI provider connection failed: {error}") from None
        except OSError as error:
            if self._cancelled.is_set():
                raise DeepSeekError("AI request cancelled.") from None
            raise DeepSeekError(f"Could not reach the AI provider: {error}") from None
        except UnicodeDecodeError:
            raise DeepSeekError("The AI provider returned an unreadable response.") from None
        except json.JSONDecodeError:
            raise DeepSeekError("The AI provider returned an unreadable response.") from None
        finally:
            with self._connection_lock:
                if self._active_connection is connection:
                    self._active_connection = None
            connection.close()
        if not isinstance(result, dict):
            raise DeepSeekError("The AI provider returned an invalid response object.")
        return result

    @staticmethod
    def _error_detail(body: bytes) -> str:
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
            message = payload.get("error", {}).get("message", "")
            message = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", str(message))
            return message[:240] or "request was not accepted"
        except Exception:
            return "request was not accepted"

    def list_models(self) -> list[ModelInfo]:
        response = self._request("/models")
        data = response.get("data")
        if not isinstance(data, list):
            raise DeepSeekError("DeepSeek returned an invalid model list.")
        models: list[ModelInfo] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            models.append(
                ModelInfo(
                    id=item["id"],
                    input_modalities=tuple(value for value in item.get("input_modalities", ["text"]) if isinstance(value, str)),
                    context_window=item.get("context_window") if isinstance(item.get("context_window"), int) else None,
                    max_output_tokens=item.get("max_output_tokens") if isinstance(item.get("max_output_tokens"), int) else None,
                )
            )
        return models

    def chat_completion(self, *, model: str, messages: list[dict], max_tokens: int = 4096) -> Completion:
        response = self._request(
            "/chat/completions",
            method="POST",
            payload={
                "model": model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "max_tokens": max_tokens,
                "temperature": 0.35,
                "stream": False,
            },
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DeepSeekError("DeepSeek returned no answer. Retry the request.")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek returned empty JSON. Retry once or simplify the request.")
        raw_usage = response.get("usage", {})
        usage = {
            key: int(raw_usage[key])
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(raw_usage, dict) and isinstance(raw_usage.get(key), int)
        }
        return Completion(content=content, model=str(response.get("model", model)), usage=usage)
