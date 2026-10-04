# LLM integration

Code: `app/llm.py`. The rest of the application only sees one method:

```python
class LLMClient(ABC):
    model: str
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...
```

`create_llm_client(settings)` is the only place that knows which provider is in use. Adding a provider means writing one subclass.

## Providers

| `LLM_PROVIDER` | Class | Transport | Notes |
|---|---|---|---|
| `anthropic` | `AnthropicClient` | official `anthropic` SDK, Messages API | Sends `model`, `max_tokens`, `system`, one user message, and `output_config.effort` only if `LLM_EFFORT` is set. Never sends `temperature`. |
| `openai` | `OpenAICompatibleClient` | `httpx` POST to `{LLM_BASE_URL}/chat/completions` | For OpenAI, Groq, Together, OpenRouter (including the free router `openrouter/free`), local Ollama, … Always sends `max_tokens` and `temperature`, which some newer models reject. |

The LLM client is created **lazily**: the app starts without a key, search works, and `/api/ask` returns 503 until a key is configured. Changing any `llm_*` setting from the Settings page discards the cached client, so the next question uses the new provider, model or key.

## Prompts

- **System prompt:** the grounding rules ([PROMPTING.md](PROMPTING.md)).
- **User prompt:** numbered sources inside `<sources>` tags, then the question.

## Response handling

- **Text only.** Thinking-capable models return non-text content blocks; only `text` blocks form the answer.
- **Truncation.** If the model stops at `max_tokens` (Anthropic `stop_reason == "max_tokens"`, OpenAI `finish_reason == "length"`), the answer is returned with "(Answer truncated: the model reached LLM_MAX_TOKENS.)" appended and a warning is logged.
- **Refusal** (`stop_reason == "refusal"`) or an empty reply raises `LLMError`.
- **Routed models.** When a router model such as `openrouter/free` is served by a different model, the server logs `LLM endpoint routed model=… to …`.
- **Grounding.** The text returned here is then classified by `qa.answer_question` (grounded / not found / ungrounded); an ungrounded reply causes one more `generate` call with a reminder ([CITATIONS.md](CITATIONS.md#ungrounded-replies-one-retry-then-unverified)). That retry is separate from the transport retry below.

## Retries

- `OpenAICompatibleClient` retries **once** after a transient failure: HTTP 429, 500, 502, 503 or 504, or a network error. It waits for `Retry-After` (capped at 5 s) if the response has one, otherwise 1 s. Other 4xx responses, such as 400 or 401, are not retried. Through `openrouter/free`, the retry may be served by a different model.
- `AnthropicClient` relies on the Anthropic SDK's own built-in retries.

## Configuration

`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_EFFORT`, `LLM_MAX_TOKENS` (default 8192, including reasoning tokens), `LLM_TEMPERATURE` (OpenAI-compatible only), `LLM_TIMEOUT_SECONDS`. All are editable on the Settings page; the key is write-only. See [CONFIGURATION.md](CONFIGURATION.md).

**Test connection** (`POST /api/admin/settings/test-llm`, admin only) makes one tiny real request ("Reply with the single word: OK") and reports success and latency, or the error.

## Error handling

| Situation | Raised | API status | User sees |
|---|---|---|---|
| No key / model | `LLMNotConfiguredError` | 503 | "AI question answering is currently unavailable." |
| Bad key (401) | `LLMError` | 502 | "The AI provider returned an error…" |
| Rate limit (429), after one retry | `LLMError` | 502 | same |
| Other HTTP error (5xx after one retry; 4xx immediately) | `LLMError("…HTTP n (see server log)")` | 502 | same |
| Network failure, after one retry | `LLMError` | 502 | same |

Provider error **bodies** are logged (truncated to 300 characters) but never returned to clients. Prompts and answers are never logged, only their sizes and timings.

## Verification status

- `AnthropicClient` is tested with the **real SDK** against a mocked HTTP transport: request shape, effort, text-only extraction, truncation, refusal, error mapping (`tests/test_production.py`).
- `OpenAICompatibleClient` is tested against `httpx.MockTransport`.
- The full Ask flow, including citation chips, invalid citations and the not-found path, was exercised in the browser with a **scripted stand-in LLM**.
- **Live provider check (2026-10-04):** OpenRouter (`LLM_PROVIDER=openai`, `LLM_BASE_URL=https://openrouter.ai/api/v1`) with `nvidia/nemotron-3-super-120b-a12b:free`, through the API and the web UI, on a freshly uploaded 3-page PDF:
  - **Factual questions:** answered correctly, citing the right page.
  - **Off-topic questions:** abstained with the not-found sentence.
  - **Invalid key:** gave a generic 502 that does not echo the key.
  - **Leak scan:** neither the key nor the token appeared in responses, logs or bundles.
  - **Scope:** a handful of questions, not a quality benchmark; the Anthropic provider has still not been run live.
- **`openrouter/free` live test (2026-10-04, production mode, through the API):** `LLM_PROVIDER=openai`, `LLM_MODEL=openrouter/free`, `LLM_BASE_URL=https://openrouter.ai/api/v1`. 8 questions (2 factual and 2 unanswerable, each asked twice) were routed to 4 different free models (`apodex/apodex-1.1-mini`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, `nvidia/nemotron-3.5-lightning`, `poolside/laguna-s-2.1`):
  - **Factual:** all 4 answers grounded, correct, and citing the right page.
  - **Unanswerable:** all 4 abstained; 2 of them without an LLM call, because no passage passed the relevance floor.
  - **Non-existent model:** HTTP 502 "LLM request failed: LLM endpoint returned HTTP 400 (see server log)".
  - **Leak scan:** no secrets in responses or logs.
  - **Prompt injection:** see [PROMPTING.md](PROMPTING.md#prompt-injection-hardening).
- `openrouter/free` is a supported configuration. Before the grounding retry existed, it once routed to a content-safety classifier that replied "User Safety: safe". Such a reply is now classified `ungrounded`, retried once, and if still uncited never shown as an answer (only as unverified output). Pinning a concrete model ID remains the most predictable option; the log line `LLM endpoint routed model=… to …` shows which model a router picked.
