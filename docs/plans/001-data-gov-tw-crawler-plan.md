# data.gov.tw Crawler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Download all three bulk export files (JSON, CSV, XML) from data.gov.tw and save them locally, with an orchestrator that can run all portals with concurrency control.

**Architecture:** Each portal is a top-level Python package exposing an async `run()`. The orchestrator in `main.py` discovers portal packages by convention and runs them with a semaphore. The crawler uses `aiohttp` to download files to a gitignored `datasets/` directory.

**Tech Stack:** Python 3.13, aiohttp, asyncio, typer, uv

---

### Task 1: Project scaffolding — add dependencies and gitignore

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

**Step 1: Add dependencies**

```bash
uv add aiohttp typer
```

**Step 2: Update .gitignore to exclude datasets directories**

Append to `.gitignore`:
```
# Downloaded datasets
**/datasets/
```

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "chore: add aiohttp and typer dependencies, gitignore datasets"
```

---

### Task 2: data_gov_tw crawler module

**Files:**
- Create: `data_gov_tw/__init__.py`
- Create: `data_gov_tw/crawler.py`

**Step 1: Write the test**

Create `tests/test_data_gov_tw_crawler.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
uv add --dev pytest pytest-asyncio
uv run pytest tests/test_data_gov_tw_crawler.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'data_gov_tw'`

**Step 3: Write crawler.py**

Create `data_gov_tw/crawler.py`:

```python
from pathlib import Path

import aiohttp

EXPORTS = [
    "https://data.gov.tw/datasets/export/json",
    "https://data.gov.tw/datasets/export/csv",
    "https://data.gov.tw/datasets/export/xml",
]

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "datasets"


def _filename_from_url(url: str) -> str:
    ext = url.rsplit("/", 1)[-1]
    return f"export.{ext}"


async def crawl(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        for url in EXPORTS:
            filename = _filename_from_url(url)
            dest = output_dir / filename
            print(f"下載中: {url}")

            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"  失敗: HTTP {resp.status}")
                    continue

                data = await resp.read()
                dest.write_bytes(data)
                print(f"  完成: {dest} ({len(data)} bytes)")
```

Create `data_gov_tw/__init__.py`:

```python
import asyncio

from data_gov_tw.crawler import crawl


async def run() -> None:
    await crawl()
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_data_gov_tw_crawler.py -v
```

Expected: all 3 tests PASS

**Step 5: Commit**

```bash
git add data_gov_tw/ tests/test_data_gov_tw_crawler.py
git commit -m "feat: add data_gov_tw crawler — downloads JSON/CSV/XML exports"
```

---

### Task 3: data_gov_tw CLI entry point

**Files:**
- Create: `data_gov_tw/__main__.py`

**Step 1: Write the test**

Add to `tests/test_data_gov_tw_crawler.py`:

```python
import subprocess


def test_cli_module_runs():
    result = subprocess.run(
        ["uv", "run", "python", "-m", "data_gov_tw", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "crawl" in result.stdout
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_data_gov_tw_crawler.py::test_cli_module_runs -v
```

Expected: FAIL — no `__main__.py`

**Step 3: Write __main__.py**

Create `data_gov_tw/__main__.py`:

```python
import asyncio

import typer

from data_gov_tw.crawler import crawl

app = typer.Typer()


@app.command()
def do_crawl() -> None:
    """下載 data.gov.tw 的資料集匯出檔案（JSON、CSV、XML）。"""
    asyncio.run(crawl())


if __name__ == "__main__":
    app()
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_data_gov_tw_crawler.py::test_cli_module_runs -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add data_gov_tw/__main__.py tests/test_data_gov_tw_crawler.py
git commit -m "feat: add data_gov_tw CLI entry point (python -m data_gov_tw crawl)"
```

---

### Task 4: shared package placeholder

**Files:**
- Create: `shared/__init__.py`

**Step 1: Create shared package**

Create `shared/__init__.py`:

```python
# Shared utilities for all portal packages.
```

**Step 2: Commit**

```bash
git add shared/__init__.py
git commit -m "chore: add shared package placeholder"
```

---

### Task 5: main.py orchestrator

**Files:**
- Modify: `main.py`

**Step 1: Write the test**

Create `tests/test_main.py`:

```python
import subprocess


def test_main_help():
    result = subprocess.run(
        ["uv", "run", "python", "main.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "concurrency" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py -v
```

Expected: FAIL — main.py doesn't accept --help / --concurrency

**Step 3: Write main.py**

Replace `main.py`:

```python
import asyncio
import importlib
import pkgutil
from pathlib import Path

import typer

# Portal packages live at the project root and expose an async run().
PORTAL_PACKAGES = [
    "data_gov_tw",
]

app = typer.Typer()


async def _run_all(concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)

    async def _run_portal(name: str) -> None:
        async with sem:
            print(f"=== {name} ===")
            mod = importlib.import_module(name)
            await mod.run()

    tasks = [_run_portal(name) for name in PORTAL_PACKAGES]
    await asyncio.gather(*tasks)


@app.command()
def main(concurrency: int = typer.Option(3, help="同時執行的 portal 數量上限")) -> None:
    """執行所有 portal 的爬蟲。"""
    asyncio.run(_run_all(concurrency))


if __name__ == "__main__":
    app()
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add orchestrator — runs all portals with concurrency control"
```

---

### Task 6: Integration smoke test

**Step 1: Run data_gov_tw crawler against the real server**

```bash
uv run python -m data_gov_tw crawl
```

Expected: downloads 3 files to `data_gov_tw/datasets/`, prints progress with byte counts.

**Step 2: Verify files exist**

```bash
ls -la data_gov_tw/datasets/
```

Expected: `export.json`, `export.csv`, `export.xml` all present with non-zero sizes.

**Step 3: Run orchestrator**

```bash
uv run python main.py --concurrency 1
```

Expected: same output, prefixed with `=== data_gov_tw ===`.

**Step 4: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

**Step 5: Commit any fixes if needed, then final commit**

```bash
git add -A
git commit -m "test: verify integration with data.gov.tw"
```
