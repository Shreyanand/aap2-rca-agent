"""Tests for GitHub workload-path fetching."""

from unittest.mock import Mock

from rca.analysis.github_fetcher import GitHubAnalyzer, parse_task_path


def test_unrecognized_task_path_is_skipped_without_aborting(tmp_path) -> None:
    github = Mock()
    analyzer = GitHubAnalyzer("123", tmp_path, github)
    task_path = "/tmp/unrecognized/workload.yml:42"
    location = parse_task_path(task_path)

    result = analyzer.fetch_workload_code(
        {
            "workload_code": [
                {
                    "purpose": "failed_task_code",
                    "file_path": location["file_path"],
                    "repos_to_try": location["repos_to_try"],
                }
            ]
        }
    )

    assert location["repos_to_try"] == []
    assert result == {"failed_task_code": None}
    github.get_file_content.assert_not_called()
    github.search_file.assert_not_called()
