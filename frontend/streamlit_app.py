"""Streamlit UI: query input, generated SQL, results, chart, execution status."""

from __future__ import annotations

import streamlit as st

from app.agent.agent import AgentAnswer, ask
from app.database.connection import check_connection

st.set_page_config(page_title="Database Analyst Agent", page_icon="\U0001f4ca", layout="wide")

st.title("Database Analyst Agent")
st.caption("Ask questions about the retail analytics database in plain English.")

EXAMPLE_QUESTIONS = [
    "Which product category generated the highest revenue?",
    "Show me the top 5 customers by total spend",
    "What is monthly revenue for 2025?",
    "Which store has the best performance this year?",
]

if "history" not in st.session_state:
    st.session_state.history: list[tuple[str, AgentAnswer | None, str | None]] = []

# Fail clearly up front if Postgres is unreachable, instead of crashing mid-query.
healthy, db_error = check_connection()
if not healthy:
    st.error(f"Database is unavailable: {db_error}")
    st.stop()

with st.sidebar:
    st.subheader("Example questions")
    for example in EXAMPLE_QUESTIONS:
        if st.button(example, width="stretch"):
            st.session_state["pending_question"] = example

question = st.chat_input("Ask a question about the data...")
if not question and "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")

if question:
    with st.spinner("Working on it..."):
        try:
            answer = ask(question)
            st.session_state.history.append((question, answer, None))
        except Exception as exc:
            st.session_state.history.append((question, None, str(exc)))

for past_question, answer, error in reversed(st.session_state.history):
    with st.chat_message("user"):
        st.write(past_question)
    with st.chat_message("assistant"):
        if error is not None:
            st.error(f"Something went wrong answering this question: {error}")
            continue

        st.write(answer.answer)

        with st.expander("Execution details", expanded=False):
            tools_line = " -> ".join(answer.tools_used) if answer.tools_used else "none"
            st.markdown(f"**Tools used:** {tools_line}")

            if answer.sql:
                st.markdown("**Generated SQL:**")
                st.code(answer.sql, language="sql")
                st.markdown(f"**Validation:** {'Passed' if answer.validation_passed else 'Failed'}")

            if answer.execution is not None:
                if answer.execution.success:
                    st.markdown(f"**Execution:** Successful ({answer.execution.elapsed_ms:.0f} ms)")
                    if answer.execution.rows:
                        st.dataframe(answer.execution.rows, width="stretch")
                    else:
                        st.caption("Query returned 0 rows.")
                else:
                    st.markdown(f"**Execution:** Failed - {answer.execution.error}")

        if answer.chart is not None:
            st.pyplot(answer.chart)
