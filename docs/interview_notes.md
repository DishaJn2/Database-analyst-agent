# Interview Notes

Running notes on design decisions, alternatives considered, and tradeoffs — filled in as each phase is implemented, per the build spec's interview-defensibility requirement.

## LLM provider selection: why the model isn't actually Llama

The original resume-driven spec locked "Llama-family LLM" as a requirement. In
practice, every free hosted Llama chat option dead-ended, verified live
against each provider's own API within the same development session:

1. **Groq** — `llama-3.3-70b-versatile`, `llama-3.1-70b-versatile`, and
   `llama3-70b-8192` all returned errors directly from Groq's API stating the
   models have been **decommissioned**. `models.list()` on the account showed
   only a non-chat `llama-prompt-guard` safety classifier under Llama
   branding -- unusable for SQL generation.
2. **Cerebras** — their own docs (`inference-docs.cerebras.ai`) state
   Llama 3.1 8B was deprecated May 2026, and Llama 3.3 70B has *also* been
   deprecated with an explicit recommendation to migrate to GPT-OSS 120B.
3. **OpenRouter** — `meta-llama/llama-3.3-70b-instruct:free` returned a 404
   with an explicit message that the free variant was pulled ("paid version
   available now"). A live query against OpenRouter's `/models` endpoint,
   filtered for `pricing == 0` and `llama` in the id, returned **zero**
   results at the time of building this.

Three independent providers, same direction, same week -- not bad luck. The
industry's free-tier hosting appears to have broadly shifted from Llama
toward OpenAI's open-weight GPT-OSS models in this window.

**Decision:** rather than keep chasing a moving target (or take on a
perpetual-free but higher-setup-friction option like Cloudflare Workers AI),
the project uses **GPT-OSS-20B via Groq** -- verified live: plain chat
completion, schema-aware SQL generation, and `bind_tools()` tool-calling all
work correctly.

**What this means for the resume claim:** "Llama-family LLM" is no longer
accurate and the README/resume language should say "open-weight LLM
(GPT-OSS-20B) via Groq" instead. The architecture, agent design, tool
calling, validation, and evaluation methodology are all unaffected -- this
project would work identically with any sufficiently capable chat model
behind `app/agent/llm.py`, which is exactly the point of keeping the
provider env-configurable rather than hard-coded.

**How to answer "why isn't this Llama, doesn't your resume say Llama?" in an
interview:** be direct about it. This is a legitimate, currently-relevant
engineering story -- free-tier LLM hosting is genuinely volatile right now,
and picking an abstraction (LangChain's chat model interface, an
env-configurable provider) instead of hard-coding a specific vendor's SDK is
exactly the right response to that volatility. That's a stronger answer than
pretending the constraint didn't exist.
