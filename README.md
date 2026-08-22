# Database Analyst Agent

An **agentic natural-language-to-SQL analyst for PostgreSQL**. Ask a business question in plain English and get a **grounded answer, validated SQL, execution results, and a visualization when useful**.

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
* [Demo](#demo)
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
* [Author](#author)

---

## Overview

**Database Analyst Agent** enables non-technical users to query a PostgreSQL database using natural language.

For example:

> *"Which product category generated the highest revenue?"*

The system translates the question into SQL, validates the generated query, executes it safely against a PostgreSQL database, analyzes the result, and returns a grounded natural-language answer.

Unlike a basic:

```text
LLM → SQL → Database
```

pipeline, this project uses a **controlled agentic workflow** where the LLM decides which tools to call while deterministic safeguards control database execution.

This separation allows the system to benefit from LLM reasoning without giving the model unrestricted access to the database.

---

## Demo

The Streamlit interface provides a conversational environment where users can ask analytical questions in plain English and receive grounded insights directly from the database.

For each question, the system can provide:

* A grounded natural-language answer
* Generated and validated SQL
* Database execution results
* Automatic visualization when appropriate

### Application Interface

<p align="center">
  <img src="assets/database-analyst-agent-demo.png" alt="Database Analyst Agent Interface" width="900"/>
</p>

### Query Analysis

The agent converts natural-language questions into validated SQL, executes them safely, and returns the generated query alongside the analysis.

<p align="center">
  <img src="assets/query-analysis-demo.png" alt="SQL Query Analysis Demo" width="900"/>
</p>

### Data Visualization

When query results are suitable for visualization, the system can automatically generate a chart to make the results easier to interpret.

<p align="center">
  <img src="assets/visualization-demo.png" alt="Database Analyst Agent Visualization" width="900"/>
</p>

---

## Key Features

* **Natural Language to SQL** — converts business questions into executable PostgreSQL queries
* **Schema-Aware Generation** — provides the agent with relevant tables, columns, relationships, and categorical value hints
* **AST-Based SQL Validation** — validates generated queries using `sqlglot`
* **Read-Only Database Access** — prevents the agent from modifying database data or schema
* **Automatic Retry** — allows the agent to correct validation or execution errors
* **Deterministic Analysis** — performs ranking, trend, percentage-change, and total calculations outside the LLM
* **Automatic Visualization** — generates appropriate charts when query results benefit from visualization
* **Conversational UI** — provides an interactive Streamlit-based interface
* **Reproducible Dataset** — includes scripts for generating approximately 43,000 synthetic rows
* **Evaluation Benchmark** — evaluates the system against 32 analytical questions
* **Automated Testing** — includes 49 tests covering core system behavior

---

## Architecture

<p align="center">
  <img src="assets/architecture.png" alt="Database Analyst Agent Architecture" width="850"/>
</p>

The architecture separates **LLM reasoning** from **database safety and deterministic computation**.

The LLM is responsible for:

* Understanding the user's analytical question
* Selecting the appropriate tools
* Generating SQL
* Interpreting grounded results

Deterministic components are responsible for:

* SQL validation
* Database access control
* Query execution
* Numerical analysis
* Visualization selection

This separation ensures that database safety does not depend on the behavior of the LLM.

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

The agent operates through a LangChain tool-calling loop and is bounded by:

```python
max_iterations = 6
```

This prevents uncontrolled retry loops while still allowing the model to recover from SQL validation or execution errors.

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

## Database Schema

The PostgreSQL database contains **8 relational tables** with approximately **43,000 rows** of reproducible synthetic data.

The schema represents an analytical business dataset designed to support questions involving:

* Aggregations
* Filtering
* Multi-table joins
* Revenue analysis
* Customer analysis
* Product/category analysis
* Ranking
* Date-based analysis
* Trend analysis
* Comparative analysis

Schema information is dynamically retrieved by the agent rather than hard-coded into the prompt.

For suitable low-cardinality categorical columns, representative values are also provided to the model.

For example, instead of only knowing:

```text
state VARCHAR
```

the agent may receive context such as:

```text
state: CA, NY, TX, FL, ...
```

This reduces SQL errors caused by differences between natural-language values and actual database values.

---

## Security

SQL generated by an LLM is treated as **untrusted input**.

The execution layer therefore uses multiple independent safeguards:

* Dedicated PostgreSQL `readonly_user`
* AST-based validation using `sqlglot`
* Single-query enforcement
* Mutating SQL rejection
* DDL rejection
* Writable CTE protection
* Dangerous function denylist
* Schema-membership validation
* Server-side statement timeout
* Bounded agent execution
* Prompt-injection resistance tests

For example, a generated query such as:

```sql
DROP TABLE customers;
```

is rejected by the execution layer regardless of why the LLM generated it.

Database safety therefore does not rely solely on prompting the model to behave correctly.

---

## Evaluation

The project includes a **32-question evaluation suite** covering:

* Aggregations
* Filtering
* Joins
* Multi-table queries
* CTEs
* Window functions
* Ranking
* Date filtering
* Trend analysis
* Comparative analysis

### Evaluation Results

| Metric               |                 Result |
| -------------------- | ---------------------: |
| Valid SQL            |       **32/32 (100%)** |
| Successful Execution |       **32/32 (100%)** |
| Result Correctness*  |        **6/7 (85.7%)** |
| Schema Relevance     |       **32/32 (100%)** |
| Average Latency      | **~19.2 sec/question** |

*The single correctness failure exposed a schema-context issue that was subsequently fixed and individually re-verified.

The evaluation suite is designed to test not only whether SQL executes, but also whether the agent retrieves appropriate schema context and produces analytically useful results.

---

## Challenges & Solutions

### 1. Schema Values vs. Schema Structure

**Challenge:**
The model could know that a `state` column existed without knowing that the dataset stored California as `CA` rather than `California`.

**Solution:**
Schema introspection was enhanced to provide representative values for suitable low-cardinality categorical columns.

This gives the LLM additional grounding without placing the entire database contents in the prompt.

### 2. Hallucination from Partial Results

**Challenge:**
Returning only a small sample of trend results could cause the LLM to describe periods or values it had never actually received.

**Solution:**
Trend and ranking analysis now provides the actual underlying values required to construct the answer.

Important numerical calculations are handled deterministically rather than relying entirely on LLM arithmetic.

### 3. Free-Tier LLM Availability

**Challenge:**
Free model availability and provider limits changed during development.

**Solution:**
The LLM layer was kept provider-configurable.

The current implementation uses:

```text
openai/gpt-oss-20b
```

through Groq.

This design makes it easier to switch providers or models without restructuring the entire application.

---

## Limitations

The current implementation has several limitations:

* No multi-turn conversational context between analytical questions
* Keyword-based schema relevance retrieval
* Column validation does not perform complete static alias/type resolution
* Free-tier LLM usage is subject to provider token and rate limits
* Current evaluation correctness coverage uses expected values for only a subset of questions
* Designed primarily for PostgreSQL rather than multiple SQL dialects

These limitations represent areas where the system can be extended rather than hidden implementation constraints.

---

## Future Scope

Potential improvements include:

* Multi-turn analytical follow-up questions
* Semantic schema retrieval for larger databases
* LLM provider/model fallback
* Query-result caching
* Expanded expected-value evaluation coverage
* Support for additional SQL databases
* More advanced visualization selection
* Improved schema retrieval for large enterprise databases
* Conversation-aware analytical sessions

---

## Getting Started

### Prerequisites

Make sure the following are installed:

* Python 3.11+
* PostgreSQL
* Git

### 1. Clone the Repository

```bash
git clone https://github.com/DishaJn2/Database-analyst-agent.git
cd Database-analyst-agent
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it.

**Windows:**

```bash
.venv\Scripts\activate
```

**macOS/Linux:**

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -e . --no-deps
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file using `.env.example` as the template.

Configure the required PostgreSQL and LLM credentials.

Example:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/database_name
GROQ_API_KEY=your_groq_api_key
```

> **Important:** Never commit your actual `.env` file or API keys to GitHub.

### 5. Create and Seed the Database

```bash
python scripts/create_database.py
python scripts/seed_database.py
```

### 6. Run the Application

```bash
streamlit run frontend/streamlit_app.py
```

The Streamlit interface will open in your browser.

You can then ask analytical questions about the database in natural language.

---

## Testing

Run the complete test suite with:

```bash
pytest tests/ -v
```

The project currently contains **49 automated tests** covering:

* Database integrity
* SQL validation
* Tool execution
* Agent behavior
* Security safeguards
* Streamlit UI behavior

---

## Project Structure

```text
Database-analyst-agent/
│
├── app/
│   ├── agent/
│   ├── tools/
│   ├── database/
│   ├── services/
│   └── config.py
│
├── frontend/
│   └── streamlit_app.py
│
├── evaluation/
│
├── scripts/
│
├── tests/
│
├── data/
│
├── assets/
│   ├── architecture.png
│   ├── database-analyst-agent-demo.png
│   ├── query-analysis-demo.png
│   └── visualization-demo.png
│
├── .env.example
├── .gitignore
├── LICENSE
├── pyproject.toml
├── README.md
└── requirements.txt
```

The `app/` package contains the core agent, database, service, and tool logic, while the Streamlit application is maintained separately under `frontend/`.

Development-only documentation is intentionally excluded from the public repository.

---
