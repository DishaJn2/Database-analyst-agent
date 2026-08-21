# Database Analyst Agent

An agentic natural-language-to-SQL analyst for PostgreSQL. Ask a business question in plain English and get a **grounded answer, validated SQL, execution results, and a visualization when useful**.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python\&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql\&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-Agent-1C3C3C?logo=langchain\&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-GPT--OSS--20B-F55036)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit\&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy\&logoColor=white)
![Pytest](https://img.shields.io/badge/Tests-Pytest-0A9EDC?logo=pytest\&logoColor=white)

---

## Table of Contents

* [Overview](#overview)
* [Key Features](#key-features)
* [Architecture](#architecture)
* [Agent Workflow](#agent-workflow)
* [Tech Stack](#tech-stack)
* [Database Schema](#database-schema)
* [Security](#security)
* [Evaluation](#evaluation)
* [Challenges & Solutions](#challenges--solutions)
* [Limitations](#limitations)
* [Future Scope](#future-scope)
* [Getting Started](#getting-started)
* [Testing](#testing)
* [Project Structure](#project-structure)

---

## Overview

Database Analyst Agent lets non-technical users ask questions such as:

> *"Which product category generated the highest revenue?"*

The system translates the question into SQL, validates the generated query, executes it safely against a PostgreSQL database, analyzes the result, and returns a grounded natural-language answer.

Unlike a basic **LLM → SQL → Database** pipeline, this project uses a controlled agentic workflow where the LLM decides which tools to call while deterministic safeguards control database execution.

---

## Key Features

* Natural-language questions → SQL → validated execution → grounded answers
* Schema-aware SQL generation with real categorical value hints
* AST-based SQL validation using `sqlglot`
* PostgreSQL-level read-only database access
* Automatic retry after validation or execution errors
* Deterministic ranking, trend, percentage-change, and total calculations
* Rule-backed automatic chart generation
* Streamlit conversational interface
* ~43,000-row reproducible synthetic dataset
* 32-question evaluation benchmark
* 49 automated tests

---

## Architecture

```text
                     +----------------------+
                     |     Streamlit UI     |
                     |   Chat + SQL + Chart |
                     +----------+-----------+
                                |
                                v
                     +----------------------+
                     |   LangChain Agent    |
                     |   Tool-Calling Loop  |
                     +----------+-----------+
                                |
                     LLM selects next action
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
     get_schema              run_sql          create_visualization
                                |
                         SQLGlot Validation
                                |
                         Read-Only DB Role
                                |
                      Deterministic Analysis
                                |
                                v
                     +----------------------+
                     |      PostgreSQL      |
                     |  8 Tables / ~43K Rows|
                     +----------------------+
```

The LLM is responsible for **reasoning, SQL generation, and tool selection**. Database safety is enforced separately by deterministic tools that the model cannot bypass.

---

## Tech Stack

| Technology                                                                                         | Purpose                                 |
| -------------------------------------------------------------------------------------------------- | --------------------------------------- |
| ![Python](https://img.shields.io/badge/-Python_3.13-3776AB?logo=python\&logoColor=white)           | Core application and agent logic        |
| ![PostgreSQL](https://img.shields.io/badge/-PostgreSQL_18-4169E1?logo=postgresql\&logoColor=white) | Relational analytics database           |
| ![LangChain](https://img.shields.io/badge/-LangChain-1C3C3C?logo=langchain\&logoColor=white)       | Agent and tool orchestration            |
| ![Groq](https://img.shields.io/badge/-Groq-F55036)                                                 | LLM inference                           |
| ![Streamlit](https://img.shields.io/badge/-Streamlit-FF4B4B?logo=streamlit\&logoColor=white)       | Interactive chat UI                     |
| ![SQLAlchemy](https://img.shields.io/badge/-SQLAlchemy-D71F00?logo=sqlalchemy\&logoColor=white)    | Database layer and schema introspection |
| ![SQLGlot](https://img.shields.io/badge/-SQLGlot-333333)                                           | AST-based SQL validation                |
| ![Matplotlib](https://img.shields.io/badge/-Matplotlib-11557C)                                     | Result visualization                    |
| ![Pytest](https://img.shields.io/badge/-Pytest-0A9EDC?logo=pytest\&logoColor=white)                | Automated testing                       |
| ![Faker](https://img.shields.io/badge/-Faker-555555)                                               | Synthetic data generation               |

---

## Agent Workflow

```text
User Question
      |
      v
Get Relevant Schema
      |
      v
LLM Generates SQL
      |
      v
AST Validation
      |
      +---- Invalid ----> Agent receives error
      |                         |
      |                         v
      |                    Fix & Retry
      |
      v
Read-Only PostgreSQL Execution
      |
      v
Deterministic Result Analysis
      |
      v
Optional Visualization
      |
      v
Grounded Natural-Language Answer
```

The agent is bounded by `max_iterations=6`, preventing uncontrolled retry loops.

---

## Security

SQL generated by an LLM is treated as **untrusted input**.

The execution layer therefore uses multiple independent safeguards:

* Dedicated PostgreSQL `readonly_user`
* AST-based validation with `sqlglot`
* Single-query enforcement
* Mutating SQL and DDL rejection
* Writable CTE protection
* Dangerous function denylist
* Schema-membership validation
* Server-side statement timeout
* Bounded agent execution
* Directly tested prompt-injection resistance

For example:

```sql
DROP TABLE customers;
```

is rejected by the execution layer regardless of why the LLM generated it.

---

## Evaluation

The project includes a **32-question evaluation suite** covering aggregations, filtering, joins, multi-table queries, CTEs, window functions, ranking, date filtering, trend analysis, and comparative analysis.

| Metric               |                 Result |
| -------------------- | ---------------------: |
| Valid SQL            |       **32/32 (100%)** |
| Successful Execution |       **32/32 (100%)** |
| Result Correctness*  |        **6/7 (85.7%)** |
| Schema Relevance     |       **32/32 (100%)** |
| Average Latency      | **~19.2 sec/question** |

*The single correctness failure exposed a schema-context issue that was subsequently fixed and individually re-verified.

---

## Challenges & Solutions

### Schema values vs. schema structure

**Challenge:** The model knew that a `state` column existed but didn't know the dataset stored California as `CA` rather than `California`.

**Solution:** Schema introspection was enhanced to provide representative values for suitable low-cardinality categorical columns.

### Hallucination from partial results

**Challenge:** Returning only a small sample of trend results could cause the LLM to describe periods it had never received.

**Solution:** Trend and ranking analysis now provides the actual underlying values needed to construct the answer.

### Free-tier LLM availability

**Challenge:** Free model availability changed during development.

**Solution:** The LLM layer was kept provider-configurable, while the current implementation uses `openai/gpt-oss-20b` through Groq.

---

## Limitations

* No multi-turn conversational context between analytical questions
* Keyword-based schema relevance retrieval
* Column validation does not perform complete static alias/type resolution
* Free-tier LLM usage is subject to provider token limits
* Current evaluation correctness coverage uses expected values for only a subset of questions

---

## Future Scope

* Multi-turn analytical follow-up questions
* Semantic schema retrieval for larger databases
* LLM provider/model fallback
* Query-result caching
* Expanded expected-value evaluation coverage

---

## Getting Started

### Prerequisites

* Python 3.11+
* PostgreSQL
* Git

```bash
git clone <this-repo>
cd db-analyst-agent

python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -e . --no-deps
pip install -r requirements.txt
```

Create `.env` from `.env.example` and configure your database and LLM credentials.

Then:

```bash
python scripts/create_database.py
python scripts/seed_database.py
streamlit run frontend/streamlit_app.py
```

---

## Testing

Run the complete test suite:

```bash
pytest tests/ -v
```

The project currently contains **49 tests** covering database integrity, SQL validation, tool execution, agent behavior, and the Streamlit UI.

---

## Project Structure

```text
db-analyst-agent/
├── app/
│   ├── agent/
│   ├── tools/
│   ├── database/
│   ├── services/
│   └── config.py
├── frontend/
│   └── streamlit_app.py
├── evaluation/
├── tests/
├── scripts/
├── docs/
├── .env.example
└── requirements.txt
```

---

## Author

**Disha Jain**
