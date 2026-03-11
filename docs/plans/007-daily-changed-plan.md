# Daily Changed Dataset Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `params` support to metadata manifest so tw-odc can download date-parameterized daily changed datasets from data.gov.tw.

**Architecture:** Extend `_dest_filename` and `fetch_all` in `fetcher.py` to resolve URL templates via an optional `params` dict on dataset entries. Add `--date` CLI option to override `params.date`. Update root `manifest.json` with daily-changed entries.

**Tech Stack:** Python 3.13, typer, aiohttp (existing stack — no new deps)

---

### Task 1: Add `resolve_params` helper to fetcher

**Files:**
- Modify: `tw_odc/fetcher.py`
- Test: `tests/test_fetcher.py`

**Step 1: Write the failing test**

Add to `tests/test_fetcher.py`:

```python
from tw_odc.fetcher import resolve_params


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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetcher.py::test_resolve_params_today tests/test_fetcher.py::test_resolve_params_literal tests/test_fetcher.py::test_resolve_params_empty -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_params'`

**Step 3: Write minimal implementation**

Add to `tw_odc/fetcher.py` (after the existing imports, add `import datetime`; after `_SAFE_FMT_RE`):

```python
import datetime

def resolve_params(params: dict | None, overrides: dict | None = None) -> dict:
    """Resolve special param values. 'today' → YYYY-MM-DD. Overrides take precedence."""
    if not params:
        return {}
    resolved = {}
    merged = {**params, **(overrides or {})}
    for key, value in merged.items():
        if value == "today":
            resolved[key] = datetime.date.today().isoformat()
        else:
            resolved[key] = str(value)
    return resolved
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fetcher.py::test_resolve_params_today tests/test_fetcher.py::test_resolve_params_literal tests/test_fetcher.py::test_resolve_params_empty -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "feat: add resolve_params helper for URL template substitution"
```

---

### Task 2: Update `_dest_filename` to support params suffix

**Files:**
- Modify: `tw_odc/fetcher.py:19-29` (`_dest_filename`)
- Test: `tests/test_fetcher.py`

**Step 1: Write the failing test**

Add to `tests/test_fetcher.py`:

```python
def test_dest_filename_with_params():
    """Datasets with resolved params should include param values in filename."""
    result = _dest_filename(
        {"id": "daily-changed-json", "format": "json"},
        0, 1,
        resolved_params={"date": "2026-03-10"},
    )
    assert result == "daily-changed-json-2026-03-10.json"


def test_dest_filename_without_params_unchanged():
    """Existing behavior: no params → id.format filename."""
    result = _dest_filename({"id": "export-json", "format": "json"}, 0, 1)
    assert result == "export-json.json"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetcher.py::test_dest_filename_with_params tests/test_fetcher.py::test_dest_filename_without_params_unchanged -v`
Expected: FAIL with `TypeError: _dest_filename() got an unexpected keyword argument 'resolved_params'`

**Step 3: Update `_dest_filename`**

Replace the existing `_dest_filename` in `tw_odc/fetcher.py`:

```python
def _dest_filename(dataset: dict, url_index: int, url_count: int, resolved_params: dict | None = None) -> str:
    """Derive destination filename from dataset id, format, and optional params."""
    fmt = dataset["format"].lower()
    dataset_id = str(dataset["id"])
    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(fmt):
        raise ValueError(f"Unsafe dataset format: {fmt!r}")
    suffix = ""
    if resolved_params:
        param_str = "-".join(resolved_params.values())
        suffix = f"-{param_str}"
    if url_count == 1:
        return f"{dataset_id}{suffix}.{fmt}"
    return f"{dataset_id}{suffix}-{url_index + 1}.{fmt}"
```

**Step 4: Run ALL fetcher tests to verify nothing broke**

Run: `uv run pytest tests/test_fetcher.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "feat: support params suffix in dest filename"
```

---

### Task 3: Update `fetch_all` to resolve params and substitute URLs

**Files:**
- Modify: `tw_odc/fetcher.py:135-173` (`fetch_all`)
- Test: `tests/test_fetcher.py`

**Step 1: Write the failing test**

Add to `tests/test_fetcher.py`:

```python
@pytest.mark.asyncio
async def test_fetch_all_resolves_params(tmp_path):
    """fetch_all should substitute {date} in URLs and include date in filename."""
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
    # Filename should include date
    assert (tmp_path / f"daily-changed-json-{today}.json").exists()


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
    assert (tmp_path / "daily-changed-json-2026-01-01.json").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetcher.py::test_fetch_all_resolves_params tests/test_fetcher.py::test_fetch_all_param_overrides -v`
Expected: FAIL — `fetch_all()` doesn't handle params yet

**Step 3: Update `fetch_all` signature and download loop**

In `tw_odc/fetcher.py`, update `fetch_all`:

1. Add `param_overrides: dict | None = None` parameter to signature.
2. Inside the download loop, after `urls = dataset["urls"]`, add params resolution and URL substitution:

```python
async def fetch_all(
    manifest: dict,
    output_dir: Path,
    concurrency: int = 5,
    only: str | None = None,
    no_cache: bool = False,
    cache_path: Path | None = None,
    param_overrides: dict | None = None,
) -> None:
```

In the download collection loop, replace:
```python
    for dataset in manifest["datasets"]:
        urls = dataset["urls"]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls))
```

With:
```python
    for dataset in manifest["datasets"]:
        resolved = resolve_params(dataset.get("params"), param_overrides)
        urls = dataset["urls"]
        if resolved:
            urls = [u.format_map(resolved) for u in urls]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls), resolved_params=resolved or None)
```

**Step 4: Run ALL fetcher tests**

Run: `uv run pytest tests/test_fetcher.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "feat: resolve params and substitute URL templates in fetch_all"
```

---

### Task 4: Add `--date` CLI option to `metadata download`

**Files:**
- Modify: `tw_odc/cli.py:95-106` (`metadata_download`)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
class TestMetadataDownloadDate:
    def test_date_option_passes_param_overrides(self, tmp_path, monkeypatch):
        """--date should pass param_overrides to fetch_all."""
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
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        captured_kwargs = {}

        async def mock_fetch_all(m, output_dir, **kwargs):
            captured_kwargs.update(kwargs)

        import tw_odc.fetcher
        monkeypatch.setattr(tw_odc.fetcher, "fetch_all", mock_fetch_all)
        monkeypatch.setattr("tw_odc.cli.asyncio.run", lambda coro: asyncio.get_event_loop().run_until_complete(coro))

        import asyncio
        result = runner.invoke(app, ["metadata", "download", "--date", "2026-03-10"])
        assert result.exit_code == 0
        assert captured_kwargs.get("param_overrides") == {"date": "2026-03-10"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::TestMetadataDownloadDate -v`
Expected: FAIL — `--date` option doesn't exist yet

**Step 3: Update `metadata_download` in `tw_odc/cli.py`**

```python
@metadata_app.command("download")
def metadata_download(
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    only: str | None = typer.Option(None, "--only", help="Download only this file"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
    date: str | None = typer.Option(None, "--date", help="Override {date} param (YYYY-MM-DD)"),
) -> None:
    """Download metadata files."""
    from tw_odc.fetcher import fetch_all

    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    param_overrides = {"date": date} if date else None
    asyncio.run(fetch_all(manifest, cwd, only=only, no_cache=no_cache, cache_path=cwd / "etags.json", param_overrides=param_overrides))
```

**Step 4: Run ALL CLI tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/cli.py tests/test_cli.py
git commit -m "feat: add --date option to metadata download for param override"
```

---

### Task 5: Update manifest.json and .gitignore

**Files:**
- Modify: `manifest.json`
- Modify: `.gitignore`

**Step 1: Update `manifest.json`**

Add two daily-changed entries after the existing 3 export entries:

```json
{
  "type": "metadata",
  "provider": "data.gov.tw",
  "datasets": [
    {
      "id": "export-json",
      "name": "全站資料集匯出 JSON",
      "format": "json",
      "urls": ["https://data.gov.tw/datasets/export/json"]
    },
    {
      "id": "export-csv",
      "name": "全站資料集匯出 CSV",
      "format": "csv",
      "urls": ["https://data.gov.tw/datasets/export/csv"]
    },
    {
      "id": "export-xml",
      "name": "全站資料集匯出 XML",
      "format": "xml",
      "urls": ["https://data.gov.tw/datasets/export/xml"]
    },
    {
      "id": "daily-changed-json",
      "name": "每日異動資料集 JSON",
      "format": "json",
      "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
      "params": { "date": "today" }
    },
    {
      "id": "daily-changed-csv",
      "name": "每日異動資料集 CSV",
      "format": "csv",
      "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=csv&report_date={date}"],
      "params": { "date": "today" }
    }
  ]
}
```

**Step 2: Update `.gitignore`**

Add `/daily-changed-*.*` after the existing export entries:

```gitignore
# Metadata downloads (root level)
/export-json.json
/export-csv.csv
/export-xml.xml
/daily-changed-*.*
```

**Step 3: Run all tests to verify nothing broke**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add manifest.json .gitignore
git commit -m "feat: add daily-changed datasets to metadata manifest"
```

---

### Task 6: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add daily-changed commands to the Commands section**

In the `## Commands` section, after the `tw-odc metadata download` block, add:

```bash
# Download daily changed datasets (uses today's date by default)
tw-odc metadata download --only daily-changed-json.json
tw-odc metadata download --only daily-changed-csv.csv --date 2026-03-10
```

**Step 2: Update the manifest.json format section**

In the Architecture section, mention `params` as an optional field in the metadata manifest description.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document daily-changed dataset commands and params field"
```
