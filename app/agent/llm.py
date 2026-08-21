"""Open-weight LLM client, accessed via an OpenAI-compatible API.

Provider is env-configurable (LLM_PROVIDER/LLM_MODEL/LLM_API_KEY) rather than
hard-coded, per the project's stack-lock rules. Two providers are wired up:

  - groq: fast, generous free tier. Currently configured to use
    openai/gpt-oss-20b -- NOT a Llama model. As of this build, Groq, Cerebras,
    and OpenRouter had all independently decommissioned or pulled free access
    to their Llama chat models within the same week (confirmed live against
    each provider's own API, not docs/blog posts). GPT-OSS-20B was chosen as
    the pragmatic fallback with zero setup friction on an already-verified
    account. This means the "Llama-family LLM" framing from the original
    resume claim no longer applies to the implementation -- see
    docs/architecture.md for the full provider timeline, and describe this
    honestly in the README as an open-weight LLM, not as Llama.
  - openrouter: kept as a working alternate path (Llama access there is
    volatile -- verify current free-model availability before relying on it).

Both are OpenAI-compatible endpoints, so this only ever needs
langchain_openai/langchain_groq clients with a different base_url -- adding
a third provider later means adding a branch, not rewriting callers.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    """Construct the chat model used for SQL generation.

    temperature defaults to 0.0: SQL generation wants low variance, not
    creativity (spec: "deterministic settings where appropriate").
    """
    if not (settings.llm_provider and settings.llm_model and settings.llm_api_key):
        raise RuntimeError(
            "LLM is not configured. Set LLM_PROVIDER, LLM_MODEL, and LLM_API_KEY in .env "
            "(see .env.example)."
        )

    if settings.llm_provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=OPENROUTER_BASE_URL,
            temperature=temperature,
        )

    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=temperature,
        )

    raise RuntimeError(
        f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}. Supported: 'openrouter', 'groq'."
    )
