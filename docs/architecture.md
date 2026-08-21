# Architecture

Deeper implementation reference than the README's overview. See the README for the high-level diagram, agent workflow, and tech-stack rationale.

## PostgreSQL role setup

The application uses two Postgres roles, created once during Phase 4 setup (not by the application itself):

```sql
CREATE ROLE app_user WITH LOGIN PASSWORD '<generated>';
CREATE ROLE readonly_user WITH LOGIN PASSWORD '<generated>';
CREATE DATABASE db_analyst_agent OWNER app_user;
GRANT CONNECT ON DATABASE db_analyst_agent TO readonly_user;

-- inside db_analyst_agent:
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES FOR ROLE app_user IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
```

The `ALTER DEFAULT PRIVILEGES` line is what makes this durable: any table `app_user` creates later (i.e. every table in `app/database/models.py`, applied via `scripts/create_database.py`) automatically grants `SELECT` to `readonly_user` the moment it's created, with no manual per-table grant step. Verified live: `readonly_user` can `SELECT` from every table but is denied `CREATE TABLE` with a real `permission denied for schema public` error.

- `app_user` (read-write): used only by `scripts/create_database.py` and `scripts/seed_database.py`. Never used by the agent.
- `readonly_user` (read-only): the *only* role `app/tools/sql_tool.py`'s `execute_sql()` connects as. This is the database-level backstop behind SQL validation -- even if validation were somehow bypassed, the role itself cannot mutate data.

## Why two engines, not one

`app/database/connection.py` defines `engine` (read-write, `app_user`) and `readonly_engine` (read-only, `readonly_user`) as separate SQLAlchemy engines, each with their own connection pool. The agent's tools are only ever given `readonly_engine`. This is a deliberate structural choice, not just a naming convention: a future contributor adding a new tool has to explicitly import the read-only engine to run any query, making an accidental read-write connection in agent-reachable code a visible, reviewable change rather than a silent default.

## Provider-agnostic LLM client

`app/agent/llm.py` reads `LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY` from the environment rather than hard-coding a vendor SDK. This turned out to matter in practice, not just in theory: see `docs/interview_notes.md` for the full timeline of three independent free-tier Llama providers dead-ending during development, and how the env-configurable design made the eventual provider switch a one-file change instead of a rewrite.

## Schema introspection vs. ORM models

`app/database/schema.py` builds the LLM-facing schema description by introspecting the *live* database (`sqlalchemy.inspect`), not by reading `app/database/models.py`. If the two ever drifted (e.g. a manual `ALTER TABLE` outside the ORM), the prompt would still reflect reality. The same module also samples distinct values for low-cardinality text columns (see the README's Challenges section) -- this requires live data, which is another reason introspection beats reading static model definitions.

## Evaluation results storage

`evaluation/results.json` is a generated artifact (via `python evaluation/evaluate.py`) but is committed to the repository deliberately: it's the evidence behind the README's "Evaluation Results" numbers, and per the build spec's rule against fabricating metrics, that evidence needs to be inspectable, not just asserted in prose.
