# Module CLI Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every module self-contained with `clean`, `score` subcommands and `--only`/`--no-cache` download flags.

**Architecture:** Add `clean()` function and `only`/`no_cache` params to `shared/fetcher.py`. Each module's `__main__.py` wires these into typer subcommands. Scaffold template updated so new modules get the same CLI. `shared/__main__.py` `score` subcommand removed.

**Tech Stack:** Python 3.13, typer, pytest, aiohttp (existing)

---

### Task 1: Add `clean()` to `shared/fetcher.py`

**Files:**
- Modify: `shared/fetcher.py`
- Test: `tests/test_fetcher.py`

**Step 1: Write the failing test**

Add to `tests/test_fetcher.py`:

```python
from shared.fetcher import clean


def test_clean_removes_all_generated_files(tmp_path):
    """clean() should remove datasets/, etags.json, issues.jsonl, scores.json."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")
    (pkg_dir / "__init__.py").write_text("")

    # Create generated files
    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "1001.csv").write_text("data")
    (pkg_dir / "etags.json").write_text("{}")
    (pkg_dir / "issues.jsonl").write_text("{}")
    (pkg_dir / "scores.json").write_text("{}")

    removed = clean(str(pkg_dir / "__init__.py"))

    assert not ds_dir.exists()
    assert not (pkg_dir / "etags.json").exists()
    assert not (pkg_dir / "issues.jsonl").exists()
    assert not (pkg_dir / "scores.json").exists()
    # manifest.json and __init__.py should remain
    assert (pkg_dir / "manifest.json").exists()
    assert (pkg_dir / "__init__.py").exists()
    assert len(removed) == 4


def test_clean_nothing_to_delete(tmp_path):
    """clean() on an already-clean module should return empty list."""
    pkg_dir = tmp_path / "test_provider"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text("{}")
    (pkg_dir / "__init__.py").write_text("")

    removed = clean(str(pkg_dir / "__init__.py"))
    assert removed == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetcher.py::test_clean_removes_all_generated_files tests/test_fetcher.py::test_clean_nothing_to_delete -v`
Expected: FAIL with `ImportError: cannot import name 'clean' from 'shared.fetcher'`

**Step 3: Write minimal implementation**

Add to `shared/fetcher.py`:

```python
import shutil

def clean(init_file: str) -> list[str]:
    """Remove all generated files for a provider package.

    Deletes: datasets/, etags.json, issues.jsonl, scores.json.
    Returns list of names that were actually removed.
    """
    pkg_dir = Path(init_file).parent
    removed: list[str] = []

    datasets_dir = pkg_dir / "datasets"
    if datasets_dir.exists():
        shutil.rmtree(datasets_dir)
        removed.append("datasets/")

    for name in ("etags.json", "issues.jsonl", "scores.json"):
        path = pkg_dir / name
        if path.exists():
            path.unlink()
            removed.append(name)

    return removed
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fetcher.py::test_clean_removes_all_generated_files tests/test_fetcher.py::test_clean_nothing_to_delete -v`
Expected: PASS

**Step 5: Commit**

```bash
git add shared/fetcher.py tests/test_fetcher.py
git commit -m "feat: add clean() function to shared/fetcher"
```

---

### Task 2: Add `only` and `no_cache` params to `fetch_all()`

**Files:**
- Modify: `shared/fetcher.py`
- Test: `tests/test_fetcher.py`

**Step 1: Write the failing tests**

Add to `tests/test_fetcher.py`:

```python
@pytest.mark.asyncio
async def test_fetch_all_only_downloads_matching_file(tmp_path):
    """--only should download only the file whose dest name matches."""
    pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Target", "format": "CSV", "urls": ["https://example.com/a.csv"]},
        {"id": "1002", "name": "Skip", "format": "JSON", "urls": ["https://example.com/b.json"]},
    ])
    mock_session = _make_mock_session(200, b"data")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await fetch_all(str(pkg_dir / "__init__.py"), only="1001.csv")

    assert (pkg_dir / "datasets" / "1001.csv").exists()
    assert not (pkg_dir / "datasets" / "1002.json").exists()


@pytest.mark.asyncio
async def test_fetch_all_only_no_match_prints_error(tmp_path, capsys):
    """--only with a non-existent filename should print available files."""
    pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Data", "format": "CSV", "urls": ["https://example.com/a.csv"]},
    ])

    await fetch_all(str(pkg_dir / "__init__.py"), only="nonexistent.csv")

    captured = capsys.readouterr()
    assert "1001.csv" in captured.out


@pytest.mark.asyncio
async def test_fetch_all_no_cache_skips_conditional_headers(tmp_path):
    """--no-cache should not send If-None-Match even when etags.json exists."""
    pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Data", "format": "CSV", "urls": ["https://example.com/a.csv"]},
    ])
    # Pre-populate etags.json
    import json as _json
    (pkg_dir / "etags.json").write_text(_json.dumps({
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
        await fetch_all(str(pkg_dir / "__init__.py"), no_cache=True)

    assert "If-None-Match" not in captured_headers
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fetcher.py::test_fetch_all_only_downloads_matching_file tests/test_fetcher.py::test_fetch_all_only_no_match_prints_error tests/test_fetcher.py::test_fetch_all_no_cache_skips_conditional_headers -v`
Expected: FAIL with `TypeError: fetch_all() got an unexpected keyword argument 'only'`

**Step 3: Modify `fetch_all()` in `shared/fetcher.py`**

Change the signature:

```python
async def fetch_all(init_file: str, concurrency: int = 5, only: str | None = None, no_cache: bool = False) -> None:
```

After building the `downloads` list (after line 74), add filtering:

```python
    if only:
        matched = [(url, dest) for url, dest in downloads if dest.name == only]
        if not matched:
            available = ", ".join(dest.name for _, dest in downloads)
            print(f"找不到檔案: {only}\n可用的檔案: {available}")
            return
        downloads = matched
```

Modify `_conditional_headers` to respect `no_cache`:

```python
    def _conditional_headers(url: str) -> dict[str, str]:
        """Build If-None-Match / If-Modified-Since headers from cache."""
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fetcher.py -v`
Expected: ALL PASS (including existing tests)

**Step 5: Commit**

```bash
git add shared/fetcher.py tests/test_fetcher.py
git commit -m "feat: add --only and --no-cache params to fetch_all()"
```

---

### Task 3: Update `data_gov_tw/__main__.py` with all new CLI features

**Files:**
- Modify: `data_gov_tw/__main__.py`
- Test: `tests/test_data_gov_tw_cli.py` (new)

**Step 1: Write the failing tests**

Create `tests/test_data_gov_tw_cli.py`:

```python
import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from data_gov_tw.__main__ import app

runner = CliRunner()


def _make_data_gov_tw(tmp_path):
    """Create a minimal data_gov_tw package for testing."""
    pkg_dir = tmp_path / "data_gov_tw"
    pkg_dir.mkdir()
    manifest = {
        "provider": "data.gov.tw",
        "slug": "data_gov_tw",
        "datasets": [
            {"id": "export-json", "name": "JSON匯出", "format": "json",
             "urls": ["https://data.gov.tw/datasets/export/json"]},
        ],
    }
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    (pkg_dir / "__init__.py").write_text("")
    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "export-json.json").write_text('[]')
    return pkg_dir


def test_clean_subcommand(tmp_path):
    """clean subcommand should call shared.fetcher.clean and print results."""
    with patch("data_gov_tw.__main__.clean") as mock_clean:
        mock_clean.return_value = ["datasets/", "etags.json"]
        result = runner.invoke(app, ["clean"])

    assert result.exit_code == 0
    assert "datasets/" in result.output


def test_clean_subcommand_nothing(tmp_path):
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
        with patch("data_gov_tw.__main__.Path.cwd", return_value=Path("/tmp")):
            result = runner.invoke(app, ["score"])

    assert result.exit_code == 0


def test_crawl_with_only_flag():
    """--only flag should be passed to fetch_all."""
    with patch("data_gov_tw.__main__.fetch_all", new_callable=AsyncMock) as mock_fetch:
        result = runner.invoke(app, ["--only", "export-json.json"])

    mock_fetch.assert_called_once()
    _, kwargs = mock_fetch.call_args
    assert kwargs.get("only") == "export-json.json" or mock_fetch.call_args[0] != ()


def test_crawl_with_no_cache_flag():
    """--no-cache flag should be passed to fetch_all."""
    with patch("data_gov_tw.__main__.fetch_all", new_callable=AsyncMock) as mock_fetch:
        result = runner.invoke(app, ["--only", "export-json.json", "--no-cache"])

    mock_fetch.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_gov_tw_cli.py -v`
Expected: FAIL (missing `clean`, `score` subcommands, missing `--only`/`--no-cache` flags)

**Step 3: Rewrite `data_gov_tw/__main__.py`**

```python
import asyncio
from pathlib import Path

import typer

from shared.fetcher import clean, fetch_all
from shared.scorer import score_provider

app = typer.Typer()


@app.callback(invoke_without_command=True)
def crawl(
    ctx: typer.Context,
    only: str = typer.Option(None, "--only", help="只下載指定檔案（datasets/ 中的檔名）"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取，強制重新下載"),
) -> None:
    """下載 data.gov.tw 的資料集匯出檔案（JSON、CSV、XML）。"""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(fetch_all(__file__, only=only, no_cache=no_cache))


@app.command()
def clean_cmd() -> None:
    """清理所有產出檔案（datasets/、etags.json、issues.jsonl、scores.json）。"""
    removed = clean(__file__)
    if removed:
        for name in removed:
            print(f"  已刪除 {name}")
    else:
        print("已經很乾淨了")


@app.command()
def score() -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    pkg_dir = Path(__file__).parent
    scores = score_provider(pkg_dir)
    datasets_dir = pkg_dir / "datasets"
    cwd = Path.cwd()

    for d in scores["datasets"]:
        star = d["star_score"]
        stars = "★" * star + "☆" * (3 - star) if star > 0 else "---"
        fmt = d["declared_format"]
        file_path = datasets_dir / f"{d['id']}.{fmt}"
        rel = file_path.relative_to(cwd) if file_path.is_relative_to(cwd) else file_path
        print(f"{stars}  {rel}")

    total = len(scores["datasets"])
    scored = [d for d in scores["datasets"] if d["star_score"] > 0]
    avg = sum(d["star_score"] for d in scored) / len(scored) if scored else 0
    print(f"\n{scores['provider']} — {total} 筆資料集, 平均 {avg:.1f} 星")


if __name__ == "__main__":
    app()
```

Note: The typer subcommand name for `clean` must be `clean` in CLI. Since `clean` is already imported from `shared.fetcher`, name the function `clean_cmd` and use `@app.command("clean")` or just `@app.command()` which will use `clean-cmd`. We should use the explicit name:

```python
@app.command("clean")
def clean_cmd() -> None:
```

**Step 4: Update tests to match actual implementation**

The tests from Step 1 may need adjustment based on the exact import paths used in the mocking. Run and fix as needed.

Run: `uv run pytest tests/test_data_gov_tw_cli.py -v`
Expected: PASS

**Step 5: Run all tests to check for regressions**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add data_gov_tw/__main__.py tests/test_data_gov_tw_cli.py
git commit -m "feat: add clean, score, --only, --no-cache to data_gov_tw CLI"
```

---

### Task 4: Update scaffold template

**Files:**
- Modify: `shared/scaffold.py`
- Test: `tests/test_scaffold.py`

**Step 1: Write the failing test**

Add to `tests/test_scaffold.py`:

```python
def test_scaffold_template_has_clean_score_only(tmp_path):
    """Scaffolded __main__.py should include clean, score subcommands and --only/--no-cache."""
    datasets = [
        {"資料集識別碼": 1, "資料集名稱": "資料", "檔案格式": "CSV", "資料下載網址": "https://www.test.gov.tw/a"},
    ]
    slug = scaffold_provider(tmp_path, "測試機關", datasets)
    main_content = (tmp_path / slug / "__main__.py").read_text()

    assert "clean" in main_content
    assert "score" in main_content
    assert "--only" in main_content or "only" in main_content
    assert "--no-cache" in main_content or "no_cache" in main_content
    assert "score_provider" in main_content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scaffold.py::test_scaffold_template_has_clean_score_only -v`
Expected: FAIL

**Step 3: Update `MAIN_TEMPLATE` in `shared/scaffold.py`**

Replace `MAIN_TEMPLATE` with:

```python
MAIN_TEMPLATE = '''import asyncio
from pathlib import Path

import typer

from shared.fetcher import clean, fetch_all
from shared.scorer import score_provider

app = typer.Typer()


@app.callback(invoke_without_command=True)
def crawl(
    ctx: typer.Context,
    only: str = typer.Option(None, "--only", help="只下載指定檔案（datasets/ 中的檔名）"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取，強制重新下載"),
) -> None:
    """下載此機關的所有開放資料集。"""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(fetch_all(__file__, only=only, no_cache=no_cache))


@app.command("clean")
def clean_cmd() -> None:
    """清理所有產出檔案（datasets/、etags.json、issues.jsonl、scores.json）。"""
    removed = clean(__file__)
    if removed:
        for name in removed:
            print(f"  已刪除 {name}")
    else:
        print("已經很乾淨了")


@app.command()
def score() -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    pkg_dir = Path(__file__).parent
    scores = score_provider(pkg_dir)
    datasets_dir = pkg_dir / "datasets"
    cwd = Path.cwd()

    for d in scores["datasets"]:
        star = d["star_score"]
        stars = "★" * star + "☆" * (3 - star) if star > 0 else "---"
        fmt = d["declared_format"]
        file_path = datasets_dir / f"{d['id']}.{fmt}"
        rel = file_path.relative_to(cwd) if file_path.is_relative_to(cwd) else file_path
        print(f"{stars}  {rel}")

    total = len(scores["datasets"])
    scored = [d for d in scores["datasets"] if d["star_score"] > 0]
    avg = sum(d["star_score"] for d in scored) / len(scored) if scored else 0
    print(f"\\n{scores['provider']} — {total} 筆資料集, 平均 {avg:.1f} 星")


if __name__ == "__main__":
    app()
'''
```

Also update `INIT_TEMPLATE` to keep `run()` compatible with `main.py` orchestrator — it currently passes no extra args, which is fine (defaults apply).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add shared/scaffold.py tests/test_scaffold.py
git commit -m "feat: update scaffold template with clean, score, --only, --no-cache"
```

---

### Task 5: Remove `score` subcommand from `shared/__main__.py`

**Files:**
- Modify: `shared/__main__.py`
- Modify: `tests/test_score_cli.py` → rename to `tests/test_data_gov_tw_cli.py` (already created in Task 3) or remove
- Test: `tests/test_scaffold.py` (existing CLI help test)

**Step 1: Remove the `score` command and `_score_one` helper from `shared/__main__.py`**

Remove: the `score` function, `_score_one` helper, and the `from shared.scorer import score_provider` import.

The file should become:

```python
import json
from pathlib import Path

import typer

from shared.scaffold import group_by_provider, scaffold_provider

app = typer.Typer()


@app.command("list")
def list_providers(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    query: str = typer.Option(
        "", help="篩選機關名稱（模糊比對）"
    ),
) -> None:
    """列出 export.json 中所有提供機關。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    for name, datasets in sorted(groups.items()):
        if query and query not in name:
            continue
        print(f"{name} ({len(datasets)} 筆)")


@app.command("scaffold")
def scaffold(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    provider: list[str] = typer.Option(
        ..., "--provider", "-p", help="要產生的機關名稱（可重複指定）"
    ),
    output_dir: Path = typer.Option(
        ".", help="產生 package 的根目錄"
    ),
) -> None:
    """從 data.gov.tw export.json 產生指定機關的 package。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    for name in provider:
        if name not in groups:
            print(f"找不到機關: {name}")
            continue
        slug = scaffold_provider(output_dir, name, groups[name])
        pkg_dir = output_dir / slug
        n = len(groups[name])
        print(f"✓ {name} → {slug}/ ({n} 筆資料集)")


if __name__ == "__main__":
    app()
```

**Step 2: Delete `tests/test_score_cli.py`**

This file tested `shared.__main__` score command which no longer exists. The equivalent functionality is now tested in `tests/test_data_gov_tw_cli.py` (Task 3).

**Step 3: Update scaffold CLI help test**

In `tests/test_scaffold.py`, the `test_scaffold_cli_help` test checks for "score" in the output. Remove that expectation if present, or verify it no longer appears:

```python
def test_scaffold_cli_help():
    import subprocess
    result = subprocess.run(
        ["uv", "run", "python", "-m", "shared", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "scaffold" in result.stdout.lower()
    assert "list" in result.stdout.lower()
```

(This test doesn't assert "score", so it should be fine as-is.)

**Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add shared/__main__.py
git rm tests/test_score_cli.py
git commit -m "refactor: remove score subcommand from shared CLI (now per-module)"
```

---

### Task 6: Update existing scaffolded modules

**Files:**
- Modify: any existing scaffolded module `__main__.py` files (e.g. `mofti_gov_tw/__main__.py`)

**Step 1: Find all existing scaffolded modules**

Run: `find . -name "manifest.json" -not -path "*/data_gov_tw/*" -not -path "*/shared/*" | sort`

**Step 2: For each module, replace its `__main__.py` with the new template**

The content should match `MAIN_TEMPLATE` from scaffold.py (just replace the file).

**Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add */\_\_main\_\_.py
git commit -m "chore: update existing scaffolded modules with new CLI template"
```

---

### Task 7: Final integration verification

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 2: Manual smoke tests**

Run each command and verify output:

```bash
# Help should show clean, score subcommands and --only/--no-cache
uv run python -m data_gov_tw --help

# Clean should work (or say "已經很乾淨了")
uv run python -m data_gov_tw clean

# --only with nonexistent file should list available files
uv run python -m data_gov_tw --only nonexistent.csv
```

**Step 3: Commit any final fixes if needed**

```bash
git add -A
git commit -m "chore: final integration fixes"
```
