"""Tests for storing batch reports with psycopg2 mapping-style rows."""

from unittest.mock import MagicMock

from psycopg2 import sql

from rca.batch import store_report


def _connection_and_cursor():
    connection = MagicMock()
    cursor_context = MagicMock()
    cursor = cursor_context.__enter__.return_value
    cursor.connection = connection
    connection.cursor.return_value = cursor_context
    return connection, cursor


def test_find_match_accepts_mapping_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        store_report,
        "known_issue_active_sql",
        lambda _conn, *, table: sql.SQL("TRUE"),
    )
    cursor = MagicMock()
    cursor.connection = MagicMock()
    cursor.fetchall.return_value = [
        {"id": 42, "root_cause_summary": "A worker ran out of capacity"}
    ]

    match_id = store_report.find_match(
        cursor,
        "results",
        {
            "job_id": "123",
            "root_cause_category": "infrastructure",
            "catalog_item": "widget",
            "root_cause_summary": "A worker ran out of capacity",
        },
    )

    assert match_id == 42


def test_store_report_reads_mapping_insert_result(monkeypatch) -> None:
    monkeypatch.setattr(
        store_report,
        "known_issue_active_sql",
        lambda _conn, *, table: sql.SQL("TRUE"),
    )
    connection, cursor = _connection_and_cursor()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = {"id": 55}

    assert store_report.store_report(
        connection,
        {"results_table": "results", "source_table": "events"},
        {
            "batch_id": "batch_test",
            "job_summaries": [
                {
                    "job_id": "123",
                    "status": "analyzed",
                    "root_cause_category": "infrastructure",
                    "root_cause_summary": "A worker ran out of capacity",
                    "confidence": "high",
                    "catalog_item": "widget",
                }
            ],
        },
    )

    assert (55, "123") in [call.args[1] for call in cursor.execute.call_args_list]
    connection.commit.assert_called_once_with()


def test_link_intra_batch_dupes_reads_mapping_result_row() -> None:
    connection, cursor = _connection_and_cursor()
    cursor.fetchone.return_value = {"aap2_job_results_fk_id": 91}

    linked = store_report.link_intra_batch_dupes(
        connection,
        {"source_table": "events"},
        [{"job_id": "222", "representative_job_id": "111"}],
    )

    assert linked == 1
    assert (91, "222") in [call.args[1] for call in cursor.execute.call_args_list]
    connection.commit.assert_called_once_with()


def test_store_report_assigns_pattern_id_from_result_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        store_report,
        "known_issue_active_sql",
        lambda _conn, *, table: sql.SQL("TRUE"),
    )
    connection, cursor = _connection_and_cursor()
    cursor.fetchall.return_value = []
    cursor.fetchone.side_effect = [{"id": 12}, {"id": 11}]
    report = {
        "batch_id": "batch_test",
        "job_summaries": [
            {"job_id": "123", "status": "analyzed", "confidence": "high"},
            {"job_id": "124", "status": "analyzed", "confidence": "high"},
        ],
        "cross_job_patterns": [
            {
                "pattern": "worker timeout",
                "jobs": ["123", "124"],
                "description": "Both jobs time out in worker 7.",
                "source": "current_batch",
            }
        ],
    }

    assert store_report.store_report(
        connection,
        {"results_table": "results", "source_table": "events"},
        report,
    )

    assert report["job_summaries"][0]["result_id"] == 12
    assert report["job_summaries"][1]["result_id"] == 11
    assert report["cross_job_patterns"][0]["pattern_id"] == "11"
    connection.commit.assert_called_once_with()


def test_store_cross_patterns_persists_derived_pattern_id() -> None:
    connection, cursor = _connection_and_cursor()
    report = {
        "batch_id": "batch_test",
        "job_summaries": [
            {"job_id": "123", "status": "analyzed", "result_id": 42},
            {"job_id": "124", "status": "analyzed", "result_id": 43},
        ],
        "cross_job_patterns": [
            {
                "pattern": "worker timeout",
                "jobs": ["123", "124"],
                "description": "Both jobs time out in worker 7.",
                "source": "current_batch",
                "pattern_id": "42",
            }
        ],
    }

    store_report.store_cross_patterns(connection, {"results_table": "results"}, report)

    execute_params = [call.args[1] for call in cursor.execute.call_args_list]
    assert ("42", "Both jobs time out in worker 7.", 42) in execute_params
    assert ("42", "Both jobs time out in worker 7.", 43) in execute_params
    connection.commit.assert_called_once_with()
