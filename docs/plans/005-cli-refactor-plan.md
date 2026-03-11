# tw-odc CLI 重構實作計畫

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 將 `main.py` 和 `shared/` 重構為統一 CLI 工具 `tw-odc`，支援 metadata/dataset 兩種資料來源，JSON 優先輸出，移除 scaffolding。

**Architecture:** 建立 `tw_odc/` 套件取代 `shared/`，以 typer 實作兩層子命令（metadata/dataset）。manifest.py 處理 manifest 讀寫與 RFC 6902 patch。fetcher/inspector/scorer 從 shared/ 遷移並改用 Path-based 介面。CLI 負責組裝所有模組。

**Tech Stack:** Python >=3.13, typer, aiohttp, jsonpatch, python-magic, rich

---

### Task 1: 建立 tw_odc/manifest.py — manifest 讀寫與 patch 機制

**Files:**
- Create: `tw_odc/__init__.py`
- Create: `tw_odc/manifest.py`
- Test: `tests/test_manifest.py`

**Step 1: Write failing tests**

```python
# tests/test_manifest.py
import json
import pytest
from pathlib import Path
from tw_odc.manifest import (
    load_manifest,
    ManifestType,
    group_by_provider,
    compute_slug,
    derive_slug,
    parse_dataset,
    create_dataset_manifest,
)


class TestLoadManifest:
    def test_load_metadata_manifest(self, tmp_path):
        m = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        result = load_manifest(tmp_path)
        assert result["type"] == "metadata"

    def test_load_dataset_manifest(self, tmp_path):
        m = {"type": "dataset", "provider": "財政部", "slug": "mof_gov_tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        result = load_manifest(tmp_path)
        assert result["type"] == "dataset"

    def test_load_missing_manifest_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path)

    def test_load_applies_patch(self, tmp_path):
        m = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1", "name": "A", "format": "csv", "urls": []}]
        }
        patch = [{"op": "replace", "path": "/datasets/0/format", "value": "json"}]
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        (tmp_path / "patch.json").write_text(json.dumps(patch))
        result = load_manifest(tmp_path)
        assert result["datasets"][0]["format"] == "json"

    def test_load_no_patch_file_is_ok(self, tmp_path):
        m = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        result = load_manifest(tmp_path)
        assert result["datasets"] == []


class TestDeriveSlug:
    def test_single_domain(self):
        assert derive_slug(["https://www.mof.gov.tw/a"]) == "mof_gov_tw"

    def test_strips_www(self):
        assert derive_slug(["https://www.example.gov.tw/a"]) == "example_gov_tw"

    def test_most_frequent_domain(self):
        urls = ["https://a.gov.tw/1", "https://b.gov.tw/2", "https://a.gov.tw/3"]
        assert derive_slug(urls) == "a_gov_tw"

    def test_empty(self):
        assert derive_slug([]) == ""


class TestComputeSlug:
    def test_with_urls(self):
        assert compute_slug("財政部", ["https://mof.gov.tw/a"]) == "mof_gov_tw"

    def test_fallback_hash(self):
        slug = compute_slug("無網址機關", [])
        assert slug.startswith("org_")
        assert len(slug) == 20


class TestGroupByProvider:
    def test_groups(self):
        datasets = [
            {"提供機關": "A", "other": 1},
            {"提供機關": "A", "other": 2},
            {"提供機關": "B", "other": 3},
        ]
        groups = group_by_provider(datasets)
        assert len(groups["A"]) == 2
        assert len(groups["B"]) == 1


class TestParseDataset:
    def test_basic(self):
        raw = {
            "資料集識別碼": 1001,
            "資料集名稱": "測試",
            "檔案格式": "CSV",
            "資料下載網址": "https://a.gov.tw/1",
        }
        result = parse_dataset(raw)
        assert result == {
            "id": "1001",
            "name": "測試",
            "format": "csv",
            "urls": ["https://a.gov.tw/1"],
        }

    def test_multiple_urls(self):
        raw = {
            "資料集識別碼": 1002,
            "資料集名稱": "多URL",
            "檔案格式": "CSV;JSON",
            "資料下載網址": "https://a.gov.tw/1;https://a.gov.tw/2",
        }
        result = parse_dataset(raw)
        assert result["urls"] == ["https://a.gov.tw/1", "https://a.gov.tw/2"]

    def test_format_alias(self):
        raw = {
            "資料集識別碼": 1003,
            "資料集名稱": "壓縮",
            "檔案格式": "壓縮檔",
            "資料下載網址": "https://a.gov.tw/1",
        }
        result = parse_dataset(raw)
        assert result["format"] == "zip"


class TestCreateDatasetManifest:
    def test_creates_manifest(self, tmp_path):
        raw_datasets = [
            {
                "資料集識別碼": 1001, "資料集名稱": "測試",
                "檔案格式": "CSV", "資料下載網址": "https://test.gov.tw/a",
            },
        ]
        slug = create_dataset_manifest(tmp_path, "測試機關", raw_datasets)
        assert slug == "test_gov_tw"
        manifest_path = tmp_path / slug / "manifest.json"
        assert manifest_path.exists()
        m = json.loads(manifest_path.read_text())
        assert m["type"] == "dataset"
        assert m["provider"] == "測試機關"
        assert len(m["datasets"]) == 1

    def test_update_existing_manifest(self, tmp_path):
        raw1 = [{"資料集識別碼": 1, "資料集名稱": "A", "檔案格式": "CSV", "資料下載網址": "https://t.gov.tw/a"}]
        slug = create_dataset_manifest(tmp_path, "T", raw1)
        raw2 = [
            {"資料集識別碼": 1, "資料集名稱": "A", "檔案格式": "CSV", "資料下載網址": "https://t.gov.tw/a"},
            {"資料集識別碼": 2, "資料集名稱": "B", "檔案格式": "JSON", "資料下載網址": "https://t.gov.tw/b"},
        ]
        slug2 = create_dataset_manifest(tmp_path, "T", raw2)
        assert slug == slug2
        m = json.loads((tmp_path / slug / "manifest.json").read_text())
        assert len(m["datasets"]) == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: FAIL (ModuleNotFoundError: tw_odc)

**Step 3: Write implementation**

```python
# tw_odc/__init__.py
"""tw-odc: Taiwan Open Data Checker CLI."""

# 中文格式名稱 → 標準副檔名
FORMAT_ALIASES: dict[str, str] = {
    "壓縮檔": "zip",
}
```

```python
# tw_odc/manifest.py
"""Manifest loading, writing, and RFC 6902 patch support."""

import hashlib
import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

import jsonpatch

from tw_odc import FORMAT_ALIASES


class ManifestType(StrEnum):
    METADATA = "metadata"
    DATASET = "dataset"


def load_manifest(manifest_dir: Path) -> dict:
    """Load manifest.json from a directory, applying patch.json if present.

    Raises FileNotFoundError if manifest.json does not exist.
    """
    manifest_path = manifest_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {manifest_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    patch_path = manifest_dir / "patch.json"
    if patch_path.exists():
        patch_ops = json.loads(patch_path.read_text(encoding="utf-8"))
        manifest = jsonpatch.apply_patch(manifest, patch_ops)

    return manifest


def derive_slug(urls: list[str]) -> str:
    """Derive a Python-safe directory name from a list of URLs."""
    if not urls:
        return ""
    domains: list[str] = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            netloc = urlparse(url).netloc.split(":")[0]
            if netloc.startswith("www."):
                netloc = netloc[4:]
            if netloc:
                domains.append(netloc)
        except Exception:
            continue
    if not domains:
        return ""
    most_common = Counter(domains).most_common(1)[0][0]
    return most_common.replace(".", "_").replace("-", "_")


def compute_slug(provider_name: str, urls: list[str]) -> str:
    """Return the slug for a provider: domain-based or org_<sha256> fallback."""
    slug = derive_slug(urls)
    if not slug:
        h = hashlib.sha256(provider_name.encode("utf-8")).hexdigest()[:16]
        slug = f"org_{h}"
    return slug


def group_by_provider(datasets: list[dict]) -> dict[str, list[dict]]:
    """Group raw export.json entries by provider name (提供機關)."""
    groups: dict[str, list[dict]] = {}
    for d in datasets:
        provider = d["提供機關"]
        groups.setdefault(provider, []).append(d)
    return groups


def parse_dataset(raw: dict) -> dict:
    """Convert a raw export.json entry to manifest dataset format."""
    urls = [u.strip() for u in raw["資料下載網址"].split(";") if u.strip()]
    formats = [f.strip() for f in raw["檔案格式"].split(";") if f.strip()]
    fmt = formats[0].lower() if formats else "bin"
    fmt = FORMAT_ALIASES.get(fmt, fmt)
    return {
        "id": str(raw["資料集識別碼"]),
        "name": raw["資料集名稱"],
        "format": fmt,
        "urls": urls,
    }


def create_dataset_manifest(
    base_dir: Path, provider_name: str, raw_datasets: list[dict]
) -> str:
    """Create or update a dataset manifest.json under base_dir/<slug>/. Returns slug."""
    all_urls = [
        u.strip()
        for d in raw_datasets
        for u in d["資料下載網址"].split(";")
        if u.strip()
    ]
    slug = compute_slug(provider_name, all_urls)
    pkg_dir = base_dir / slug
    pkg_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "type": ManifestType.DATASET,
        "provider": provider_name,
        "slug": slug,
        "datasets": [parse_dataset(d) for d in raw_datasets],
    }
    (pkg_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return slug
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tw_odc/__init__.py tw_odc/manifest.py tests/test_manifest.py
git commit -m "feat(tw_odc): add manifest module with RFC 6902 patch support"
```

---

### Task 2: 遷移 fetcher.py 到 tw_odc/

**Files:**
- Create: `tw_odc/fetcher.py`
- Modify: `tests/test_fetcher.py` (update imports)

**Step 1: Copy and refactor fetcher.py**

將 `shared/fetcher.py` 複製到 `tw_odc/fetcher.py`，改動：

1. `_load_manifest(init_file)` → 移除（由 CLI 層呼叫 `manifest.load_manifest()`）
2. `fetch_all(init_file, ...)` → `fetch_all(manifest: dict, output_dir: Path, ...)`
3. `clean(init_file)` → `clean(pkg_dir: Path)`，移除 `__init__.py` 相關邏輯

```python
# tw_odc/fetcher.py
import asyncio
import json
import re
import shutil
import ssl
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_SAFE_FMT_RE = re.compile(r"^\w+$")


def _dest_filename(dataset: dict, url_index: int, url_count: int) -> str:
    """Derive destination filename from dataset id and format."""
    fmt = dataset["format"].lower()
    dataset_id = str(dataset["id"])
    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(fmt):
        raise ValueError(f"Unsafe dataset format: {fmt!r}")
    if url_count == 1:
        return f"{dataset_id}.{fmt}"
    return f"{dataset_id}-{url_index + 1}.{fmt}"


def clean(pkg_dir: Path) -> list[str]:
    """Remove all generated files for a provider package.

    Deletes: datasets/, etags.json, issues.jsonl, scores.json.
    Returns list of names that were actually removed.
    """
    manifest_path = pkg_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"manifest.json not found in {pkg_dir}; not a provider package"
        )
    removed: list[str] = []
    datasets_dir = pkg_dir / "datasets"
    if datasets_dir.is_dir():
        shutil.rmtree(datasets_dir)
        removed.append("datasets/")
    for name in ("etags.json", "issues.jsonl", "scores.json"):
        path = pkg_dir / name
        if path.exists():
            path.unlink()
            removed.append(name)
    return removed


async def fetch_all(
    manifest: dict,
    output_dir: Path,
    concurrency: int = 5,
    only: str | None = None,
    no_cache: bool = False,
    cache_path: Path | None = None,
) -> None:
    """Download all datasets listed in manifest.

    Args:
        manifest: Parsed manifest dict with "datasets" key.
        output_dir: Directory to write downloaded files to.
        concurrency: Maximum number of simultaneous downloads.
        only: If set, only download the file whose dest name matches.
        no_cache: If True, skip conditional headers (ignore ETag cache).
        cache_path: Path to etags.json. If None, uses output_dir.parent / "etags.json".
    """
    if cache_path is None:
        cache_path = output_dir.parent / "etags.json"
    issues_path = output_dir.parent / "issues.jsonl"

    # Load cached ETags
    cache: dict[str, dict[str, str]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    # Collect all (url, dest) pairs
    downloads: list[tuple[str, Path]] = []
    for dataset in manifest["datasets"]:
        urls = dataset["urls"]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls))
            dest = (output_dir / filename).resolve()
            try:
                dest.relative_to(output_dir.resolve())
            except ValueError:
                raise ValueError(f"Destination path escapes output directory: {dest}")
            downloads.append((url, dest))

    if only:
        matched = [(url, dest) for url, dest in downloads if dest.name == only]
        if not matched:
            available = ", ".join(dest.name for _, dest in downloads)
            import sys
            print(f"找不到檔案: {only}\n可用的檔案: {available}", file=sys.stderr)
            return
        downloads = matched

    output_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    issues: list[dict] = []
    blocked_domains: set[str] = set()

    # (rest of the async download logic is identical to shared/fetcher.py)
    # _print, _conditional_headers, _update_cache, _do_download, _download
    # ... (same implementation, just copy from shared/fetcher.py lines 124-248)

    def _print(progress: Progress, msg: str) -> None:
        progress.console.print(msg, highlight=False)

    def _conditional_headers(url: str) -> dict[str, str]:
        if no_cache:
            return {}
        headers: dict[str, str] = {}
        entry = cache.get(url)
        if entry:
            if entry.get("etag"):
                headers["If-None-Match"] = entry["etag"]
            if entry.get("last_modified"):
                headers["If-Modified-Since"] = entry["last_modified"]
        return headers

    def _update_cache(url: str, headers: dict) -> None:
        etag = headers.get("ETag", "")
        last_modified = headers.get("Last-Modified", "")
        entry: dict[str, str] = {}
        if isinstance(etag, str) and etag:
            entry["etag"] = etag
        if isinstance(last_modified, str) and last_modified:
            entry["last_modified"] = last_modified
        if entry:
            cache[url] = entry

    async def _do_download(
        session: aiohttp.ClientSession,
        url: str,
        dest: Path,
        progress: Progress,
        ssl_ctx: ssl.SSLContext | bool = True,
    ) -> str:
        filename = dest.name
        headers = _conditional_headers(url)
        async with session.get(url, ssl=ssl_ctx, headers=headers) as resp:
            if resp.status == 304:
                _print(progress, f"[dim]—[/dim] {filename} (未變更)")
                return "not_modified"
            if resp.status == 429:
                domain = urlparse(url).hostname or url
                blocked_domains.add(domain)
                _print(progress, f"[red]✗[/red] {filename}: HTTP 429 — 已封鎖 {domain} 的所有請求")
                issues.append({"file": filename, "url": url, "issue": "rate_limited", "detail": f"HTTP 429, domain {domain} blocked"})
                return "error"
            if resp.status != 200:
                _print(progress, f"[red]✗[/red] {filename}: HTTP {resp.status}")
                issues.append({"file": filename, "url": url, "issue": "http_error", "detail": f"HTTP {resp.status}"})
                return "error"
            _update_cache(url, dict(resp.headers))
            total = resp.content_length
            task = progress.add_task(filename, total=total or None)
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))
            progress.remove_task(task)
            return "downloaded"

    async def _download(
        session: aiohttp.ClientSession, url: str, dest: Path, progress: Progress
    ) -> None:
        filename = dest.name
        domain = urlparse(url).hostname or url
        async with sem:
            if domain in blocked_domains:
                _print(progress, f"[dim]—[/dim] {filename} (跳過, {domain} 已被 429 封鎖)")
                issues.append({"file": filename, "url": url, "issue": "rate_limited", "detail": f"skipped, domain {domain} blocked"})
                return
            await asyncio.sleep(0.5)
            try:
                result = await _do_download(session, url, dest, progress)
                if result == "downloaded":
                    size = dest.stat().st_size
                    _print(progress, f"[green]✓[/green] {filename} ({size:,} bytes)")
            except aiohttp.ClientSSLError as exc:
                _print(progress, f"[yellow]⚠[/yellow] {filename}: SSL error, retrying without verification")
                issues.append({"file": filename, "url": url, "issue": "ssl_error", "detail": str(exc)})
                try:
                    no_verify = ssl.create_default_context()
                    no_verify.check_hostname = False
                    no_verify.verify_mode = ssl.CERT_NONE
                    no_verify_connector = aiohttp.TCPConnector(ssl=no_verify)
                    async with aiohttp.ClientSession(connector=no_verify_connector) as retry_session:
                        result = await _do_download(retry_session, url, dest, progress, ssl_ctx=no_verify)
                        if result == "downloaded":
                            size = dest.stat().st_size
                            _print(progress, f"[green]✓[/green] {filename} ({size:,} bytes) [yellow](SSL 驗證跳過)[/yellow]")
                except (aiohttp.ClientError, asyncio.TimeoutError) as retry_exc:
                    _print(progress, f"[red]✗[/red] {filename}: retry failed: {retry_exc}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                _print(progress, f"[red]✗[/red] {filename}: network error: {exc}")
                issues.append({"file": filename, "url": url, "issue": "network_error", "detail": str(exc)})
            except Exception as exc:
                _print(progress, f"[red]✗[/red] {filename}: unexpected error: {exc}")
                issues.append({"file": filename, "url": url, "issue": "unexpected_error", "detail": str(exc)})

    connector = aiohttp.TCPConnector(limit=concurrency)
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(), DownloadColumn(), TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession(connector=connector) as session:
            await asyncio.gather(
                *[_download(session, url, dest, progress) for url, dest in downloads]
            )

    if cache:
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if issues:
        with open(issues_path, "w", encoding="utf-8") as f:
            for issue in issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")
        import sys
        print(f"⚠ {len(issues)} 個問題已記錄到 {issues_path}", file=sys.stderr)
```

**Step 2: Update test imports**

Update `tests/test_fetcher.py`:
- Change all `from shared.fetcher import ...` → `from tw_odc.fetcher import ...`
- Change `_make_manifest` to no longer require `__init__.py` — tests now pass `manifest` dict and `output_dir` directly to `fetch_all`
- Change `clean()` calls to pass `pkg_dir` Path instead of `__init__.py` path

```python
# tests/test_fetcher.py — key changes:

# Old: from shared.fetcher import clean, fetch_all
from tw_odc.fetcher import clean, fetch_all, _dest_filename

def _make_manifest(tmp_path, datasets):
    """Create a minimal package with manifest.json, return (manifest_dict, pkg_dir)."""
    manifest = {"type": "dataset", "provider": "測試機關", "slug": "test_provider", "datasets": datasets}
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest, pkg_dir

# Old: await fetch_all(str(pkg_dir / "__init__.py"))
# New: await fetch_all(manifest, pkg_dir / "datasets")

# Old: clean(str(pkg_dir / "__init__.py"))
# New: clean(pkg_dir)
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_fetcher.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "feat(tw_odc): migrate fetcher with Path-based interface"
```

---

### Task 3: 遷移 inspector.py 和 scorer.py 到 tw_odc/

**Files:**
- Create: `tw_odc/inspector.py` (copy from `shared/inspector.py`, no changes needed)
- Create: `tw_odc/scorer.py` (copy from `shared/scorer.py`, update import path)
- Modify: `tests/test_inspector.py` (update imports)
- Modify: `tests/test_scorer.py` (update imports)

**Step 1: Copy files**

`tw_odc/inspector.py` — identical to `shared/inspector.py`.

`tw_odc/scorer.py` — change one import:
```python
# Old:
from shared.inspector import InspectionResult, inspect_dataset
# New:
from tw_odc.inspector import InspectionResult, inspect_dataset
```

**Step 2: Update test imports**

`tests/test_inspector.py`:
```python
# Old:
from shared.inspector import InspectionResult, detect_format, inspect_dataset, inspect_zip_contents
# New:
from tw_odc.inspector import InspectionResult, detect_format, inspect_dataset, inspect_zip_contents
```

`tests/test_scorer.py`:
```python
# Old:
from shared.inspector import InspectionResult
from shared.scorer import score_dataset, score_provider
# New:
from tw_odc.inspector import InspectionResult
from tw_odc.scorer import score_dataset, score_provider
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_inspector.py tests/test_scorer.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tw_odc/inspector.py tw_odc/scorer.py tests/test_inspector.py tests/test_scorer.py
git commit -m "feat(tw_odc): migrate inspector and scorer modules"
```

---

### Task 4: 建立 CLI — tw_odc/cli.py 和 tw_odc/__main__.py

**Files:**
- Create: `tw_odc/cli.py`
- Create: `tw_odc/__main__.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

```python
# tests/test_cli.py
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tw_odc.cli import app

runner = CliRunner()


class TestMetadataList:
    def test_json_output(self, tmp_path, monkeypatch):
        """metadata list outputs JSON array of providers."""
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON匯出", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "資料A",
             "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/d"},
            {"提供機關": "A機關", "資料集識別碼": 2, "資料集名稱": "資料A2",
             "檔案格式": "JSON", "資料下載網址": "https://a.gov.tw/d2"},
            {"提供機關": "B機關", "資料集識別碼": 3, "資料集名稱": "資料B",
             "檔案格式": "CSV", "資料下載網址": "https://b.gov.tw/d"},
        ]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [p["provider"] for p in data]
        assert "A機關" in names
        assert "B機關" in names

    def test_text_output(self, tmp_path, monkeypatch):
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON匯出", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "資料A",
             "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/d"},
        ]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "list", "--format", "text"])
        assert result.exit_code == 0
        assert "A機關" in result.output
        # Should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)


class TestMetadataCreate:
    def test_creates_dataset_manifest(self, tmp_path, monkeypatch):
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON匯出", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "測試機關", "資料集識別碼": 1001, "資料集名稱": "測試",
             "檔案格式": "CSV", "資料下載網址": "https://test.gov.tw/a"},
        ]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "create", "--provider", "測試機關"])
        assert result.exit_code == 0
        slug = result.output.strip()
        assert slug == "test_gov_tw"
        assert (tmp_path / slug / "manifest.json").exists()


class TestDatasetList:
    def test_json_output(self, tmp_path, monkeypatch):
        manifest = {
            "type": "dataset",
            "provider": "測試機關",
            "slug": "test_gov_tw",
            "datasets": [
                {"id": "1001", "name": "資料A", "format": "csv", "urls": ["https://test.gov.tw/a"]},
                {"id": "1002", "name": "資料B", "format": "json", "urls": ["https://test.gov.tw/b"]},
            ],
        }
        pkg_dir = tmp_path / "test_gov_tw"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["id"] == "1001"

    def test_with_dir_flag(self, tmp_path, monkeypatch):
        manifest = {
            "type": "dataset",
            "provider": "測試機關",
            "slug": "test_gov_tw",
            "datasets": [{"id": "1001", "name": "資料A", "format": "csv", "urls": ["https://test.gov.tw/a"]}],
        }
        pkg_dir = tmp_path / "test_gov_tw"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["dataset", "--dir", "test_gov_tw", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


class TestDatasetClean:
    def test_clean_removes_files(self, tmp_path, monkeypatch):
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001.csv").write_text("data")
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "clean"])
        assert result.exit_code == 0
        assert not ds_dir.exists()


class TestWrongManifestType:
    def test_metadata_cmd_in_dataset_dir(self, tmp_path, monkeypatch):
        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "list"])
        assert result.exit_code != 0

    def test_dataset_cmd_in_metadata_dir(self, tmp_path, monkeypatch):
        manifest = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

```python
# tw_odc/__main__.py
"""Allow running as `python -m tw_odc`."""
from tw_odc.cli import app

if __name__ == "__main__":
    app()
```

```python
# tw_odc/cli.py
"""tw-odc CLI: Taiwan Open Data Checker."""

import asyncio
import json
import sys
from enum import StrEnum
from pathlib import Path

import typer

from tw_odc.manifest import (
    ManifestType,
    create_dataset_manifest,
    group_by_provider,
    load_manifest,
)

app = typer.Typer(name="tw-odc")
metadata_app = typer.Typer(help="metadata 資料來源操作")
dataset_app = typer.Typer(help="dataset 資料集操作")
app.add_typer(metadata_app, name="metadata")
app.add_typer(dataset_app, name="dataset")


class OutputFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


def _load_and_check(manifest_dir: Path, expected_type: ManifestType) -> dict:
    """Load manifest and verify type matches expected."""
    manifest = load_manifest(manifest_dir)
    actual = manifest.get("type")
    if actual != expected_type:
        print(
            f"錯誤: 預期 manifest type 為 '{expected_type}'，實際為 '{actual}'",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)
    return manifest


def _find_export_json(manifest: dict, manifest_dir: Path) -> Path:
    """Find the export-json file from a metadata manifest."""
    for ds in manifest["datasets"]:
        if ds["id"] == "export-json":
            filename = f"{ds['id']}.{ds['format']}"
            return manifest_dir / filename
    print("錯誤: manifest 中找不到 export-json 資料集", file=sys.stderr)
    raise typer.Exit(code=1)


def _output(data, fmt: OutputFormat) -> None:
    """Write data to stdout in the requested format."""
    if fmt == OutputFormat.JSON:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # One-line summary per entry
                    name = item.get("name") or item.get("provider") or str(item)
                    extra = {k: v for k, v in item.items() if k not in ("name", "provider")}
                    parts = [name]
                    if "count" in extra:
                        parts.append(f"({extra['count']} 筆)")
                    if "slug" in extra:
                        parts.append(f"[{extra['slug']}]")
                    print(" ".join(parts))
                else:
                    print(item)
        else:
            print(data)


# ─── metadata commands ───


@metadata_app.command("download")
def metadata_download(
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
    only: str | None = typer.Option(None, "--only", help="只下載指定檔案"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取"),
) -> None:
    """下載 metadata 檔案。"""
    from tw_odc.fetcher import fetch_all

    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    asyncio.run(fetch_all(manifest, cwd, only=only, no_cache=no_cache, cache_path=cwd / "etags.json"))


@metadata_app.command("list")
def metadata_list(
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """列出 metadata 中的所有機關。"""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"錯誤: {export_path} 不存在，請先執行 tw-odc metadata download", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    result = []
    for name, datasets in sorted(groups.items()):
        all_urls = [
            u.strip()
            for d in datasets
            for u in d["資料下載網址"].split(";")
            if u.strip()
        ]
        from tw_odc.manifest import compute_slug
        slug = compute_slug(name, all_urls)
        result.append({"provider": name, "slug": slug, "count": len(datasets)})

    _output(result, fmt)


@metadata_app.command("create")
def metadata_create(
    provider: str = typer.Option(..., "--provider", "-p", help="機關名稱"),
) -> None:
    """從 metadata 建立 dataset manifest。輸出資料夾路徑到 stdout。"""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"錯誤: {export_path} 不存在，請先執行 tw-odc metadata download", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if provider not in groups:
        print(f"錯誤: 找不到機關「{provider}」", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(cwd, provider, groups[provider])
    print(slug)


@metadata_app.command("update")
def metadata_update(
    provider: str | None = typer.Option(None, "--provider", "-p", help="機關名稱"),
    dir_path: str | None = typer.Option(None, "--dir", help="目標資料夾"),
) -> None:
    """更新既有的 dataset manifest。"""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"錯誤: {export_path} 不存在，請先執行 tw-odc metadata download", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if dir_path:
        # Find provider name from existing manifest
        target_dir = cwd / dir_path
        target_manifest = load_manifest(target_dir)
        provider = target_manifest["provider"]

    if not provider:
        print("錯誤: 請指定 --provider 或 --dir", file=sys.stderr)
        raise typer.Exit(code=1)

    if provider not in groups:
        print(f"錯誤: 找不到機關「{provider}」", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(cwd, provider, groups[provider])
    print(slug, file=sys.stderr)


# ─── dataset commands ───

_dataset_dir_option = typer.Option(None, "--dir", help="dataset 資料夾路徑")


@dataset_app.callback()
def dataset_callback(
    ctx: typer.Context,
    dir_path: str | None = _dataset_dir_option,
) -> None:
    """dataset 操作共用的 --dir 參數。"""
    ctx.ensure_object(dict)
    if dir_path:
        ctx.obj["dir"] = Path.cwd() / dir_path
    else:
        ctx.obj["dir"] = Path.cwd()


def _get_dataset_dir(ctx: typer.Context) -> Path:
    return ctx.obj["dir"]


@dataset_app.command("list")
def dataset_list(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """列出 dataset manifest 中的資料集。"""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    _output(manifest["datasets"], fmt)


@dataset_app.command("download")
def dataset_download(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="只下載指定 ID 的資料集"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取"),
) -> None:
    """下載 dataset 資料集。"""
    from tw_odc.fetcher import fetch_all

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    output_dir = pkg_dir / "datasets"

    only = None
    if dataset_id:
        # Find the dataset to determine filename
        for ds in manifest["datasets"]:
            if str(ds["id"]) == dataset_id:
                only = f"{ds['id']}.{ds['format']}"
                break
        else:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
            raise typer.Exit(code=1)

    asyncio.run(fetch_all(manifest, output_dir, only=only, no_cache=no_cache, cache_path=pkg_dir / "etags.json"))


@dataset_app.command("check")
def dataset_check(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="只檢查指定 ID 的資料集"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """檢查已下載的資料集。"""
    from tw_odc.inspector import inspect_dataset

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    targets = manifest["datasets"]
    if dataset_id:
        targets = [ds for ds in targets if str(ds["id"]) == dataset_id]
        if not targets:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
            raise typer.Exit(code=1)

    results = []
    for ds in targets:
        result = inspect_dataset(ds, datasets_dir)
        results.append({
            "id": result.dataset_id,
            "name": result.dataset_name,
            "declared_format": result.declared_format,
            "detected_formats": result.detected_formats,
            "file_exists": result.file_exists,
            "file_empty": result.file_empty,
            "issues": result.issues,
        })

    _output(results, fmt)


@dataset_app.command("score")
def dataset_score(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="只評分指定 ID 的資料集"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    from tw_odc.inspector import inspect_dataset
    from tw_odc.scorer import score_dataset

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    targets = manifest["datasets"]
    if dataset_id:
        targets = [ds for ds in targets if str(ds["id"]) == dataset_id]
        if not targets:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
            raise typer.Exit(code=1)

    results = []
    for ds in targets:
        inspection = inspect_dataset(ds, datasets_dir)
        score = score_dataset(inspection)
        results.append(score.to_dict())

    _output(results, fmt)


@dataset_app.command("clean")
def dataset_clean(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="只清除指定 ID 的檔案"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """清除下載的檔案。"""
    pkg_dir = _get_dataset_dir(ctx)
    _load_and_check(pkg_dir, ManifestType.DATASET)

    if dataset_id:
        # Clean specific dataset files
        datasets_dir = pkg_dir / "datasets"
        removed = []
        if datasets_dir.exists():
            for f in datasets_dir.glob(f"{dataset_id}.*"):
                f.unlink()
                removed.append(str(f.name))
            for f in datasets_dir.glob(f"{dataset_id}-*"):
                f.unlink()
                removed.append(str(f.name))
        _output({"removed": removed}, fmt)
    else:
        from tw_odc.fetcher import clean
        removed = clean(pkg_dir)
        _output({"removed": removed}, fmt)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tw_odc/cli.py tw_odc/__main__.py tests/test_cli.py
git commit -m "feat(tw_odc): add CLI with metadata and dataset subcommands"
```

---

### Task 5: 根目錄 manifest.json、.gitignore、pyproject.toml

**Files:**
- Create: `manifest.json` (root)
- Modify: `.gitignore`
- Modify: `pyproject.toml`

**Step 1: Create root manifest.json**

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
    }
  ]
}
```

**Step 2: Update .gitignore**

```gitignore
# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments
.venv

# Worktrees
.worktrees/

# Metadata downloads (root level)
/export-json.json
/export-csv.csv
/export-xml.xml

# Downloaded datasets
**/datasets/

# Fetcher runtime data
**/etags.json
**/issues.jsonl

# Scorer output
**/scores.json
```

**Step 3: Update pyproject.toml**

Add `jsonpatch` dependency and `tw-odc` script entry:

```toml
[project]
name = "roc-open-data-checker"
version = "0.1.0"
description = "Taiwan Open Data Checker — 台灣開放資料品質檢測工具"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "aiohttp>=3.13.3",
    "jsonpatch>=1.33",
    "python-magic>=0.4.27",
    "rich>=13.0.0",
    "typer>=0.24.1",
]

[project.scripts]
tw-odc = "tw_odc.cli:app"

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
]
```

**Step 4: Install new dependency**

Run: `uv add jsonpatch`

**Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: All PASS (tw_odc tests pass, old shared tests still pass for now)

**Step 6: Commit**

```bash
git add manifest.json .gitignore pyproject.toml uv.lock
git commit -m "feat: add root manifest.json, register tw-odc CLI, add jsonpatch dep"
```

---

### Task 6: 更新所有 dataset manifest 加入 type 欄位

**Files:**
- Modify: all `*/manifest.json` files (add `"type": "dataset"`)

**Step 1: Write a one-off script or do manually**

For each existing provider directory's `manifest.json`, add `"type": "dataset"` as the first field. This can be done with a small Python snippet:

```bash
uv run python -c "
import json
from pathlib import Path
for m in sorted(Path('.').glob('*/manifest.json')):
    if m.parent.name == 'tw_odc' or m.name == 'manifest.json' and m.parent == Path('.'):
        continue
    data = json.loads(m.read_text('utf-8'))
    if 'type' not in data:
        data = {'type': 'dataset', **data}
        m.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')
        print(f'Updated {m}')
"
```

**Step 2: Verify a few**

Run: `head -3 mof_gov_tw/manifest.json`
Expected: `"type": "dataset"` present

**Step 3: Commit**

```bash
git add */manifest.json
git commit -m "feat: add type field to all dataset manifests"
```

---

### Task 7: 刪除舊檔案 — shared/、main.py、舊測試

**Files:**
- Delete: `shared/` (entire directory)
- Delete: `main.py`
- Delete: `tests/test_main.py`
- Delete: `tests/test_scaffold.py`
- Delete: `tests/test_shared_cli.py`
- Delete: `tests/test_data_gov_tw.py`
- Delete: `tests/test_data_gov_tw_cli.py`
- Delete: `data_gov_tw/` (entire directory — manifest moved to root)

**Step 1: Delete files**

```bash
rm -rf shared/
rm main.py
rm tests/test_main.py tests/test_scaffold.py tests/test_shared_cli.py
rm tests/test_data_gov_tw.py tests/test_data_gov_tw_cli.py
rm -rf data_gov_tw/
```

**Step 2: Run tests**

Run: `uv run pytest -v`
Expected: All remaining tests PASS (test_manifest.py, test_fetcher.py, test_inspector.py, test_scorer.py, test_cli.py)

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: remove shared/, main.py, data_gov_tw/ — replaced by tw_odc"
```

---

### Task 8: 清理所有 provider 的 __init__.py 和 __main__.py

**Files:**
- Delete: all `*/__init__.py` and `*/__main__.py` in provider directories

**Step 1: Delete files**

```bash
uv run python -c "
from pathlib import Path
for m in sorted(Path('.').glob('*/manifest.json')):
    d = m.parent
    if d.name == 'tw_odc' or d.name == 'tests':
        continue
    for f in ('__init__.py', '__main__.py'):
        p = d / f
        if p.exists():
            p.unlink()
            print(f'Deleted {p}')
"
```

**Step 2: Verify tw-odc still works**

Run: `uv run tw-odc --help`
Expected: Shows metadata and dataset subcommands

Run: `uv run pytest -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove provider __init__.py and __main__.py — CLI replaces per-module entry points"
```

---

### Task 9: 更新 CLAUDE.md 和 README

**Files:**
- Modify: `CLAUDE.md`
- Modify (or create): `README.md` (jq 使用範例)

**Step 1: Update CLAUDE.md**

Update the Commands section and Architecture section to reflect the new `tw-odc` CLI. Remove references to `main.py`, `shared/`, `python -m <provider>`, and scaffolding. Add examples of `tw-odc metadata` and `tw-odc dataset` commands. Include `jq` examples for filtering metadata list output.

**Step 2: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update CLAUDE.md and README for tw-odc CLI"
```
