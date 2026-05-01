"""LLM 网关 — OpenAI 兼容的 LLM 调用封装，含指数退避重试。"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import requests

from app.common.config import settings

logger = logging.getLogger(__name__)


class LLMGateway:
    """OpenAI-compatible LLM 调用网关。

    支持 JSON 模式输出、自动重试（指数退避 + jitter）、429/5xx 处理。
    未配置 API key 时 enabled=False，所有调用返回空 dict。
    """

    def __init__(self) -> None:
        self.enabled = bool(settings.llm_api_key and settings.llm_base_url and settings.llm_model)

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """调用 LLM 并返回解析后的 JSON dict。失败时返回 {}。"""
        if not self.enabled:
            logger.debug("LLM disabled, returning {}")
            return {}

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if settings.llm_temperature >= 0:
            payload["temperature"] = settings.llm_temperature
        if settings.llm_json_mode:
            payload["response_format"] = {"type": "json_object"}
        if settings.llm_thinking_disabled:
            payload["thinking"] = {"type": "disabled"}

        logger.debug("LLM 请求: model=%s user_prompt_len=%d json_mode=%s temp=%s",
                     settings.llm_model, len(user_prompt), settings.llm_json_mode,
                     settings.llm_temperature if settings.llm_temperature >= 0 else "omitted")

        max_retries = max(0, settings.llm_max_retries)
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=settings.llm_timeout,
                )
            except requests.RequestException as exc:
                logger.warning("LLM 请求异常 (%d/%d): %s", attempt + 1, max_retries + 1, exc)
                if attempt >= max_retries:
                    return {}
                time.sleep(self._retry_delay(attempt=attempt, response=None))
                continue

            logger.debug("LLM HTTP %d (attempt %d/%d)", response.status_code, attempt + 1, max_retries + 1)

            if response.status_code == 429 or 500 <= response.status_code < 600:
                logger.warning("LLM HTTP %d (%d/%d)", response.status_code, attempt + 1, max_retries + 1)
                if attempt >= max_retries:
                    return {}
                time.sleep(self._retry_delay(attempt=attempt, response=response))
                continue

            try:
                response.raise_for_status()
                body = response.json()
                # Log full response structure at DEBUG level
                logger.debug(
                    "LLM 完整响应: model=%s finish_reason=%s usage=%s content_len=%d",
                    body.get("model", "?"),
                    body.get("choices", [{}])[0].get("finish_reason", "?"),
                    body.get("usage", {}),
                    len(body.get("choices", [{}])[0].get("message", {}).get("content", "")),
                )
                content = body["choices"][0]["message"]["content"]
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                resp_snippet = ""
                try:
                    resp_snippet = response.text[:800]
                except Exception:
                    pass
                logger.warning("LLM 响应解析失败 (HTTP %d): %s", response.status_code, exc)
                if resp_snippet:
                    logger.warning("LLM 响应体: %s", resp_snippet)
                return {}

            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    logger.debug("LLM JSON 解析成功, keys=%s", list(parsed.keys())[:10])
                except ValueError:
                    logger.warning("LLM 返回非 JSON 文本 (%d 字符): %.500s", len(content), content)
                    return {}
                if isinstance(parsed, dict):
                    return parsed
                logger.warning("LLM 返回非 dict JSON (type=%s)", type(parsed).__name__)
                return {}

            if isinstance(content, dict):
                return content
            logger.warning("LLM 返回未知 content 类型: %s", type(content).__name__)
            return {}

        return {}

    @staticmethod
    def _retry_delay(attempt: int, response: requests.Response | None) -> float:
        """计算指数退避延迟（含 Retry-After 支持和随机 jitter）。"""
        retry_after = None
        if response is not None:
            retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(0.0, float(retry_after)), settings.llm_retry_max_seconds)
            except ValueError:
                pass

        base = max(0.1, settings.llm_retry_base_seconds)
        jitter = random.uniform(0.0, base)
        return min((base * (2 ** attempt)) + jitter, settings.llm_retry_max_seconds)
