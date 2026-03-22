from __future__ import annotations

import json
import random
import time
from typing import Any

import requests

from app.common.config import settings


class LLMGateway:
    def __init__(self) -> None:
        self.enabled = bool(settings.llm_api_key and settings.llm_base_url and settings.llm_model)

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.enabled:
            return {}

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        max_retries = max(0, settings.llm_max_retries)
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=settings.llm_timeout,
                )
            except requests.RequestException:
                if attempt >= max_retries:
                    return {}
                time.sleep(self._retry_delay(attempt=attempt, response=None))
                continue

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= max_retries:
                    return {}
                time.sleep(self._retry_delay(attempt=attempt, response=response))
                continue

            try:
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
            except (requests.RequestException, ValueError, KeyError, TypeError):
                return {}

            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except ValueError:
                    return {}
                return parsed if isinstance(parsed, dict) else {}

            return content if isinstance(content, dict) else {}

        return {}

    @staticmethod
    def _retry_delay(attempt: int, response: requests.Response | None) -> float:
        retry_after = None
        if response is not None:
            retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(0.0, float(retry_after)), settings.llm_retry_max_seconds)
            except ValueError:
                pass

        # Exponential backoff with jitter to avoid synchronized retries.
        base = max(0.1, settings.llm_retry_base_seconds)
        jitter = random.uniform(0.0, base)
        return min((base * (2 ** attempt)) + jitter, settings.llm_retry_max_seconds)
