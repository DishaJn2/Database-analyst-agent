"""Tests: the Streamlit UI renders and completes a real question end-to-end.

Uses Streamlit's official headless AppTest harness rather than a browser.
Makes a real LLM call for the interaction test, so it's skipped without a
configured key, same as tests/test_agent.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.config import settings

APP_PATH = str(Path(__file__).resolve().parent.parent / "frontend" / "streamlit_app.py")


def test_initial_render_has_no_exceptions() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception
    assert at.title[0].value == "Database Analyst Agent"


@pytest.mark.skipif(not settings.llm_api_key, reason="LLM_API_KEY not configured; skipping live UI test")
def test_submitting_a_question_renders_answer_sql_and_table() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    at.chat_input[0].set_value("How many customers do we have?").run()

    assert not at.exception
    assert len(at.chat_message) == 2
    assert any("3,000" in m.value or "3000" in m.value for m in at.markdown)
    assert at.code[0].language == "sql"
    assert len(at.dataframe) == 1
