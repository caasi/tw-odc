# tw-odc i18n Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add i18n support to tw-odc CLI using i18nice, supporting `en` (default) and `zh-TW`.

**Architecture:** A thin `tw_odc/i18n.py` module wraps i18nice, providing `setup_locale()` and `t()`. JSON translation files live in `tw_odc/locales/`. The app-level Typer callback detects locale from `--lang` flag, `LANG`/`LC_ALL` env, or defaults to `en`. All runtime messages use `t()` with error codes `E0xx`/`E1xx`. Help text and docstrings are plain English (not translated).

**Tech Stack:** Python 3.13, i18nice, typer, pytest

---

### Task 1: Add i18nice dependency

**Files:**
- Modify: `pyproject.toml:7-13`

**Step 1: Add dependency**

```toml
dependencies = [
    "aiohttp>=3.13.3",
    "i18nice>=0.16.0",
    "jsonpatch>=1.33",
    "python-magic>=0.4.27",
    "rich>=13.0.0",
    "typer>=0.24.1",
]
```

**Step 2: Install**

Run: `uv sync`
Expected: resolves and installs i18nice

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add i18nice dependency for i18n support"
```

---

### Task 2: Create translation files

**Files:**
- Create: `tw_odc/locales/en.json`
- Create: `tw_odc/locales/zh-TW.json`

**Step 1: Create en.json**

```json
{
  "E001": "Expected manifest type '%{expected}', got '%{actual}'",
  "E002": "export-json dataset not found in manifest",
  "E003": "%{path} does not exist, run 'tw-odc metadata download' first",
  "E004": "Provider not found: '%{provider}'",
  "E005": "Please specify --provider or --dir",
  "E006": "Dataset not found: ID %{id}",
  "E106": "File not found: %{name}\nAvailable files: %{available}",
  "status.not_modified": "%{filename} (not modified)",
  "status.downloaded": "%{filename} (%{size} bytes)",
  "status.downloaded_ssl_skip": "%{filename} (%{size} bytes) (SSL verification skipped)",
  "status.rate_limited": "%{filename}: HTTP 429 — blocked all requests for %{domain}",
  "status.http_error": "%{filename}: HTTP %{status}",
  "status.skipped_blocked": "%{filename} (skipped, %{domain} blocked by 429)",
  "status.ssl_retry": "%{filename}: SSL error, retrying without verification",
  "status.retry_failed": "%{filename}: retry failed: %{error}",
  "status.network_error": "%{filename}: network error: %{error}",
  "status.unexpected_error": "%{filename}: unexpected error: %{error}",
  "summary.issues": "%{count} issue(s) recorded to %{path}",
  "output.count_suffix": "(%{count} datasets)",
  "output.partial": "(partial)"
}
```

**Step 2: Create zh-TW.json**

```json
{
  "E001": "預期 manifest type 為 '%{expected}'，實際為 '%{actual}'",
  "E002": "manifest 中找不到 export-json 資料集",
  "E003": "%{path} 不存在，請先執行 tw-odc metadata download",
  "E004": "找不到機關「%{provider}」",
  "E005": "請指定 --provider 或 --dir",
  "E006": "找不到 ID 為 %{id} 的資料集",
  "E106": "找不到檔案: %{name}\n可用的檔案: %{available}",
  "status.not_modified": "%{filename} (未變更)",
  "status.downloaded": "%{filename} (%{size} bytes)",
  "status.downloaded_ssl_skip": "%{filename} (%{size} bytes) (SSL 驗證跳過)",
  "status.rate_limited": "%{filename}: HTTP 429 — 已封鎖 %{domain} 的所有請求",
  "status.http_error": "%{filename}: HTTP %{status}",
  "status.skipped_blocked": "%{filename} (跳過, %{domain} 已被 429 封鎖)",
  "status.ssl_retry": "%{filename}: SSL 錯誤，嘗試跳過驗證重試",
  "status.retry_failed": "%{filename}: 重試失敗: %{error}",
  "status.network_error": "%{filename}: 網路錯誤: %{error}",
  "status.unexpected_error": "%{filename}: 非預期錯誤: %{error}",
  "summary.issues": "⚠ %{count} 個問題已記錄到 %{path}",
  "output.count_suffix": "(%{count} 筆)",
  "output.partial": "(部分)"
}
```

**Step 3: Commit**

```bash
git add tw_odc/locales/en.json tw_odc/locales/zh-TW.json
git commit -m "feat: add en and zh-TW translation files"
```

---

### Task 3: Create i18n module with tests (TDD)

**Files:**
- Create: `tests/test_i18n.py`
- Create: `tw_odc/i18n.py`

**Step 1: Write failing tests**

```python
# tests/test_i18n.py
import os
import pytest
from tw_odc.i18n import setup_locale, t, get_locale


class TestSetupLocale:
    def test_default_is_en(self):
        setup_locale()
        assert get_locale() == "en"

    def test_explicit_lang(self):
        setup_locale("zh-TW")
        assert get_locale() == "zh-TW"

    def test_env_lang_zh_tw(self, monkeypatch):
        monkeypatch.setenv("LANG", "zh_TW.UTF-8")
        setup_locale()
        assert get_locale() == "zh-TW"

    def test_env_lc_all_overrides_lang(self, monkeypatch):
        monkeypatch.setenv("LANG", "en_US.UTF-8")
        monkeypatch.setenv("LC_ALL", "zh_TW.UTF-8")
        setup_locale()
        assert get_locale() == "zh-TW"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("LANG", "zh_TW.UTF-8")
        setup_locale("en")
        assert get_locale() == "en"

    def test_unknown_env_falls_back_to_en(self, monkeypatch):
        monkeypatch.setenv("LANG", "fr_FR.UTF-8")
        monkeypatch.delenv("LC_ALL", raising=False)
        setup_locale()
        assert get_locale() == "en"


class TestTranslation:
    def test_en_error_code(self):
        setup_locale("en")
        result = t("E004", provider="TestOrg")
        assert "TestOrg" in result
        assert "Provider not found" in result

    def test_zh_tw_error_code(self):
        setup_locale("zh-TW")
        result = t("E004", provider="測試機關")
        assert "測試機關" in result
        assert "找不到機關" in result

    def test_en_status_message(self):
        setup_locale("en")
        result = t("status.not_modified", filename="test.csv")
        assert "test.csv" in result
        assert "not modified" in result

    def test_zh_tw_status_message(self):
        setup_locale("zh-TW")
        result = t("status.not_modified", filename="test.csv")
        assert "test.csv" in result
        assert "未變更" in result

    def test_missing_key_returns_key(self):
        setup_locale("en")
        result = t("nonexistent.key")
        assert "nonexistent.key" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_i18n.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tw_odc.i18n'`

**Step 3: Implement i18n module**

```python
# tw_odc/i18n.py
"""Internationalization support for tw-odc CLI."""

import os
from pathlib import Path

import i18n

_SUPPORTED = {"en", "zh-TW"}
_locale = "en"

# Configure i18nice
i18n.set("load_path", [str(Path(__file__).parent / "locales")])
i18n.set("file_format", "json")
i18n.set("fallback", "en")
i18n.set("error_on_missing_translation", False)


def _detect_env_locale() -> str:
    """Detect locale from LC_ALL or LANG environment variables."""
    env_val = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    # e.g. "zh_TW.UTF-8" → "zh-TW"
    code = env_val.split(".")[0]  # strip encoding
    if code.startswith("zh_TW") or code.startswith("zh-TW"):
        return "zh-TW"
    return "en"


def setup_locale(lang: str | None = None) -> None:
    """Initialize locale. Priority: explicit lang > env > default en."""
    global _locale
    if lang and lang in _SUPPORTED:
        _locale = lang
    elif lang is None:
        _locale = _detect_env_locale()
    else:
        _locale = "en"
    i18n.set("locale", _locale)


def get_locale() -> str:
    """Return the current locale string."""
    return _locale


def t(key: str, **kwargs) -> str:
    """Translate a message key with optional placeholders."""
    return i18n.t(key, locale=_locale, **kwargs)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_i18n.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add tests/test_i18n.py tw_odc/i18n.py
git commit -m "feat: add i18n module with locale detection and translation"
```

---

### Task 4: Add --lang flag to CLI app callback

**Files:**
- Modify: `tw_odc/cli.py:18-22`
- Modify: `tests/test_cli.py` (add lang flag tests)

**Step 1: Write failing test**

Add to `tests/test_cli.py`:

```python
class TestLangFlag:
    def test_default_locale_is_en(self, tmp_path, monkeypatch):
        """Without --lang, locale defaults to en."""
        manifest = {"type": "metadata", "provider": "data.gov.tw",
                    "datasets": [{"id": "export-json", "name": "JSON", "format": "json",
                                  "urls": ["https://data.gov.tw/datasets/export/json"]}]}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [{"提供機關": "X", "資料集識別碼": 1, "資料集名稱": "D",
                        "檔案格式": "CSV", "資料下載網址": "https://x.tw/d"}]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["metadata", "list"])
        assert result.exit_code == 0

    def test_lang_zh_tw(self, tmp_path, monkeypatch):
        """--lang zh-TW should produce Chinese error messages."""
        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--lang", "zh-TW", "metadata", "list"])
        assert result.exit_code != 0
        assert "E001" in result.output

    def test_lang_en(self, tmp_path, monkeypatch):
        """--lang en should produce English error messages."""
        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--lang", "en", "metadata", "list"])
        assert result.exit_code != 0
        assert "E001" in result.output
        assert "Expected manifest type" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestLangFlag -v`
Expected: FAIL

**Step 3: Add --lang callback to app**

In `cli.py`, add the import and app-level callback:

```python
from tw_odc.i18n import setup_locale, t
```

```python
@app.callback()
def main_callback(
    lang: str | None = typer.Option(None, "--lang", help="Language: en, zh-TW"),
) -> None:
    """Taiwan Open Data Checker CLI."""
    setup_locale(lang)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestLangFlag -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add tw_odc/cli.py tests/test_cli.py
git commit -m "feat: add --lang flag to CLI for locale selection"
```

---

### Task 5: Convert cli.py help text and docstrings to English

**Files:**
- Modify: `tw_odc/cli.py`

This is a non-TDD refactor — no behavior change, just string updates.

**Step 1: Replace all Chinese help/docstrings**

Changes (complete list):

```python
# line 19
metadata_app = typer.Typer(help="Metadata source operations")
# line 20
dataset_app = typer.Typer(help="Dataset operations")

# line 81 help strings
fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format")
only: str | None = typer.Option(None, "--only", help="Download only this file")
no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache")

# line 85 docstring
"""Download metadata files."""

# line 95 help
fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format")

# line 97 docstring
"""List all providers in metadata."""

# line 125 help
provider: str = typer.Option(..., "--provider", "-p", help="Provider name")

# line 127 docstring
"""Create a dataset manifest from metadata. Prints directory slug to stdout."""

# line 148 help
provider: str | None = typer.Option(None, "--provider", "-p", help="Provider name")
dir_path: str | None = typer.Option(None, "--dir", help="Target directory")

# line 151 docstring
"""Update an existing dataset manifest."""

# line 181
_dataset_dir_option = typer.Option(None, "--dir", help="Dataset directory path")

# line 189 docstring
"""Shared --dir option for dataset commands."""

# line 204 help
fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format")

# line 206 docstring
"""List datasets in a dataset manifest."""

# line 215 help
dataset_id: str | None = typer.Option(None, "--id", help="Download only this dataset ID")
no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache")

# line 218 docstring
"""Download datasets."""

# line 240-241 help
dataset_id: str | None = typer.Option(None, "--id", help="Check only this dataset ID")
fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format")

# line 242 docstring
"""Check downloaded datasets."""

# line 276 help
dataset_id: str | None = typer.Option(None, "--id", help="Score only this dataset ID")
fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format")

# line 278 docstring
"""Score downloaded datasets using the 5-Star model."""

# line 305-306 help
dataset_id: str | None = typer.Option(None, "--id", help="Clean only this dataset ID")
fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format")

# line 308 docstring
"""Clean downloaded files."""
```

**Step 2: Run all tests**

Run: `uv run pytest -v`
Expected: all PASS (no behavior change except string content)

**Step 3: Commit**

```bash
git add tw_odc/cli.py
git commit -m "refactor: convert CLI help text and docstrings to English"
```

---

### Task 6: Replace cli.py error messages with t() + error codes

**Files:**
- Modify: `tw_odc/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Update tests to expect error codes**

Update existing tests that check for Chinese error messages:

In `TestWrongManifestType.test_metadata_cmd_in_dataset_dir`:
```python
result = runner.invoke(app, ["metadata", "list"])
assert result.exit_code != 0
assert "E001" in result.output
```

In `TestWrongManifestType.test_dataset_cmd_in_metadata_dir`:
```python
result = runner.invoke(app, ["dataset", "list"])
assert result.exit_code != 0
assert "E001" in result.output
```

In `TestDatasetDownloadById.test_id_not_found`:
```python
result = runner.invoke(app, ["dataset", "download", "--id", "9999"])
assert result.exit_code != 0
assert "E006" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestWrongManifestType tests/test_cli.py::TestDatasetDownloadById::test_id_not_found -v`
Expected: FAIL — old Chinese messages don't contain error codes

**Step 3: Replace all error messages in cli.py**

Replace each `print(f"錯誤: ...")` with `print(f"E0xx: {t('E0xx', ...)}")`:

```python
# _load_and_check (line 36-38)
print(
    f"E001: {t('E001', expected=expected_type, actual=actual)}",
    file=sys.stderr,
)

# _find_export_json (line 49)
print(f"E002: {t('E002')}", file=sys.stderr)

# metadata_list (line 102)
print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)

# metadata_create (line 132) — same E003
print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)

# metadata_create (line 139)
print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)

# metadata_update (line 156) — same E003
print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)

# metadata_update (line 168)
print(f"E005: {t('E005')}", file=sys.stderr)

# metadata_update (line 172)
print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)

# dataset_download (line 229)
print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)

# dataset_check (line 253)
print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)

# dataset_score (line 290)
print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)

# dataset_clean (line 317)
print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)
```

Also replace the `_output` formatting string:

```python
# line 66: "({extra['count']} 筆)" → t()
if "count" in extra:
    parts.append(t("output.count_suffix", count=extra["count"]))
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add tw_odc/cli.py tests/test_cli.py
git commit -m "feat: replace CLI error messages with i18n error codes"
```

---

### Task 7: Replace fetcher.py messages with t()

**Files:**
- Modify: `tw_odc/fetcher.py`
- Modify: `tests/test_fetcher.py`

**Step 1: Update test that checks stderr messages**

In `test_fetch_all_only_no_match_prints_error`:
```python
async def test_fetch_all_only_no_match_prints_error(tmp_path, capsys):
    manifest, pkg_dir = _make_manifest(tmp_path, [
        {"id": "1001", "name": "Data", "format": "CSV", "urls": ["https://example.com/a.csv"]},
    ])
    await fetch_all(manifest, pkg_dir / "datasets", only="nonexistent.csv")
    captured = capsys.readouterr()
    assert "E106" in captured.err
    assert "1001.csv" in captured.err
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetcher.py::test_fetch_all_only_no_match_prints_error -v`
Expected: FAIL

**Step 3: Replace all messages in fetcher.py**

Add import at top:
```python
from tw_odc.i18n import t
```

Replace messages (inside `fetch_all` and its nested functions):

```python
# _do_download: line 224
_print(progress, f"[dim]—[/dim] {t('status.not_modified', filename=filename)}")

# _do_download: line 229
_print(progress, f"[red]✗[/red] {t('status.rate_limited', filename=filename, domain=domain)}")

# _do_download: line 233
_print(progress, f"[red]✗[/red] {t('status.http_error', filename=filename, status=resp.status)}")

# _download: line 253
_print(progress, f"[dim]—[/dim] {t('status.skipped_blocked', filename=filename, domain=domain)}")

# _download: line 261
_print(progress, f"[green]✓[/green] {t('status.downloaded', filename=filename, size=f'{size:,}')}")

# _download: line 263
_print(progress, f"[yellow]⚠[/yellow] {t('status.ssl_retry', filename=filename)}")

# _download: line 274
_print(progress, f"[green]✓[/green] {t('status.downloaded_ssl_skip', filename=filename, size=f'{size:,}')}")

# _download: line 276
_print(progress, f"[red]✗[/red] {t('status.retry_failed', filename=filename, error=retry_exc)}")

# _download: line 278
_print(progress, f"[red]✗[/red] {t('status.network_error', filename=filename, error=exc)}")

# _download: line 281
_print(progress, f"[red]✗[/red] {t('status.unexpected_error', filename=filename, error=exc)}")

# fetch_all: line 177
print(f"E106: {t('E106', name=only, available=available)}", file=sys.stderr)

# fetch_all: line 302
print(f"⚠ {t('summary.issues', count=len(issues), path=issues_path)}", file=sys.stderr)
```

Also replace `"etags.json (部分)"`, `"issues.jsonl (部分)"`, `"scores.json (部分)"` in `clean_dataset`:

```python
# line 80
removed.append(f"etags.json {t('output.partial')}")

# line 107
removed.append(f"issues.jsonl {t('output.partial')}")

# line 120
removed.append(f"scores.json {t('output.partial')}")
```

**Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: all PASS

Note: Some tests checking for specific Chinese strings like `"etags.json (部分)"` in `test_clean_dataset_removes_files_when_last_entry` will need updating:

```python
# Replace these assertions:
assert "etags.json (部分)" in removed
# With:
assert any("etags.json" in r for r in removed)
```

Do the same for `"issues.jsonl (部分)"` and `"scores.json (部分)"`.

**Step 5: Commit**

```bash
git add tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "feat: replace fetcher messages with i18n translations"
```

---

### Task 8: Final integration test and cleanup

**Files:**
- Modify: `tests/test_i18n.py` (add integration test)

**Step 1: Write integration test**

Add to `tests/test_i18n.py`:

```python
class TestIntegration:
    def test_all_keys_present_in_both_locales(self):
        """Every key in en.json must exist in zh-TW.json and vice versa."""
        import json
        from pathlib import Path

        locales_dir = Path(__file__).parent.parent / "tw_odc" / "locales"
        en = json.loads((locales_dir / "en.json").read_text(encoding="utf-8"))
        zh = json.loads((locales_dir / "zh-TW.json").read_text(encoding="utf-8"))
        assert set(en.keys()) == set(zh.keys()), (
            f"Missing in zh-TW: {set(en.keys()) - set(zh.keys())}, "
            f"Missing in en: {set(zh.keys()) - set(en.keys())}"
        )

    def test_cli_lang_flag_produces_chinese(self, tmp_path, monkeypatch):
        """End-to-end: --lang zh-TW should produce Chinese error output."""
        from typer.testing import CliRunner
        from tw_odc.cli import app

        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["--lang", "zh-TW", "metadata", "list"])
        assert result.exit_code != 0
        assert "E001" in result.output
        assert "預期" in result.output
```

**Step 2: Run all tests**

Run: `uv run pytest -v`
Expected: all PASS

**Step 3: Commit**

```bash
git add tests/test_i18n.py
git commit -m "test: add i18n integration tests for locale key parity and CLI"
```

---

## Summary of all changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `i18nice` dependency |
| `tw_odc/locales/en.json` | Create | English translations |
| `tw_odc/locales/zh-TW.json` | Create | Traditional Chinese translations |
| `tw_odc/i18n.py` | Create | Locale detection, `setup_locale()`, `t()` |
| `tw_odc/cli.py` | Modify | Add `--lang` flag, English help/docstrings, error codes + `t()` |
| `tw_odc/fetcher.py` | Modify | Replace hardcoded messages with `t()` |
| `tests/test_i18n.py` | Create | Unit + integration tests for i18n |
| `tests/test_cli.py` | Modify | Update assertions for error codes |
| `tests/test_fetcher.py` | Modify | Update assertions for translated messages |
