"""Tests for GitHub workload-path fetching."""

from unittest.mock import Mock

import pytest

from rca.analysis.github_fetcher import (
    GitHubAnalyzer,
    GitHubAuthenticationError,
    GitHubClient,
    parse_task_path,
)


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


def test_github_client_raises_authentication_error_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock(status_code=401)
    monkeypatch.setattr("rca.analysis.github_fetcher.requests.get", Mock(return_value=response))

    with pytest.raises(GitHubAuthenticationError, match="authentication failed"):
        GitHubClient("invalid-token").get_file_content("owner", "repo", "path.yaml")
