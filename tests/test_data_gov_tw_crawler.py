import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from data_gov_tw.crawler import crawl, EXPORTS


def test_exports_has_three_urls():
    assert len(EXPORTS) == 3
    assert all(url.startswith("https://data.gov.tw/") for url in EXPORTS)


@pytest.mark.asyncio
async def test_crawl_downloads_all_exports(tmp_path):
    mock_content = b"test content"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=mock_content)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await crawl(output_dir=tmp_path)

    assert (tmp_path / "export.json").read_bytes() == mock_content
    assert (tmp_path / "export.csv").read_bytes() == mock_content
    assert (tmp_path / "export.xml").read_bytes() == mock_content


@pytest.mark.asyncio
async def test_crawl_handles_http_error(tmp_path, capsys):
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await crawl(output_dir=tmp_path)

    assert not (tmp_path / "export.json").exists()
    captured = capsys.readouterr()
    assert "500" in captured.out or "失敗" in captured.out
