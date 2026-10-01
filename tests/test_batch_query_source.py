"""Tests for selecting only failed, unprocessed source jobs."""

from unittest.mock import MagicMock

from rca.batch.query_source_db import query_job_ids


def test_query_job_ids_returns_rows_and_applies_filters() -> None:
    connection = MagicMock()
    cursor_context = MagicMock()
    cursor = cursor_context.__enter__.return_value
    cursor.fetchall.return_value = [{"job_id": 123}, {"job_id": 456}]
    connection.cursor.return_value = cursor_context

    assert query_job_ids(connection, "aap2_events", since="2026-09-30 12:00:00", limit=15) == [123, 456]

    query, params = cursor.execute.call_args.args
    rendered = str(query)
    assert "ai_processed IS NULL OR ai_processed = FALSE" in rendered
    assert "job_finished >= %s" in rendered
    assert params == ["2026-09-30 12:00:00", 15]
