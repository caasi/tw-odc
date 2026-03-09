import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from data_gov_tw.crawler import crawl, EXPORTS


def test_exports_has_three_urls():
    assert len(EXPORTS) == 3
    assert all(url.startswith("https://data.gov.tw/") for url in EXPORTS)


def _make_mock_session(status, content=b""):
    """Create a mock aiohttp session with streaming support."""

    async def _iter_chunked(chunk_size):
        if content:
            yield content

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.content_length = len(content) if content else 0
    mock_response.content = mock_content_obj
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session


@pytest.mark.asyncio
async def test_crawl_downloads_all_exports(tmp_path):
    mock_content = b"test content"
    mock_session = _make_mock_session(200, mock_content)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await crawl(output_dir=tmp_path)

    assert (tmp_path / "export.json").read_bytes() == mock_content
    assert (tmp_path / "export.csv").read_bytes() == mock_content
    assert (tmp_path / "export.xml").read_bytes() == mock_content


@pytest.mark.asyncio
async def test_crawl_handles_http_error(tmp_path):
    mock_session = _make_mock_session(500)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await crawl(output_dir=tmp_path)

    assert not (tmp_path / "export.json").exists()


def test_cli_module_runs():
    result = subprocess.run(
        ["uv", "run", "python", "-m", "data_gov_tw", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "data.gov.tw" in result.stdout
