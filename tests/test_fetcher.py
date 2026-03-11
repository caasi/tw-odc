import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tw_odc.fetcher import clean, clean_dataset, fetch_all, resolve_params, _dest_filename


def test_resolve_params_today(monkeypatch):
    """resolve_params should replace 'today' with current date."""
    import datetime
    monkeypatch.setattr("tw_odc.fetcher.datetime", type("M", (), {"date": type("D", (), {"today": staticmethod(lambda: datetime.date(2026, 3, 10))})})())
    result = resolve_params({"date": "today"})
    assert result == {"date": "2026-03-10"}


def test_resolve_params_literal():
    """resolve_params should pass through literal string values."""
    result = resolve_params({"date": "2026-01-15"})
    assert result == {"date": "2026-01-15"}


def test_resolve_params_empty():
    """resolve_params with None or empty dict returns empty dict."""
    assert resolve_params(None) == {}
    assert resolve_params({}) == {}


def test_dest_filename_ignores_params():
    """Params are for URL substitution only; filename is always id.format with no param suffix."""
    result = _dest_filename(
        {"id": "daily-changed-json", "format": "json"},
        0, 1,
    )
    assert result == "daily-changed-json.json"


def test_dest_filename_without_params_unchanged():
    """Existing behavior: no params → id.format filename."""
    result = _dest_filename({"id": "export-json", "format": "json"}, 0, 1)
    assert result == "export-json.json"


def _make_manifest(tmp_path, datasets):
    """Create a minimal package with manifest.json, return (manifest_dict, pkg_dir)."""
    manifest = {"type": "dataset", "provider": "測試機關", "slug": "test_provider", "datasets": datasets}
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest, pkg_dir


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
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "測試資料", "format": "CSV", "urls": ["https://example.com/data.csv"]},
        {"id": "1002", "name": "另一筆", "format": "JSON", "urls": ["https://example.com/data.json"]},
    ])
    mock_content = b"hello"
    mock_session = _make_mock_session(200, mock_content)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(manifest, pkg_dir / "datasets")

    datasets_dir = pkg_dir / "datasets"
    assert (datasets_dir / "1001.csv").read_bytes() == mock_content
    assert (datasets_dir / "1002.json").read_bytes() == mock_content


@pytest.mark.asyncio
async def test_fetch_all_handles_http_error(tmp_path):
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "測試資料", "format": "CSV", "urls": ["https://example.com/data.csv"]},
    ])
    mock_session = _make_mock_session(500)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(manifest, pkg_dir / "datasets")

    assert not (pkg_dir / "datasets" / "1001.csv").exists()


@pytest.mark.asyncio
async def test_fetch_all_handles_network_error(tmp_path):
    """A network error for one download should not abort others."""
    import aiohttp as _aiohttp

    manifest, pkg_dir = _make_manifest(tmp_path, [
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
        await fetch_all(manifest, pkg_dir / "datasets")

    assert (pkg_dir / "datasets" / "good.csv").exists()
    assert not (pkg_dir / "datasets" / "bad.csv").exists()


def test_dest_filename_rejects_path_traversal(tmp_path):
    """dataset ids or formats with path separators must be rejected."""
    with pytest.raises(ValueError, match="Unsafe dataset id"):
        _dest_filename({"id": "../__init__", "format": "py"}, 0, 1)

    with pytest.raises(ValueError, match="Unsafe dataset format"):
        _dest_filename({"id": "1001", "format": "py/../evil"}, 0, 1)


def test_dest_filename_accepts_unicode_format():
    """Chinese format names like '其他' should be accepted."""
    result = _dest_filename({"id": "1001", "format": "其他"}, 0, 1)
    assert result == "1001.其他"


@pytest.mark.asyncio
async def test_fetch_all_blocks_domain_on_429(tmp_path):
    """After a 429, all subsequent requests to the same domain are skipped."""
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "First", "format": "CSV", "urls": ["https://blocked.example.com/a.csv"]},
        {"id": "1002", "name": "Second", "format": "CSV", "urls": ["https://blocked.example.com/b.csv"]},
        {"id": "1003", "name": "Other domain", "format": "CSV", "urls": ["https://other.example.com/c.csv"]},
    ])

    call_count = {"blocked.example.com": 0, "other.example.com": 0}

    async def _iter_chunked(chunk_size):
        yield b"ok"

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    def _get(url, **kwargs):
        from urllib.parse import urlparse
        domain = urlparse(url).hostname
        call_count[domain] = call_count.get(domain, 0) + 1

        resp = AsyncMock()
        if domain == "blocked.example.com":
            resp.status = 429
        else:
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
        await fetch_all(manifest, pkg_dir / "datasets", concurrency=1)

    # Only 1 request should hit blocked domain (the first one triggers 429, second is skipped)
    assert call_count["blocked.example.com"] == 1
    # Other domain should still work
    assert (pkg_dir / "datasets" / "1003.csv").exists()


@pytest.mark.asyncio
async def test_fetch_all_handles_multiple_urls(tmp_path):
    manifest, pkg_dir = _make_manifest(tmp_path, [
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
        await fetch_all(manifest, pkg_dir / "datasets")

    datasets_dir = pkg_dir / "datasets"
    assert (datasets_dir / "2001-1.csv").read_bytes() == mock_content
    assert (datasets_dir / "2001-2.csv").read_bytes() == mock_content


def test_clean_removes_all_generated_files(tmp_path):
    """clean() should remove datasets/, etags.json, issues.jsonl, scores.json."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")

    # Create generated files
    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "1001.csv").write_text("data")
    (pkg_dir / "etags.json").write_text("{}")
    (pkg_dir / "issues.jsonl").write_text("{}")
    (pkg_dir / "scores.json").write_text("{}")

    removed = clean(pkg_dir)

    assert not ds_dir.exists()
    assert not (pkg_dir / "etags.json").exists()
    assert not (pkg_dir / "issues.jsonl").exists()
    assert not (pkg_dir / "scores.json").exists()
    assert (pkg_dir / "manifest.json").exists()
    assert len(removed) == 4


def test_clean_nothing_to_delete(tmp_path):
    """clean() on an already-clean module should return empty list."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")

    removed = clean(pkg_dir)
    assert removed == []


def test_clean_raises_without_manifest(tmp_path):
    """clean() should raise FileNotFoundError when manifest.json is missing."""
    pkg_dir = tmp_path / "not_a_provider"
    pkg_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="manifest.json not found"):
        clean(pkg_dir)


def test_clean_dataset_removes_files_and_entries(tmp_path):
    """clean_dataset() should remove dataset files and related entries from etags/issues/scores."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")

    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "1001.csv").write_text("data")
    (ds_dir / "1002.json").write_text("other")

    (pkg_dir / "etags.json").write_text(json.dumps({
        "https://example.com/1001.csv": {"etag": "\"aaa\""},
        "https://example.com/1002.json": {"etag": "\"bbb\""},
    }))
    (pkg_dir / "issues.jsonl").write_text(
        '{"file": "1001.csv", "url": "https://example.com/1001.csv", "issue": "http_error"}\n'
        '{"file": "1002.json", "url": "https://example.com/1002.json", "issue": "ssl_error"}\n'
    )
    (pkg_dir / "scores.json").write_text(json.dumps({
        "provider": "測試",
        "datasets": [
            {"id": "1001", "star_score": 2},
            {"id": "1002", "star_score": 3},
        ],
    }))

    removed = clean_dataset(pkg_dir, "1001", ["https://example.com/1001.csv"])

    assert "1001.csv" in removed
    assert not (ds_dir / "1001.csv").exists()
    assert (ds_dir / "1002.json").exists()

    # etags.json should only have 1002
    etags = json.loads((pkg_dir / "etags.json").read_text())
    assert "https://example.com/1001.csv" not in etags
    assert "https://example.com/1002.json" in etags

    # issues.jsonl should only have 1002
    lines = (pkg_dir / "issues.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert "1002.json" in lines[0]

    # scores.json should only have 1002
    scores = json.loads((pkg_dir / "scores.json").read_text())
    assert len(scores["datasets"]) == 1
    assert scores["datasets"][0]["id"] == "1002"


def test_clean_dataset_removes_files_when_last_entry(tmp_path):
    """clean_dataset() should delete the file entirely when no entries remain."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")

    (pkg_dir / "etags.json").write_text(json.dumps({
        "https://example.com/1001.csv": {"etag": "\"aaa\""},
    }))
    (pkg_dir / "issues.jsonl").write_text(
        '{"file": "1001.csv", "issue": "http_error"}\n'
    )
    (pkg_dir / "scores.json").write_text(json.dumps({
        "provider": "測試",
        "datasets": [{"id": "1001", "star_score": 2}],
    }))

    removed = clean_dataset(pkg_dir, "1001", ["https://example.com/1001.csv"])

    assert not (pkg_dir / "etags.json").exists()
    assert not (pkg_dir / "issues.jsonl").exists()
    assert not (pkg_dir / "scores.json").exists()
    assert any("etags.json" in r for r in removed)
    assert any("issues.jsonl" in r for r in removed)
    assert any("scores.json" in r for r in removed)


def test_clean_dataset_multi_url(tmp_path):
    """clean_dataset() should handle datasets with multiple URLs."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")

    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "2001-1.csv").write_text("a")
    (ds_dir / "2001-2.csv").write_text("b")

    (pkg_dir / "etags.json").write_text(json.dumps({
        "https://example.com/part1.csv": {"etag": "\"a\""},
        "https://example.com/part2.csv": {"etag": "\"b\""},
    }))

    removed = clean_dataset(
        pkg_dir, "2001",
        ["https://example.com/part1.csv", "https://example.com/part2.csv"],
    )

    assert "2001-1.csv" in removed
    assert "2001-2.csv" in removed
    assert not (pkg_dir / "etags.json").exists()


def test_clean_dataset_no_side_files(tmp_path):
    """clean_dataset() should work when etags/issues/scores don't exist."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")

    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "1001.csv").write_text("data")

    removed = clean_dataset(pkg_dir, "1001", ["https://example.com/1001.csv"])
    assert removed == ["1001.csv"]


@pytest.mark.asyncio
async def test_fetch_all_resolves_params(tmp_path):
    """fetch_all should substitute {date} in URLs; filename should be stable (no date suffix)."""
    manifest = {
        "type": "metadata",
        "provider": "data.gov.tw",
        "datasets": [{
            "id": "daily-changed-json",
            "name": "每日異動資料集 JSON",
            "format": "json",
            "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
            "params": {"date": "today"},
        }],
    }

    import datetime
    captured_urls = []

    async def _iter_chunked(chunk_size):
        yield b'[{"id": 1}]'

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    def _get(url, **kwargs):
        captured_urls.append(url)
        resp = AsyncMock()
        resp.status = 200
        resp.content_length = 12
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
        await fetch_all(manifest, tmp_path)

    today = datetime.date.today().isoformat()
    # URL should have date substituted
    assert len(captured_urls) == 1
    assert f"report_date={today}" in captured_urls[0]
    # Filename should NOT include date (params are for URL substitution only)
    assert (tmp_path / "daily-changed-json.json").exists()


@pytest.mark.asyncio
async def test_fetch_all_param_overrides(tmp_path):
    """param_overrides should take precedence over manifest params."""
    manifest = {
        "type": "metadata",
        "provider": "data.gov.tw",
        "datasets": [{
            "id": "daily-changed-json",
            "name": "每日異動資料集 JSON",
            "format": "json",
            "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
            "params": {"date": "today"},
        }],
    }
    captured_urls = []

    async def _iter_chunked(chunk_size):
        yield b'[]'

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    def _get(url, **kwargs):
        captured_urls.append(url)
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
        await fetch_all(manifest, tmp_path, param_overrides={"date": "2026-01-01"})

    assert "report_date=2026-01-01" in captured_urls[0]
    assert (tmp_path / "daily-changed-json.json").exists()


@pytest.mark.asyncio
async def test_fetch_all_only_downloads_matching_file(tmp_path):
    """--only should download only the file whose dest name matches."""
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Target", "format": "CSV", "urls": ["https://example.com/a.csv"]},
        {"id": "1002", "name": "Skip", "format": "JSON", "urls": ["https://example.com/b.json"]},
    ])
    mock_session = _make_mock_session(200, b"data")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(manifest, pkg_dir / "datasets", only="1001.csv")

    assert (pkg_dir / "datasets" / "1001.csv").exists()
    assert not (pkg_dir / "datasets" / "1002.json").exists()


@pytest.mark.asyncio
async def test_fetch_all_only_no_match_prints_error(tmp_path, capsys):
    """--only with a non-existent filename should print available files and not create datasets/."""
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Data", "format": "CSV", "urls": ["https://example.com/a.csv"]},
    ])

    await fetch_all(manifest, pkg_dir / "datasets", only="nonexistent.csv")

    captured = capsys.readouterr()
    assert "E106" in captured.err
    assert "1001.csv" in captured.err
    assert not (pkg_dir / "datasets").exists()


@pytest.mark.asyncio
async def test_fetch_all_no_cache_skips_conditional_headers(tmp_path):
    """--no-cache should not send If-None-Match even when etags.json exists."""
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Data", "format": "CSV", "urls": ["https://example.com/a.csv"]},
    ])
    # Pre-populate etags.json
    (pkg_dir / "etags.json").write_text(json.dumps({
        "https://example.com/a.csv": {"etag": "\"abc123\""}
    }))

    captured_headers = {}

    async def _iter_chunked(chunk_size):
        yield b"data"

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    def _get(url, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        resp = AsyncMock()
        resp.status = 200
        resp.content_length = 4
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
        await fetch_all(manifest, pkg_dir / "datasets", no_cache=True)

    assert "If-None-Match" not in captured_headers


@pytest.mark.asyncio
async def test_fetch_all_parameterized_skips_etag_cache(tmp_path):
    """Datasets with params should never send conditional headers, even when etags.json has a matching URL."""
    manifest = {
        "type": "metadata",
        "provider": "data.gov.tw",
        "datasets": [{
            "id": "daily-changed-json",
            "name": "每日異動",
            "format": "json",
            "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
            "params": {"date": "today"},
        }],
    }
    import datetime
    today = datetime.date.today().isoformat()
    resolved_url = f"https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={today}"

    # Pre-populate etags.json with the resolved URL so a normal (non-param) dataset would get a 304
    cache_path = tmp_path / "etags.json"
    cache_path.write_text(json.dumps({resolved_url: {"etag": '"abc123"'}}))

    captured_headers = {}

    async def _iter_chunked(chunk_size):
        yield b"[]"

    mock_content_obj = MagicMock()
    mock_content_obj.iter_chunked = _iter_chunked

    def _get(url, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
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
        await fetch_all(manifest, tmp_path, cache_path=cache_path)

    # No conditional headers sent despite etags.json having the URL
    assert "If-None-Match" not in captured_headers

    # ETag for the parameterized URL should have been evicted from the cache file
    # (when the only entry was for the parameterized URL, the file should be removed)
    if cache_path.exists():
        new_cache = json.loads(cache_path.read_text())
        assert resolved_url not in new_cache
