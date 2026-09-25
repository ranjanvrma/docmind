"""LLM provider abstraction.

The rest of the application only sees ``LLMClient.generate(system, user)``.
Which provider sits behind it is decided once, in ``create_llm_client``, from
environment variables:

* ``LLM_PROVIDER=anthropic`` -> Anthropic Messages API via the official SDK.
* ``LLM_PROVIDER=openai``    -> any OpenAI-compatible ``/chat/completions``
  endpoint (OpenAI, Groq, Together, OpenRouter, a local Ollama server, ...).
  Set ``LLM_BASE_URL`` to point at a non-OpenAI server.

Adding another provider means writing one more subclass; nothing else changes.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """The LLM call failed (network, auth, rate limit, bad response...)."""


class LLMNotConfiguredError(LLMError):
    """No API key / model configured, so question answering is unavailable."""


class LLMClient(ABC):
    model: str

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's text reply."""


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str, max_tokens: int, timeout: float):
        import anthropic  # imported lazily so the dependency is only needed for this provider

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key (check LLM_API_KEY)") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached; try again shortly") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API") from exc

        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this request")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("The model returned an empty response")
        if response.stop_reason == "max_tokens":
            logger.warning("LLM response was truncated at max_tokens=%d", self.max_tokens)
        return text


class OpenAICompatibleClient(LLMClient):
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout: float,
        base_url: str = "",
        temperature: float = 0.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = httpx.Client(
            base_url=(base_url or self.DEFAULT_BASE_URL).rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach the LLM endpoint: {exc.__class__.__name__}") from exc

        if response.status_code == 401:
            raise LLMError("The LLM endpoint rejected the API key (check LLM_API_KEY)")
        if response.status_code == 429:
            raise LLMError("LLM rate limit reached; try again shortly")
        if response.status_code >= 400:
            raise LLMError(f"LLM endpoint returned HTTP {response.status_code}: {response.text[:300]}")

        try:
            text = (response.json()["choices"][0]["message"]["content"] or "").strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Unexpected response format from the LLM endpoint") from exc
        if not text:
            raise LLMError("The model returned an empty response")
        return text


def create_llm_client(settings: Settings) -> LLMClient:
    if not settings.llm_configured:
        raise LLMNotConfiguredError(
            "Question answering needs an LLM. Set LLM_API_KEY (and optionally LLM_PROVIDER / LLM_MODEL) in .env."
        )
    if settings.llm_provider == "anthropic":
        client: LLMClient = AnthropicClient(
            settings.llm_api_key, settings.llm_model, settings.llm_max_tokens, settings.llm_timeout_seconds
        )
    else:
        client = OpenAICompatibleClient(
            settings.llm_api_key,
            settings.llm_model,
            settings.llm_max_tokens,
            settings.llm_timeout_seconds,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
        )
    logger.info("LLM client ready: provider=%s model=%s", settings.llm_provider, settings.llm_model)
    return client


def timed_generate(client: LLMClient, system_prompt: str, user_prompt: str) -> str:
    start = time.perf_counter()
    text = client.generate(system_prompt, user_prompt)
    logger.info(
        "LLM call model=%s prompt_chars=%d answer_chars=%d took %.1fs",
        client.model,
        len(system_prompt) + len(user_prompt),
        len(text),
        time.perf_counter() - start,
    )
    return text
