# Provider Scaffold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-generate a top-level Python package per provider organization from data.gov.tw metadata, each downloading its datasets via shared logic. Refactor `data_gov_tw` to the same manifest-based architecture.

**Architecture:** Every provider package contains only `__init__.py` (exposes `run()`) and `manifest.json` (dataset list). All download logic lives in `shared/fetcher.py`. A scaffolder in `shared/scaffold.py` reads `data_gov_tw/datasets/export.json` and generates all provider packages. `main.py` discovers providers dynamically by scanning for `manifest.json`.

**Tech Stack:** Python 3.13, aiohttp, asyncio, typer, rich, uv

---

### Task 1: shared/fetcher.py — generic manifest-based downloader

Extract download logic from `data_gov_tw/crawler.py` into a reusable fetcher that reads `manifest.json`.

**Files:**
- Create: `shared/fetcher.py`
- Create: `tests/test_fetcher.py`

**Step 1: Write the test**

Create `tests/test_fetcher.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_fetcher.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shared.fetcher'`

**Step 3: Write shared/fetcher.py**

Create `shared/fetcher.py`:

```python
import asyncio
import json
from pathlib import Path

import aiohttp
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn


def _load_manifest(init_file: str) -> tuple[Path, dict]:
    """Load manifest.json from the same directory as __init__.py."""
    pkg_dir = Path(init_file).parent
    manifest_path = pkg_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return pkg_dir, manifest


def _dest_filename(dataset: dict, url_index: int, url_count: int) -> str:
    """Derive destination filename from dataset id and format."""
    fmt = dataset["format"].lower()
    dataset_id = dataset["id"]
    if url_count == 1:
        return f"{dataset_id}.{fmt}"
    return f"{dataset_id}-{url_index + 1}.{fmt}"


async def fetch_all(init_file: str) -> None:
    """Download all datasets listed in manifest.json next to init_file."""
    pkg_dir, manifest = _load_manifest(init_file)
    output_dir = pkg_dir / "datasets"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all (url, dest) pairs
    downloads: list[tuple[str, Path]] = []
    for dataset in manifest["datasets"]:
        urls = dataset["urls"]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls))
            downloads.append((url, output_dir / filename))

    async def _download(
        session: aiohttp.ClientSession, url: str, dest: Path, progress: Progress
    ) -> None:
        filename = dest.name
        async with session.get(url) as resp:
            if resp.status != 200:
                progress.console.print(f"[red]✗[/red] {filename}: HTTP {resp.status}")
                return

            total = resp.content_length
            task = progress.add_task(filename, total=total or None)

            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))

            size = dest.stat().st_size
            progress.remove_task(task)
            progress.console.print(f"[green]✓[/green] {filename} ({size:,} bytes)")

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession() as session:
            await asyncio.gather(
                *[_download(session, url, dest, progress) for url, dest in downloads]
            )
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_fetcher.py -v
```

Expected: all 3 tests PASS

**Step 5: Commit**

```bash
git add shared/fetcher.py tests/test_fetcher.py
git commit -m "feat: add shared/fetcher.py — generic manifest-based downloader"
```

---

### Task 2: Refactor data_gov_tw to use manifest.json + shared/fetcher.py

Replace `data_gov_tw/crawler.py` with a `manifest.json` and thin `__init__.py`.

**Files:**
- Create: `data_gov_tw/manifest.json`
- Modify: `data_gov_tw/__init__.py`
- Modify: `data_gov_tw/__main__.py`
- Delete: `data_gov_tw/crawler.py`
- Rewrite: `tests/test_data_gov_tw_crawler.py` → `tests/test_data_gov_tw.py`

**Step 1: Create data_gov_tw/manifest.json**

```json
{
  "provider": "data.gov.tw",
  "slug": "data_gov_tw",
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

**Step 2: Rewrite data_gov_tw/__init__.py**

```python
from shared.fetcher import fetch_all


async def run() -> None:
    await fetch_all(__file__)
```

**Step 3: Rewrite data_gov_tw/__main__.py**

```python
import asyncio

import typer

from shared.fetcher import fetch_all

app = typer.Typer()


@app.command()
def crawl() -> None:
    """下載 data.gov.tw 的資料集匯出檔案（JSON、CSV、XML）。"""
    asyncio.run(fetch_all(__file__))


if __name__ == "__main__":
    app()
```

**Step 4: Delete data_gov_tw/crawler.py**

```bash
rm data_gov_tw/crawler.py
```

**Step 5: Rewrite tests**

Delete `tests/test_data_gov_tw_crawler.py`, create `tests/test_data_gov_tw.py`:

```python
import json
import subprocess
from pathlib import Path

import pytest


def test_manifest_has_three_datasets():
    manifest_path = Path("data_gov_tw/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["datasets"]) == 3
    assert all(
        any(url.startswith("https://data.gov.tw/") for url in ds["urls"])
        for ds in manifest["datasets"]
    )


def test_cli_module_runs():
    result = subprocess.run(
        ["uv", "run", "python", "-m", "data_gov_tw", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "data.gov.tw" in result.stdout
```

**Step 6: Run tests**

```bash
uv run pytest tests/test_data_gov_tw.py tests/test_fetcher.py -v
```

Expected: all tests PASS

**Step 7: Commit**

```bash
rm tests/test_data_gov_tw_crawler.py
git add data_gov_tw/ tests/
git add -u  # picks up deleted files
git commit -m "refactor: data_gov_tw uses manifest.json + shared/fetcher.py"
```

---

### Task 3: shared/scaffold.py — generate provider packages from export.json

**Files:**
- Create: `shared/scaffold.py`
- Create: `tests/test_scaffold.py`

**Step 1: Write the test**

Create `tests/test_scaffold.py`:

```python
import json
from pathlib import Path

import pytest

from shared.scaffold import derive_slug, group_by_provider, scaffold_provider


def test_derive_slug_single_domain():
    urls = ["https://www.mofti.gov.tw/download/abc", "https://www.mofti.gov.tw/download/def"]
    assert derive_slug(urls) == "mofti_gov_tw"


def test_derive_slug_strips_www():
    urls = ["https://www.example.gov.tw/data"]
    assert derive_slug(urls) == "example_gov_tw"


def test_derive_slug_multiple_domains_picks_most_frequent():
    urls = [
        "https://a.gov.tw/1",
        "https://b.gov.tw/2",
        "https://a.gov.tw/3",
    ]
    assert derive_slug(urls) == "a_gov_tw"


def test_derive_slug_strips_port():
    urls = ["https://api.example.com:8080/data"]
    assert derive_slug(urls) == "api_example_com"


def test_derive_slug_fallback_empty():
    assert derive_slug([]) == ""


def test_group_by_provider():
    datasets = [
        {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "資料1", "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/1"},
        {"提供機關": "A機關", "資料集識別碼": 2, "資料集名稱": "資料2", "檔案格式": "JSON", "資料下載網址": "https://a.gov.tw/2"},
        {"提供機關": "B機關", "資料集識別碼": 3, "資料集名稱": "資料3", "檔案格式": "CSV", "資料下載網址": "https://b.gov.tw/3"},
    ]
    groups = group_by_provider(datasets)
    assert len(groups) == 2
    assert len(groups["A機關"]) == 2
    assert len(groups["B機關"]) == 1


def test_scaffold_provider(tmp_path):
    datasets = [
        {"資料集識別碼": 1001, "資料集名稱": "測試資料", "檔案格式": "CSV", "資料下載網址": "https://www.test.gov.tw/a"},
        {"資料集識別碼": 1002, "資料集名稱": "另一筆", "檔案格式": "JSON;CSV", "資料下載網址": "https://www.test.gov.tw/b;https://www.test.gov.tw/c"},
    ]
    slug = scaffold_provider(tmp_path, "測試機關", datasets)

    assert slug == "test_gov_tw"
    pkg_dir = tmp_path / slug
    assert (pkg_dir / "__init__.py").exists()
    assert (pkg_dir / "manifest.json").exists()

    manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "測試機關"
    assert manifest["slug"] == "test_gov_tw"
    assert len(manifest["datasets"]) == 2
    assert manifest["datasets"][1]["urls"] == ["https://www.test.gov.tw/b", "https://www.test.gov.tw/c"]


def test_scaffold_provider_skips_existing(tmp_path):
    datasets = [
        {"資料集識別碼": 1, "資料集名稱": "資料", "檔案格式": "CSV", "資料下載網址": "https://www.test.gov.tw/a"},
    ]
    slug = scaffold_provider(tmp_path, "測試機關", datasets)
    # Modify the manifest to detect if it gets overwritten
    pkg_dir = tmp_path / slug
    (pkg_dir / "manifest.json").write_text("custom")

    slug2 = scaffold_provider(tmp_path, "測試機關", datasets)
    assert (pkg_dir / "manifest.json").read_text() == "custom"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scaffold.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write shared/scaffold.py**

```python
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


INIT_TEMPLATE = '''from shared.fetcher import fetch_all


async def run() -> None:
    await fetch_all(__file__)
'''

MAIN_TEMPLATE = '''import asyncio

import typer

from shared.fetcher import fetch_all

app = typer.Typer()


@app.command()
def crawl() -> None:
    """下載此機關的所有開放資料集。"""
    asyncio.run(fetch_all(__file__))


if __name__ == "__main__":
    app()
'''


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
            netloc = urlparse(url).netloc
            # Strip port
            netloc = netloc.split(":")[0]
            # Strip www.
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


def group_by_provider(datasets: list[dict]) -> dict[str, list[dict]]:
    """Group raw export.json entries by provider name."""
    groups: dict[str, list[dict]] = {}
    for d in datasets:
        provider = d["提供機關"]
        groups.setdefault(provider, []).append(d)
    return groups


def _parse_dataset(raw: dict) -> dict:
    """Convert a raw export.json entry to manifest dataset format."""
    urls = [u.strip() for u in raw["資料下載網址"].split(";") if u.strip()]
    formats = [f.strip() for f in raw["檔案格式"].split(";") if f.strip()]
    fmt = formats[0].lower() if formats else "bin"
    return {
        "id": str(raw["資料集識別碼"]),
        "name": raw["資料集名稱"],
        "format": fmt,
        "urls": urls,
    }


def scaffold_provider(
    base_dir: Path, provider_name: str, raw_datasets: list[dict]
) -> str:
    """Generate a provider package under base_dir. Returns the slug."""
    all_urls = []
    for d in raw_datasets:
        all_urls.extend(u.strip() for u in d["資料下載網址"].split(";") if u.strip())

    slug = derive_slug(all_urls)
    if not slug:
        # Fallback: hash of provider name
        slug = f"org_{abs(hash(provider_name)) % 10**8:08d}"

    pkg_dir = base_dir / slug
    if pkg_dir.exists():
        return slug

    pkg_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "provider": provider_name,
        "slug": slug,
        "datasets": [_parse_dataset(d) for d in raw_datasets],
    }

    (pkg_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (pkg_dir / "__init__.py").write_text(INIT_TEMPLATE)

    return slug
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_scaffold.py -v
```

Expected: all tests PASS

**Step 5: Commit**

```bash
git add shared/scaffold.py tests/test_scaffold.py
git commit -m "feat: add shared/scaffold.py — generates provider packages from metadata"
```

---

### Task 4: scaffold CLI entry point

**Files:**
- Create: `shared/__main__.py`

**Step 1: Write the test**

Add to `tests/test_scaffold.py`:

```python
def test_scaffold_cli_help():
    import subprocess

    result = subprocess.run(
        ["uv", "run", "python", "-m", "shared", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "scaffold" in result.stdout.lower() or "export.json" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scaffold.py::test_scaffold_cli_help -v
```

Expected: FAIL

**Step 3: Write shared/__main__.py**

```python
import json
from pathlib import Path

import typer

from shared.scaffold import group_by_provider, scaffold_provider

app = typer.Typer()


@app.command()
def scaffold(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    output_dir: Path = typer.Option(
        ".", help="產生 package 的根目錄"
    ),
) -> None:
    """從 data.gov.tw export.json 產生所有提供機關的 package。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    created = 0
    skipped = 0
    for provider, datasets in groups.items():
        pkg_dir = output_dir / scaffold_provider(output_dir, provider, datasets)
        if (pkg_dir / "manifest.json").stat().st_size > 0:
            created += 1
        else:
            skipped += 1

    print(f"完成: 產生 {created} 個 package（跳過 {skipped} 個已存在）")


if __name__ == "__main__":
    app()
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_scaffold.py -v
```

Expected: all tests PASS

**Step 5: Commit**

```bash
git add shared/__main__.py tests/test_scaffold.py
git commit -m "feat: add scaffold CLI (python -m shared export.json)"
```

---

### Task 5: Update main.py — dynamic provider discovery

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

**Step 1: Rewrite main.py**

```python
import asyncio
import importlib
from pathlib import Path

import typer

app = typer.Typer()

PROJECT_ROOT = Path(__file__).parent


def discover_providers() -> list[str]:
    """Find all directories containing manifest.json."""
    providers = []
    for manifest in sorted(PROJECT_ROOT.glob("*/manifest.json")):
        pkg_name = manifest.parent.name
        providers.append(pkg_name)
    return providers


async def _run_all(concurrency: int) -> None:
    providers = discover_providers()
    print(f"發現 {len(providers)} 個 provider")
    sem = asyncio.Semaphore(concurrency)

    async def _run_provider(name: str) -> None:
        async with sem:
            print(f"=== {name} ===")
            mod = importlib.import_module(name)
            await mod.run()

    tasks = [_run_provider(name) for name in providers]
    await asyncio.gather(*tasks)


@app.command()
def main(concurrency: int = typer.Option(3, help="同時執行的 provider 數量上限")) -> None:
    """執行所有 provider 的下載。"""
    asyncio.run(_run_all(concurrency))


if __name__ == "__main__":
    app()
```

**Step 2: Update tests/test_main.py**

```python
import subprocess
from pathlib import Path

from main import discover_providers


def test_main_help():
    result = subprocess.run(
        ["uv", "run", "python", "main.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "concurrency" in result.stdout.lower()


def test_discover_finds_data_gov_tw():
    providers = discover_providers()
    assert "data_gov_tw" in providers
```

**Step 3: Run tests**

```bash
uv run pytest tests/test_main.py tests/test_fetcher.py tests/test_data_gov_tw.py -v
```

Expected: all tests PASS

**Step 4: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "refactor: main.py discovers providers dynamically via manifest.json"
```

---

### Task 6: Integration test — scaffold + download first provider

**Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS

**Step 2: Run data_gov_tw download (verify refactored version works)**

```bash
uv run python -m data_gov_tw
```

Expected: downloads 3 files to `data_gov_tw/datasets/` with progress bars.

**Step 3: Scaffold one provider from export.json**

```bash
uv run python -m shared data_gov_tw/datasets/export.json --output-dir .
```

Expected: creates ~797 directories with `__init__.py` + `manifest.json`.

**Step 4: Verify first provider**

```bash
cat mofti_gov_tw/manifest.json | python3 -m json.tool | head -20
```

Expected: shows provider name and dataset list.

**Step 5: Download first provider**

```bash
uv run python -m mofti_gov_tw
```

Expected: downloads CSV files to `mofti_gov_tw/datasets/`.

**Step 6: Run orchestrator with first two providers**

```bash
uv run python main.py --concurrency 2
```

Expected: discovers all scaffolded providers, downloads concurrently.

**Step 7: Commit any fixes**

```bash
git add -A
git commit -m "test: verify scaffold and download integration"
```
