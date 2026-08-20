"""Llama-family LLM client, accessed via Groq's OpenAI-compatible API.

Provider is env-configurable (LLM_PROVIDER/LLM_MODEL/LLM_API_KEY) rather than
hard-coded, per the project's stack-lock rules -- but only 'groq' is actually
implemented right now. Swapping to another OpenAI-compatible Llama host later
(Cerebras, OpenRouter, ...) means adding a branch here, not rewriting callers.
"""

from __future__ import annotations

from langchain_groq import ChatGroq

from app.config import settings


def get_llm(temperature: float = 0.0) -> ChatGroq:
    """Construct the chat model used for SQL generation.

    temperature defaults to 0.0: SQL generation wants low variance, not
    creativity (spec: "deterministic settings where appropriate").
    """
    if not (settings.llm_provider and settings.llm_model and settings.llm_api_key):
        raise RuntimeError(
            "LLM is not configured. Set LLM_PROVIDER, LLM_MODEL, and LLM_API_KEY in .env "
            "(see .env.example)."
        )
    if settings.llm_provider != "groq":
        raise RuntimeError(
            f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}. Only 'groq' is currently supported."
        )
    return ChatGroq(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        temperature=temperature,
    )
