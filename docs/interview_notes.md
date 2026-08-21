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

## Agent vs. chatbot vs. workflow

- **A chatbot** answers from what the model already knows (or hallucinates).
  This project never lets the model answer from memory -- every factual claim
  in the final response has to come from a `run_sql` result it actually
  received this turn.
- **A fixed workflow** (`User -> LLM -> SQL -> execute -> return`) has no real
  decision point: the LLM is just one interchangeable step in a hard-coded
  sequence. If the SQL is wrong, there's no path to notice and correct it.
- **This project** is agentic specifically because the control flow isn't
  fully fixed in code: the LLM decides whether it has enough schema context,
  whether a validation/execution failure needs a retry (and how to fix the
  query), and whether the result is worth visualizing. That decision-making
  is real (verified by testing: a `LIMIT 1` ranking question correctly did
  *not* trigger a chart; a top-5 ranking question did), not just a label.
- The bound is what keeps it safe: `max_iterations=6` caps the retry loop,
  and no tool call can bypass validation. Agentic decision-making about *which
  tool to call* is fine to hand to the LLM; agentic decision-making about
  *whether a DROP TABLE should run* is not, and isn't -- that's enforced in
  code the LLM cannot influence.

## Why sqlglot (AST) over regex/string matching for SQL validation

A substring check for `"DROP"` fails in both directions: it's bypassable
(comments, case variation, a column named `dropdown_id`) and it can't
distinguish `DROP TABLE x` from `SELECT * FROM x WHERE note = 'do not drop'`.
Parsing into an AST and checking node *types* fixes both: `DROP` only matters
if it's actually a `Drop` node. This is also what catches Postgres's writable
CTE gotcha (`WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x`),
which still parses as a top-level `SELECT` -- a check that only inspected the
root statement type would miss it; walking the full tree doesn't.

**What the validator deliberately doesn't do:** full alias/type resolution
(e.g. catching `customers.total_amount`, a real column referenced on the
wrong table). That class of error is already reliably caught by Postgres
itself at execution time with a clear error message the agent can act on --
building a full static binder to catch it *before* execution would be a lot
of added complexity for an error class that already fails safely. This is a
deliberate scope boundary, worth stating as one if asked "why doesn't your
validator catch X" -- the honest answer is "because something else already
does, safely."

## Why classic AgentExecutor, not LangGraph

The resume lock explicitly excludes LangGraph. Two build-time details make
this a real constraint, not a token compliance box: LangChain 1.x's newer
`create_agent` API pulls in `langgraph` as a transitive dependency even if no
LangGraph code is written -- so the project pins `langchain>=0.3,<0.4`
specifically to avoid that, verified by checking the installed package list
after each dependency change. The classic `create_tool_calling_agent` +
`AgentExecutor` API (LangChain 0.3.x) provides the same tool-calling loop
without it.

## Two bugs the evaluation suite actually caught

Both are documented in the README's Challenges section; the interview-useful
part is *how* they were found, since "how do you debug this" is a standing
question in the spec:

1. **State format mismatch** ("customers in California" -> 0 results,
   should've been 56): caught by the evaluation suite's correctness check
   against a precomputed expected value, not by manual testing. Root cause:
   the schema prompt had column names/types but no example values, so the
   LLM guessed a plausible-but-wrong format. Fix: sample real distinct values
   for low-cardinality text columns.
2. **Trend hallucination** (identical Nov/Dec revenue in a 12-month trend
   answer): caught by *noticing a statistically implausible result* during
   manual testing, not by an automated check -- a reminder that automated
   correctness checks only catch what they're built to check, and spot-
   checking real outputs against domain knowledge ("would two random months
   really be identical to the cent?") still matters. Root cause: the
   `run_sql` tool summarized trend data as a period *count* plus a 5-row
   sample, so the LLM had real data for 5 of 12 months and fabricated the
   rest to fill out its answer table. Fix: return full trend/ranked values,
   not just their count.

## Scaling considerations (a likely interview question)

- **Schema size**: keyword-based relevance filtering (`get_relevant_tables`)
  works fine at 8 tables; at real scale (50+ tables) it should move to
  embedding-based retrieval over table/column descriptions. The FK-graph
  expansion step would still apply on top of whichever retrieval mechanism
  picks the initial candidate set.
- **Result size**: the "return all rows below 30, else sample + stats"
  approach in `run_sql` bounds token usage at today's data volume; at much
  larger result sets this would need to lean more heavily on the
  precomputed `analyze_result` statistics and less on raw rows, or paginate.
- **Concurrency**: `RunState` is created fresh per request specifically so
  concurrent Streamlit sessions don't share agent state -- this was a
  deliberate choice up front, not a retrofit.
- **LLM cost/quota at scale**: the free-tier daily token ceiling hit during
  this project's own evaluation run is exactly the kind of constraint that
  forces a real production system toward either a paid tier, a self-hosted
  model, or a fallback provider chain -- worth naming unprompted if asked
  "how would you scale this."

## The daily quota is a hard cap, not a rolling window (confirmed empirically)

Worth stating precisely if asked "what happens when the LLM API fails" or
"how do you evaluate the system under real constraints": Groq's 429 error
for `openai/gpt-oss-20b` reports a *tokens-per-day* (TPD) limit of 200,000,
and this was hit twice in the same development session -- once from
cumulative testing, and again roughly 30 minutes later when a single
one-word test call ("used 200000/200000") immediately re-triggered the same
error. If it were a short rolling window, that single small call wouldn't
have re-exhausted it. This is genuine, observed evidence (not documentation
guesswork) that free-tier daily quotas need to be treated as a hard ceiling
for planning evaluation runs and demos, not a soft throttle that clears
itself in a few minutes. The system's actual behavior under this condition
is exactly what you'd want: every failure was caught, reported with the
real provider error message, and the evaluation script completed a full
report instead of crashing -- see `app/services/evaluation_service.py`'s
try/except around each `ask()` call.
