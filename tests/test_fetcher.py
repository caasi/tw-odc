import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.fetcher import fetch_all


def _make_manifest(tmp_path, datasets):
    """Create a minimal package with manifest.json."""
    manifest = {"provider": "測試機關", "slug": "test_provider", "datasets": datasets}
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    (pkg_dir / "__init__.py").write_text("")
    return pkg_dir


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
    mock_response.headers = {}
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session


@pytest.mark.asyncio
async def test_fetch_all_downloads_from_manifest(tmp_path):
    pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "測試資料", "format": "CSV", "urls": ["https://example.com/data.csv"]},
        {"id": "1002", "name": "另一筆", "format": "JSON", "urls": ["https://example.com/data.json"]},
    ])
    mock_content = b"hello"
    mock_session = _make_mock_session(200, mock_content)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(str(pkg_dir / "__init__.py"))

    datasets_dir = pkg_dir / "datasets"
    assert (datasets_dir / "1001.csv").read_bytes() == mock_content
    assert (datasets_dir / "1002.json").read_bytes() == mock_content


@pytest.mark.asyncio
async def test_fetch_all_handles_http_error(tmp_path):
    pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "測試資料", "format": "CSV", "urls": ["https://example.com/data.csv"]},
    ])
    mock_session = _make_mock_session(500)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(str(pkg_dir / "__init__.py"))

    assert not (pkg_dir / "datasets" / "1001.csv").exists()


@pytest.mark.asyncio
async def test_fetch_all_handles_network_error(tmp_path):
    """A network error for one download should not abort others."""
    import aiohttp as _aiohttp

    pkg_dir = _make_manifest(tmp_path, [
        {"id": "good", "name": "正常資料", "format": "CSV", "urls": ["https://example.com/good.csv"]},
        {"id": "bad", "name": "壞連結", "format": "CSV", "urls": ["https://example.com/bad.csv"]},
    ])

    async def _iter_chunked(chunk_size):
        yield b"ok"

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    def _get(url, **kwargs):
        """Synchronous factory — returns an async context manager per URL."""
        if "bad" in url:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(
                side_effect=_aiohttp.ClientConnectionError("simulated error")
            )
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        resp = AsyncMock()
        resp.status = 200
        resp.content_length = 2
        resp.content = mock_content_obj
        resp.headers = {}
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    mock_session = AsyncMock()
    mock_session.get = _get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        # Should not raise even though one download fails
        await fetch_all(str(pkg_dir / "__init__.py"))

    assert (pkg_dir / "datasets" / "good.csv").exists()
    assert not (pkg_dir / "datasets" / "bad.csv").exists()


def test_dest_filename_rejects_path_traversal(tmp_path):
    """dataset ids or formats with path separators must be rejected."""
    from shared.fetcher import _dest_filename

    with pytest.raises(ValueError, match="Unsafe dataset id"):
        _dest_filename({"id": "../__init__", "format": "py"}, 0, 1)

    with pytest.raises(ValueError, match="Unsafe dataset format"):
        _dest_filename({"id": "1001", "format": "py/../evil"}, 0, 1)


@pytest.mark.asyncio
async def test_fetch_all_handles_multiple_urls(tmp_path):
    pkg_dir = _make_manifest(tmp_path, [
        {
            "id": "2001",
            "name": "多檔資料",
            "format": "CSV",
            "urls": [
                "https://example.com/part1.csv",
                "https://example.com/part2.csv",
            ],
        },
    ])
    mock_content = b"data"
    mock_session = _make_mock_session(200, mock_content)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(str(pkg_dir / "__init__.py"))

    datasets_dir = pkg_dir / "datasets"
    assert (datasets_dir / "2001-1.csv").read_bytes() == mock_content
    assert (datasets_dir / "2001-2.csv").read_bytes() == mock_content
