import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from data_gov_tw.__main__ import app

runner = CliRunner()


def test_clean_subcommand():
    """clean subcommand should call shared.fetcher.clean and print results."""
    with patch("data_gov_tw.__main__.clean") as mock_clean:
        mock_clean.return_value = ["datasets/", "etags.json"]
        result = runner.invoke(app, ["clean"])

    assert result.exit_code == 0
    assert "datasets/" in result.output


def test_clean_subcommand_nothing():
    """clean subcommand should print message when nothing to delete."""
    with patch("data_gov_tw.__main__.clean") as mock_clean:
        mock_clean.return_value = []
        result = runner.invoke(app, ["clean"])

    assert result.exit_code == 0
    assert "乾淨" in result.output


def test_score_subcommand():
    """score subcommand should call score_provider and print results."""
    mock_scores = {
        "provider": "data.gov.tw",
        "slug": "data_gov_tw",
        "scored_at": "2026-01-01T00:00:00+00:00",
        "datasets": [
            {"id": "export-json", "name": "JSON匯出", "declared_format": "json",
             "detected_format": "json", "star_score": 3,
             "stars": {"available_online": True, "machine_readable": True, "open_format": True},
             "issues": []},
        ],
    }
    with patch("data_gov_tw.__main__.score_provider", return_value=mock_scores):
        with patch("data_gov_tw.__main__.Path") as MockPath:
            mock_pkg_dir = MockPath.return_value.parent
            mock_pkg_dir.__truediv__ = lambda self, x: Path("/tmp/datasets") if x == "datasets" else Path(f"/tmp/{x}")
            MockPath.cwd.return_value = Path("/tmp")
            result = runner.invoke(app, ["score"])

    assert result.exit_code == 0


def test_crawl_with_only_flag():
    """--only flag should be passed to fetch_all."""
    with patch("data_gov_tw.__main__.fetch_all", new_callable=AsyncMock) as mock_fetch:
        result = runner.invoke(app, ["--only", "export-json.json"])

    mock_fetch.assert_called_once()


def test_crawl_with_no_cache_flag():
    """--no-cache flag should be passed to fetch_all."""
    with patch("data_gov_tw.__main__.fetch_all", new_callable=AsyncMock) as mock_fetch:
        result = runner.invoke(app, ["--only", "export-json.json", "--no-cache"])

    mock_fetch.assert_called_once()
