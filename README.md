# Database Analyst Agent

An agentic natural-language-to-SQL analyst for PostgreSQL: ask a business question in plain English, get back a grounded answer, the SQL that produced it, and a chart when one adds value.

## Overview

Database Analyst Agent lets a non-technical user ask questions like *"Which product category generated the highest revenue?"* against a real PostgreSQL retail-analytics database and get a correct, explained answer — without writing SQL themselves. It's built as a controlled agentic workflow: an LLM decides which tools to call and writes the SQL, but every tool enforces deterministic safety regardless of what the LLM asks for.

## Problem Statement

Most people who need answers from a database — analysts, founders, support staff — don't write SQL. The usual workarounds are either asking an engineer (slow, expensive) or building a fixed dashboard (inflexible, doesn't answer the question you actually have today). A natural-language interface removes that bottleneck, but a naive "LLM writes SQL and runs it" approach is genuinely dangerous: LLMs hallucinate columns, generate incorrect joins, and can be prompt-injected into writing destructive SQL. This project's core problem isn't "can an LLM write SQL" — it's "how do you make that safe, verifiable, and actually correct enough to trust."

## Motivation

This project exists to build and demonstrate a genuinely agentic system — not a chatbot wrapper around an LLM, but a workflow where an LLM makes real tool-selection decisions inside deterministic guardrails. The target user is anyone who needs ad-hoc business answers from structured data without SQL skills: a small e-commerce operator asking "which store is underperforming," a support lead asking "how many refunds did we process last month."

## Features

- Natural-language question -> SQL -> verified execution -> analyzed, grounded answer
- Schema-aware prompting: the LLM sees only relevant tables/columns, with real example values for categorical columns (not just names/types)
- AST-based SQL validation (not string matching) — rejects mutating statements, stacked queries, and Postgres's writable-CTE gotcha
- Read-only database role enforced at the PostgreSQL level, independent of the LLM's behavior
- Deterministic result analysis (ranking, trend, % change) and rule-based chart selection — no LLM arithmetic
- Streamlit chat UI showing the answer, generated SQL, validation/execution status, result table, and chart
- Reproducible synthetic dataset (~43,000 records, fixed seed) and a 32-question evaluation suite with measured (not assumed) accuracy

## Architecture

```text
                     +----------------------+
                     |   Streamlit UI       |
                     |  (chat + details)     |
                     +----------+-----------+
                                |
                                v
                     +----------------------+
                     |  LangChain Agent      |
                     |  (AgentExecutor,      |
                     |   tool-calling loop,  |
                     |   max 6 iterations)   |
                     +----------+-----------+
                                |
             LLM decides which tool to call next
                                |
        +-----------------+----+----+------------------+
        |                 |         |                  |
        v                 v         v                  v
  get_schema          run_sql   create_visualization  (final answer,
  (schema.py:      (validate_  (analysis_tool +        no tool call)
   live intro-      and_execute:  visualization_tool)
   spection +       sqlglot AST
   value hints)      validation
                     -> readonly
                     Postgres role
                     -> deterministic
                     analysis)
                                |
                                v
                     +----------------------+
                     |     PostgreSQL        |
                     |  8 tables, ~43k rows  |
                     |  readonly_user role   |
                     +----------------------+
```

The LLM writes SQL as part of its own reasoning (that's genuinely its job), but every *tool* it can call enforces deterministic safety regardless of what it asked for — `run_sql` always goes through AST-based validation and executes only against the read-only Postgres role, so even a successfully prompt-injected LLM cannot bypass validation. This was verified directly, not just assumed: see [Security](#security).

## Agent Workflow

```text
RECEIVE_QUESTION
     |
     v
LLM calls get_schema(question) -> relevant tables/columns + example values
     |
     v
LLM writes SQL, calls run_sql(sql)
     |
     +--> validate_sql (sqlglot AST): reject if not a single read-only SELECT/CTE,
     |    reject unknown tables/columns, reject dangerous functions
     |
     +--> INVALID --> LLM sees the rejection reason, fixes the query, retries
     |                (bounded by max_iterations=6 -- no unbounded loops)
     |
     v
execute_sql against readonly_user, server-side statement_timeout
     |
     +--> DB ERROR --> structured error returned to LLM, same retry path
     |
     v
analyze_result (deterministic: ranking / trend / % change / totals)
     |
     v
LLM optionally calls create_visualization (own decision, backed by a
deterministic should_visualize() check as a safety net)
     |
     v
LLM produces final natural-language answer, grounded in the real numbers
it received (not re-derived or guessed)
```

This is accurately described as a **controlled agentic workflow with LLM-driven tool selection and deterministic safety/validation steps** — not unrestricted autonomous reasoning, and not a fixed `User -> LLM -> SQL` pipeline either.

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13 | |
| Database | PostgreSQL 18 | Real constraints, window functions, CTEs -- the SQL features the project needs to demonstrate |
| ORM / DB layer | SQLAlchemy 2.0 | Schema definition, live introspection (`sqlalchemy.inspect`), connection/session management |
| Agent framework | LangChain 0.3.x (classic `AgentExecutor`) | Explicitly *not* the 1.x line, which pulls in LangGraph as a transitive dependency -- see [Challenges](#challenges--solutions) |
| LLM | `openai/gpt-oss-20b` via Groq (free tier) | See [Challenges](#challenges--solutions) for why this isn't Llama despite the original plan |
| UI | Streamlit | Chat-style interface, `st.session_state` for conversation history |
| SQL validation | `sqlglot` (AST parsing) | Structural validation immune to comment/case-based string-match bypasses |
| Synthetic data | `Faker` | Realistic names/emails/addresses, fixed seed for reproducibility |
| Visualization | `matplotlib` | Headless (`Agg` backend), rendered via `st.pyplot` |
| Testing | `pytest` | 49 tests across database, validation, tools, agent, and UI layers |

## Database Schema

8 tables, designed as a small retail-analytics star-ish schema centered on `orders`:

```text
customers ----< orders >---- stores ----< employees
                  |
                  +----< order_items >---- products ---- categories
                  |
                  +----< payments
```

- **customers** — one row per customer, with signup date, city/state/country
- **categories** / **products** — product catalog; `products.unit_price`/`cost_price` support margin analysis
- **stores** / **employees** — physical locations grouped by region, staff assigned per store
- **orders** — one row per order; `total_amount` is a denormalized, exactly-computed sum of its line items (cheap aggregation queries, kept consistent by the seed script)
- **order_items** — line items; `unit_price` is a price *snapshot* at sale time, intentionally independent of the product's current price
- **payments** — one payment record per order (method, amount, status)

Every table has primary keys, foreign keys, `CHECK` constraints (e.g. non-negative amounts, valid status enums), and indexes on foreign keys and frequently-filtered columns (`order_date`, `signup_date`, `region`). Full DDL: `app/database/models.py`.

**Data volume** (fixed seed = 42, fully reproducible via `python scripts/seed_database.py --reset`):

| Table | Rows |
|---|---|
| categories | 8 |
| products | 200 |
| stores | 15 |
| employees | ~66 |
| customers | 3,000 |
| orders | 9,000 |
| order_items | ~21,000 |
| payments | 9,000 |
| **Total** | **~43,000** |

Verified live against the database: 0 mismatches between `orders.total_amount` and the actual sum of its `order_items`, 0 mismatches between `payments.amount` and `orders.total_amount`, 0 orphaned rows.

## Tools

| Tool | Purpose | Deterministic parts |
|---|---|---|
| `get_schema` | Return schema text (tables/columns/FKs/example values) relevant to the question | Keyword match + one-hop FK graph expansion, falling back to the full schema when nothing matches |
| `run_sql` | Validate, execute, and analyze a SQL query | AST validation (`sqlglot`), read-only Postgres role, server-side statement timeout, deterministic result analysis |
| `create_visualization` | Create a chart for the current result, if suitable | `should_visualize()` rule (a ranking or trend has something to chart; a single aggregate doesn't) backs up the LLM's own decision |

## Example Queries

```text
"Which product category generated the highest revenue?"
"Show me the top 5 categories by revenue"
"What is monthly revenue for 2025?"
"How many customers are located in California?"
"Which store had the highest total revenue from completed orders?"
"Rank customers by total spend using a window function and show the top 10"
"What is the quarter-over-quarter revenue growth in 2025?"
```

The full 32-question evaluation set, covering every required SQL category, is in `evaluation/questions.json`.

## Evaluation Methodology

`evaluation/questions.json` defines 32 natural-language questions spanning simple aggregation, filtering, joins, multi-table joins, `GROUP BY`, `HAVING`, CTEs, window functions, date filtering, ranking, trend analysis, and comparative analysis. A subset carries a precomputed `expected_value`, calculated directly against the live (fixed-seed, reproducible) dataset, enabling genuine correctness checking rather than just "did it execute."

`app/services/evaluation_service.py` runs every question through the real agent and measures:

- **Valid SQL rate** — did `run_sql` pass AST validation
- **Execution success rate** — the required baseline metric
- **Result correctness** — for questions with a precomputed `expected_value`
- **Schema relevance accuracy** — does `get_relevant_tables()` actually include the tables a question needs, checked against curated `expected_tables`
- **Average latency** per question

Run it yourself: `python evaluation/evaluate.py`. It always prints the real measured numbers — no target is ever hard-coded into the output.

## Evaluation Results

Full 32-question run, before the schema-example-values fix described in [Challenges & Solutions](#challenges--solutions):

| Metric | Result |
|---|---|
| Valid SQL | 32/32 (100.0%) |
| Successful execution | 32/32 (100.0%) |
| Result correctness (7 questions with a precomputed expected value) | 6/7 (85.7%) |
| Schema relevance | 32/32 (100.0%) |
| Average latency | ~19.2s / question |

The one correctness failure (question 5, "How many customers are located in California?") was root-caused, fixed, and individually re-verified to now return the correct value (56, matching a direct SQL count) — see the Challenges section. A full clean 32/32 re-run to confirm system-wide 7/7 correctness after the fix is pending the next daily token-quota reset: this project's own evaluation runs hit Groq's 200,000-tokens/day ceiling for `openai/gpt-oss-20b` twice during development (once from cumulative testing, once again ~30 minutes later after a single test call consumed the last remaining tokens — confirming it's a hard daily cap, not a short rolling window). That's documented honestly here rather than worked around with a fabricated number, and it's also genuine evidence for the [Limitations](#limitations) section below.

Reproduce: `python evaluation/evaluate.py` (writes `evaluation/results.json`).

## Security

- **Read-only database role.** All agent-executed SQL runs against a dedicated `readonly_user` Postgres role that cannot `INSERT`/`UPDATE`/`DELETE`/`DDL` at the database level — verified directly (`readonly_user` denied `CREATE TABLE` with a real `permission denied` error).
- **AST-based validation, not string matching.** `app/tools/validation_tool.py` parses SQL with `sqlglot` and rejects anything that isn't a single, well-formed `SELECT`/`WITH` statement, including nested cases a naive top-level check would miss (Postgres's writable-CTE gotcha: `WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x` still parses as a top-level `SELECT`).
- **Denylisted dangerous functions** (`pg_sleep`, `dblink`, file/network I/O functions).
- **Schema-membership checks** reject queries referencing tables/columns that don't exist, before ever reaching the database.
- **Server-side statement timeout**, set per connection, so Postgres itself kills a runaway query even if the driver is blocked waiting on it (verified against a real ~450M-row cross join).
- **Bounded agent loop** (`max_iterations=6`) — no unbounded retry loops.
- **Prompt-injection resistance verified directly**, not assumed: calling the `run_sql` tool with `"DROP TABLE customers"` is rejected by the validator regardless of how the LLM was prompted to produce it — the safety guarantee lives in the tool, not in the LLM's judgment.

## Why This Is Agentic AI

There's a real difference between three things this project could have been:

1. **Simple LLM-to-SQL**: one LLM call turns a question into SQL, which is executed and returned. No tool selection, no validation loop, no recovery from a bad query.
2. **A deterministic pipeline with an LLM step embedded in it**: a fixed sequence of stages where the LLM is just one interchangeable function call among several hard-coded steps.
3. **This project**: the LLM genuinely decides *which* tools to call and *when* — whether to retrieve schema, whether the SQL needs fixing after a validation failure, whether the result is worth visualizing — within a bounded loop (`AgentExecutor`, `max_iterations=6`) and behind deterministic safety enforcement it cannot override.

That third property is what makes it agentic rather than a workflow: the control flow isn't fully fixed in code, it's a real decision the model makes per-question, based on what the tools return. At the same time, this is deliberately **not** described as unrestricted autonomous reasoning — every consequential action (SQL execution) passes through deterministic validation the LLM cannot bypass, exactly because LLM judgment alone is not a sufficient safety boundary for a system with real database access.

## Challenges & Solutions

**Free-tier LLM provider volatility.** The original plan (per the submitted resume) was a Llama-family model. During development, three independent providers — Groq, Cerebras, and OpenRouter — were each verified live to have deprecated or pulled free access to their Llama chat models within the same week. Rather than keep chasing a moving target, the project uses `openai/gpt-oss-20b` via Groq, verified working end-to-end (chat, schema-aware SQL generation, tool calling). This is documented honestly rather than mislabeled: the resume's "Llama-family" framing no longer matches the implementation. See `docs/interview_notes.md` for the full timeline and how to address this directly in an interview. The provider is env-configurable specifically because this kind of volatility is real and current, not hypothetical.

**Schema-aware prompting without example values causes wrong SQL.** The evaluation suite caught a real bug: asked "how many customers are in California," the LLM wrote `WHERE state = 'California'`, but the seeded data stores state as a 2-letter abbreviation (`'CA'`). The schema text showed column names and types but never example values. Fixed by sampling distinct values for text columns below a cardinality threshold (60 -- wide enough for genuine categorical columns like US state abbreviations, narrow enough to exclude near-unique columns like city or email) and including a few as hints in the schema text.

**Trend/ranking answers can hallucinate missing rows.** Early testing surfaced a subtler bug: a 12-month revenue trend question came back with November and December showing *identical* revenue -- statistically near-impossible given the seed data's seasonal weighting. The `run_sql` tool was only returning a 5-row sample plus the trend's period *count*, not its actual per-period values, so the LLM fabricated the months it never received. Fixed by returning full trend/ranked values, and all rows (not just a sample) below a 30-row cap, so the model always has the real numbers it needs to answer accurately.

## Limitations

- Column-level SQL validation is schema-membership-based, not fully alias/type-resolved -- a column that's real but referenced on the wrong table (e.g. `customers.total_amount`) isn't caught by the validator, only by execution against Postgres. This is a deliberate scope boundary, not an oversight: full static binding would need a much heavier validator for a class of error the database already rejects reliably.
- The free-tier LLM has a daily token quota (Groq, `openai/gpt-oss-20b`: 200,000 tokens/day at time of writing). Heavy interactive use plus running the full evaluation suite in the same day can exhaust it -- the system fails safely when this happens (structured error, no crash), but it is a real usage ceiling worth knowing about.
- Schema relevance filtering is keyword-based rather than embedding/semantic search -- appropriate at 8 tables, would need revisiting at real scale (see below).
- No conversation memory across questions in the current UI -- each question is answered independently; the chat history is display-only.

## Future Scope

- Multi-turn follow-up questions ("now break that down by region") using conversation-aware schema/context carry-over.
- Semantic/embedding-based schema relevance for larger schemas, where keyword matching would stop scaling.
- A second, larger model as a fallback path when the primary free-tier model's daily quota is exhausted.
- Query result caching for repeated/similar questions.
- Expected-value coverage for more of the 32 evaluation questions (currently a subset; the rest are open-ended enough that a single canonical numeric answer isn't well-defined).

## Installation

Prerequisites: Python 3.11+, PostgreSQL, Git.

```bash
git clone <this-repo>
cd db-analyst-agent
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e . --no-deps
pip install -r requirements.txt
```

## Environment Setup

Copy `.env.example` to `.env` and fill in real values:

```text
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-20b
LLM_API_KEY=<your Groq API key, from console.groq.com -- free, no credit card>

DATABASE_URL=postgresql+psycopg://app_user:<password>@localhost:5432/db_analyst_agent
READONLY_DATABASE_URL=postgresql+psycopg://readonly_user:<password>@localhost:5432/db_analyst_agent
```

`app_user` needs table-creation rights on the target database; `readonly_user` should be granted `SELECT`-only (see `docs/architecture.md` for the exact role/grant setup). `.env` is gitignored and must never be committed.

## Running

```bash
# 1. Create the schema
python scripts/create_database.py

# 2. Seed ~43,000 synthetic records (add --reset to wipe and reseed)
python scripts/seed_database.py

# 3. Launch the app
streamlit run frontend/streamlit_app.py
```

## Testing

```bash
pytest tests/ -v
```

49 tests across database integrity, SQL validation (21 cases covering the full reject matrix plus injection edge cases), tool execution, the live agent (skipped automatically if `LLM_API_KEY` isn't set), and the Streamlit UI (via Streamlit's official headless `AppTest` harness).

## Project Structure

```text
db-analyst-agent/
├── app/
│   ├── agent/          # LangChain agent, LLM client, prompts
│   ├── tools/           # schema / SQL validation+execution / analysis / visualization
│   ├── database/        # SQLAlchemy models, connection, live schema introspection, seeding
│   ├── services/        # evaluation orchestration
│   └── config.py
├── frontend/
│   └── streamlit_app.py
├── evaluation/           # 32-question benchmark, runner, measured results
├── tests/                # 49 tests across every layer
├── scripts/              # one-shot DB create/seed scripts
├── docs/                 # architecture notes, interview prep
├── .env.example
└── requirements.txt
```

## Author

Disha Jain
