from unittest.mock import ANY, AsyncMock, patch

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


def test_crawl_with_only_flag():
    """--only flag should be passed to fetch_all."""
    with patch("data_gov_tw.__main__.fetch_all", new_callable=AsyncMock) as mock_fetch:
        result = runner.invoke(app, ["--only", "export-json.json"])

    mock_fetch.assert_called_once_with(ANY, only="export-json.json", no_cache=False)


def test_crawl_with_no_cache_flag():
    """--no-cache flag should be passed to fetch_all."""
    with patch("data_gov_tw.__main__.fetch_all", new_callable=AsyncMock) as mock_fetch:
        result = runner.invoke(app, ["--only", "export-json.json", "--no-cache"])

    mock_fetch.assert_called_once_with(ANY, only="export-json.json", no_cache=True)
