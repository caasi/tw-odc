# 011 — 發布 tw-odc 到 PyPI：實作計畫

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 tw-odc 遷移到 src layout、加入跨平台 metadata 路徑解析、並發布到 PyPI。

**Architecture:** 搬移 `tw_odc/` 到 `src/tw_odc/`，新增 `paths.py` 處理 `data_dir()` 路徑邏輯（`$PWD` 優先、fallback 到 `platformdirs`），metadata 指令加 `--dir` 選項，bootstrap 機制在首次使用時複製內建 manifest，URL HEAD 預檢確保連結可達。

**Tech Stack:** Python 3.13, uv, uv_build, platformdirs, typer, aiohttp, pytest

**Spec:** `docs/plans/011-pypi-publish-design.md`

---

## Chunk 1: src Layout 遷移與 pyproject.toml

### Task 1: 搬移 `tw_odc/` 到 `src/tw_odc/`

**Files:**
- Move: `tw_odc/` → `src/tw_odc/`

- [ ] **Step 1: 建立 src 目錄並搬移**

```bash
mkdir -p src
git mv tw_odc src/tw_odc
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "refactor: move tw_odc/ to src/tw_odc/ for src layout"
```

### Task 2: 更新 `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 build-system、新增 platformdirs、調整 pythonpath**

```toml
[build-system]
requires = ["uv_build>=0.10.9,<0.11.0"]
build-backend = "uv_build"

[project]
name = "tw-odc"
version = "0.1.0"
description = "Taiwan Open Data Checker — 台灣開放資料品質檢測工具"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "aiohttp>=3.13.3",
    "chardet>=7.0.1",
    "i18nice>=0.16.0",
    "jsonpatch>=1.33",
    "platformdirs>=4.0",
    "python-magic>=0.4.27",
    "rich>=13.0.0",
    "typer>=0.24.1",
]

[project.scripts]
tw-odc = "tw_odc.cli:app"

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
]
```

刪除以下區段：
```toml
# 刪除
[tool.setuptools.packages.find]
include = ["tw_odc*"]

[tool.setuptools.package-data]
tw_odc = ["locales/*.json"]
```

- [ ] **Step 2: 同步依賴**

Run: `uv sync`
Expected: 成功安裝所有依賴（含新增的 platformdirs）

- [ ] **Step 3: 修正 test_i18n.py 中 locales 路徑**

`tests/test_i18n.py:76` 的 `TestIntegration.test_all_keys_present_in_both_locales` 用 `Path(__file__).parent.parent / "tw_odc" / "locales"` 硬寫路徑。改為使用 `importlib.resources`：

```python
from importlib.resources import files
locales_dir = Path(str(files("tw_odc").joinpath("locales")))
```

- [ ] **Step 4: 跑全部測試確認遷移正確**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_i18n.py
git commit -m "build: switch to uv_build, add platformdirs, update pythonpath for src layout"
```

---

## Chunk 2: `paths.py` — 路徑解析模組

### Task 3: 建立 `paths.py` 及測試

**Files:**
- Create: `src/tw_odc/paths.py`
- Create: `tests/test_paths.py`

- [ ] **Step 1: 寫 `_config_dir` 的失敗測試**

```python
# tests/test_paths.py
import sys
from pathlib import Path

from tw_odc.paths import _config_dir


class TestConfigDir:
    def test_unix_returns_xdg_path(self, monkeypatch):
        """Linux/macOS should return ~/.config/tw-odc/."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = _config_dir()
        assert result == Path.home() / ".config" / "tw-odc"

    def test_macos_returns_xdg_path(self, monkeypatch):
        """macOS should also return ~/.config/tw-odc/ (not ~/Library/...)."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = _config_dir()
        assert result == Path.home() / ".config" / "tw-odc"

    def test_respects_xdg_config_home(self, monkeypatch):
        """Should respect XDG_CONFIG_HOME env var."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        result = _config_dir()
        assert result == Path("/custom/config/tw-odc")
```

Run: `uv run pytest tests/test_paths.py -v`
Expected: FAIL — `tw_odc.paths` does not exist

- [ ] **Step 2: 實作 `_config_dir`**

```python
# src/tw_odc/paths.py
"""Path resolution for tw-odc metadata storage."""

import json
import sys
from pathlib import Path

APP_NAME = "tw-odc"


def _config_dir() -> Path:
    """回傳跨平台的使用者設定目錄。

    - Linux: ~/.config/tw-odc/（XDG）
    - macOS: ~/.config/tw-odc/（強制 XDG，不用 ~/Library/Application Support/）
    - Windows: C:/Users/<user>/AppData/Local/tw-odc/
    """
    if sys.platform == "win32":
        from platformdirs.windows import Windows
        return Path(Windows(APP_NAME).user_config_dir)
    else:
        from platformdirs.unix import Unix
        return Path(Unix(APP_NAME).user_config_dir)
```

Run: `uv run pytest tests/test_paths.py::TestConfigDir -v`
Expected: PASS

- [ ] **Step 3: 寫 `data_dir` 的失敗測試**

在 `tests/test_paths.py` 加入：

```python
import json

from tw_odc.paths import data_dir


class TestDataDir:
    def test_cwd_with_metadata_manifest(self, tmp_path, monkeypatch):
        """$PWD with type=metadata manifest → return $PWD."""
        manifest = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)
        assert data_dir() == tmp_path

    def test_cwd_with_dataset_manifest_falls_back(self, tmp_path, monkeypatch):
        """$PWD with type=dataset manifest → fallback to config dir."""
        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = data_dir()
        assert result != tmp_path
        assert ".config/tw-odc" in str(result)

    def test_cwd_without_manifest_falls_back(self, tmp_path, monkeypatch):
        """$PWD without manifest.json → fallback to config dir."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = data_dir()
        assert ".config/tw-odc" in str(result)

    def test_cwd_with_corrupt_manifest_falls_back(self, tmp_path, monkeypatch):
        """$PWD with corrupt manifest.json → fallback to config dir."""
        (tmp_path / "manifest.json").write_text("not json")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = data_dir()
        assert result != tmp_path

    def test_creates_config_dir_if_not_exists(self, tmp_path, monkeypatch):
        """Should create config dir when falling back."""
        monkeypatch.chdir(tmp_path)
        config = tmp_path / "custom_config" / "tw-odc"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom_config"))
        monkeypatch.setattr(sys, "platform", "linux")
        result = data_dir()
        assert result == config
        assert config.exists()
```

Run: `uv run pytest tests/test_paths.py::TestDataDir -v`
Expected: FAIL — `data_dir` not defined

- [ ] **Step 4: 實作 `data_dir`**

在 `src/tw_odc/paths.py` 加入：

```python
def data_dir() -> Path:
    """回傳 metadata 存放目錄。

    優先順序：
    1. $PWD 有 manifest.json 且 type == "metadata" → 回傳 $PWD
    2. 否則 → _config_dir()
    """
    cwd = Path.cwd()
    local_manifest = cwd / "manifest.json"
    if local_manifest.is_file():
        try:
            data = json.loads(local_manifest.read_text(encoding="utf-8"))
            if data.get("type") == "metadata":
                return cwd
        except (json.JSONDecodeError, OSError):
            pass

    config = _config_dir()
    config.mkdir(parents=True, exist_ok=True)
    return config
```

Run: `uv run pytest tests/test_paths.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tw_odc/paths.py tests/test_paths.py
git commit -m "feat: add paths.py with data_dir() for cross-platform metadata resolution"
```

---

## Chunk 3: `importlib.resources` 統一、default manifest

### Task 4: 更新 `i18n.py` 使用 `importlib.resources`

**Files:**
- Modify: `src/tw_odc/i18n.py:12`

- [ ] **Step 1: 修改 `i18n.py` 的 locale 路徑載入**

將第 12 行：
```python
i18n.set("load_path", [str(Path(__file__).parent / "locales")])
```
改為：
```python
from importlib.resources import files
i18n.set("load_path", [str(files("tw_odc").joinpath("locales"))])
```

同時移除 `from pathlib import Path` import（`i18n.py` 中僅此處使用 `Path`，移除即可）。

- [ ] **Step 2: 跑 i18n 測試確認不壞**

Run: `uv run pytest tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/tw_odc/i18n.py
git commit -m "refactor: use importlib.resources for locale loading"
```

### Task 5: 建立 `default_manifest.json`

**Files:**
- Create: `src/tw_odc/default_manifest.json`

- [ ] **Step 1: 寫 default manifest 的測試**

```python
# tests/test_paths.py 新增
from importlib.resources import files


class TestDefaultManifest:
    def test_default_manifest_is_valid_json(self):
        """Bundled default_manifest.json should be valid and type=metadata."""
        content = files("tw_odc").joinpath("default_manifest.json").read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["type"] == "metadata"
        assert len(data["datasets"]) == 5

    def test_default_manifest_has_all_exports(self):
        """Should contain export-json, export-csv, export-xml, daily-changed-json, daily-changed-csv."""
        content = files("tw_odc").joinpath("default_manifest.json").read_text(encoding="utf-8")
        data = json.loads(content)
        ids = {d["id"] for d in data["datasets"]}
        assert ids == {"export-json", "export-csv", "export-xml", "daily-changed-json", "daily-changed-csv"}
```

Run: `uv run pytest tests/test_paths.py::TestDefaultManifest -v`
Expected: FAIL — file not found

- [ ] **Step 2: 建立 default_manifest.json**

複製根目錄 `manifest.json` 的內容到 `src/tw_odc/default_manifest.json`（內容完全相同）。

- [ ] **Step 3: 跑測試確認**

Run: `uv run pytest tests/test_paths.py::TestDefaultManifest -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tw_odc/default_manifest.json tests/test_paths.py
git commit -m "feat: add bundled default_manifest.json for bootstrap"
```

---

## Chunk 4: Metadata 子指令 `--dir` 與 bootstrap

### Task 6: 加入 metadata `--dir` 選項

**Files:**
- Modify: `src/tw_odc/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 寫 metadata --dir 的測試**

在 `tests/test_cli.py` 新增：

```python
class TestMetadataDir:
    def test_metadata_list_with_dir(self, tmp_path, monkeypatch):
        """metadata --dir should use specified directory for metadata."""
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()
        manifest = {
            "type": "metadata", "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (meta_dir / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "D",
             "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/d"},
        ]
        (meta_dir / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        # $PWD has NO metadata manifest
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "--dir", str(meta_dir), "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(p["provider"] == "A機關" for p in data)
```

Run: `uv run pytest tests/test_cli.py::TestMetadataDir -v`
Expected: FAIL — metadata has no --dir option

- [ ] **Step 2: 實作 metadata callback 加 --dir**

修改 `src/tw_odc/cli.py`：

在頂部 imports 加入：
```python
from typing import Annotated, Optional
from tw_odc.paths import data_dir
```

加入 metadata callback：
```python
@metadata_app.callback()
def metadata_callback(
    ctx: typer.Context,
    dir: Annotated[Optional[Path], typer.Option("--dir", help="Metadata 目錄路徑")] = None,
) -> None:
    """Metadata subcommand group."""
    ctx.ensure_object(dict)
    ctx.obj["metadata_dir"] = Path(dir) if dir else data_dir()
```

加入 helper：
```python
def _get_metadata_dir(ctx: typer.Context) -> Path:
    return ctx.obj["metadata_dir"]
```

- [ ] **Step 3: 更新所有 metadata 指令使用 `_get_metadata_dir`**

修改以下指令，將 `cwd = Path.cwd()` 替換為 `metadata_dir = _get_metadata_dir(ctx)`：

**`metadata_download`**：加 `ctx: typer.Context` 參數，用 `metadata_dir` 取代 `cwd`
**`metadata_list`**：同上
**`metadata_create`**：加 `ctx`，從 `metadata_dir` 讀取 export-json，但 `create_dataset_manifest` 仍用 `Path.cwd()` 作為 `base_dir`
**`metadata_update`**：加 `ctx`，從 `metadata_dir` 讀取 export-json，但 provider 目錄用 `Path.cwd()` 解析。注意：此指令已有自己的 `--dir` 參數（用於指定 provider 目錄），需改名或調整避免衝突。將 provider 的 `--dir` 參數改為 `--provider-dir`。
**`metadata_apply_daily`**：加 `ctx`，用 `metadata_dir` 讀取 daily-changed-json.json，但 `find_existing_providers` 仍用 `Path.cwd()`

- [ ] **Step 4: 修正 metadata_update 的 --dir 衝突**

`metadata_update` 已有 `--dir` 選項（指 provider 目錄）。現在 metadata callback 也有 `--dir`。解法：metadata_update 的 `--dir` 改名為 `--provider-dir`。

更新 `metadata_update` 的簽名：
```python
@metadata_app.command("update")
def metadata_update(
    ctx: typer.Context,
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider name"),
    provider_dir: str | None = typer.Option(None, "--provider-dir", help="Target provider directory"),
) -> None:
```

同步更新對應測試（如有）。

- [ ] **Step 5: 跑全部測試確認**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py
git commit -m "feat: add --dir option to metadata subcommands, use data_dir() fallback"
```

### Task 7: Bootstrap — 首次使用自動複製 manifest

**Files:**
- Modify: `src/tw_odc/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 寫 bootstrap 測試**

```python
class TestMetadataBootstrap:
    def test_download_creates_manifest_from_default(self, tmp_path, monkeypatch):
        """When metadata_dir has no manifest.json, bootstrap from default."""
        # Use empty dir as metadata_dir (no manifest.json)
        meta_dir = tmp_path / "config" / "tw-odc"
        meta_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        # Mock fetch_all as a no-op to avoid actual downloads
        import tw_odc.fetcher
        monkeypatch.setattr(tw_odc.fetcher, "fetch_all", lambda *a, **kw: None)
        # Mock asyncio.run to just call the coroutine (fetch_all is now sync no-op)
        monkeypatch.setattr("tw_odc.cli.asyncio.run", lambda coro: None)

        result = runner.invoke(app, ["metadata", "--dir", str(meta_dir), "download"])
        assert result.exit_code == 0
        # manifest.json should now exist in meta_dir
        assert (meta_dir / "manifest.json").exists()
        data = json.loads((meta_dir / "manifest.json").read_text())
        assert data["type"] == "metadata"
```

Run: `uv run pytest tests/test_cli.py::TestMetadataBootstrap -v`
Expected: FAIL

- [ ] **Step 2: 實作 bootstrap 邏輯**

在 `src/tw_odc/cli.py` 的 `metadata_download` 開頭加入：

```python
from tw_odc.paths import ensure_manifest

metadata_dir = _get_metadata_dir(ctx)
ensure_manifest(metadata_dir)
manifest = _load_and_check(metadata_dir, ManifestType.METADATA)
```

在 `src/tw_odc/paths.py` 新增：

```python
def ensure_manifest(metadata_dir: Path) -> None:
    """若 metadata_dir 內無 manifest.json，從 package 內建的 default 複製一份。"""
    manifest_path = metadata_dir / "manifest.json"
    if manifest_path.exists():
        return
    from importlib.resources import files
    default = files("tw_odc").joinpath("default_manifest.json").read_text(encoding="utf-8")
    metadata_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(default, encoding="utf-8")
```

- [ ] **Step 3: 跑測試確認**

Run: `uv run pytest tests/test_cli.py::TestMetadataBootstrap -v`
Expected: PASS

- [ ] **Step 4: 寫 ensure_manifest 的單元測試**

在 `tests/test_paths.py` 新增：

```python
from tw_odc.paths import ensure_manifest


class TestEnsureManifest:
    def test_copies_default_when_missing(self, tmp_path):
        """Should copy default manifest when manifest.json is absent."""
        target = tmp_path / "config"
        target.mkdir()
        ensure_manifest(target)
        assert (target / "manifest.json").exists()
        data = json.loads((target / "manifest.json").read_text())
        assert data["type"] == "metadata"

    def test_noop_when_exists(self, tmp_path):
        """Should not overwrite existing manifest.json."""
        existing = {"type": "metadata", "provider": "custom", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(existing))
        ensure_manifest(tmp_path)
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert data["provider"] == "custom"

    def test_creates_parent_dirs(self, tmp_path):
        """Should create parent directories if they don't exist."""
        target = tmp_path / "a" / "b" / "c"
        ensure_manifest(target)
        assert (target / "manifest.json").exists()
```

Run: `uv run pytest tests/test_paths.py::TestEnsureManifest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tw_odc/paths.py src/tw_odc/cli.py tests/test_paths.py tests/test_cli.py
git commit -m "feat: bootstrap default manifest on first metadata download"
```

---

## Chunk 5: URL HEAD 預檢

### Task 8: 加入 URL HEAD 健康檢查

**Files:**
- Modify: `src/tw_odc/fetcher.py`
- Modify: `tests/test_fetcher.py`

- [ ] **Step 1: 寫 `check_url_health` 的測試**

在 `tests/test_fetcher.py` 新增：

```python
import pytest
from tw_odc.fetcher import check_url_health


class TestCheckUrlHealth:
    @pytest.mark.asyncio
    async def test_healthy_url_returns_true(self, aiohttp_server_or_mock):
        """HTTP 200 → (True, None)."""
        # Use aiohttp test server or mock
        ok, reason = await check_url_health("https://httpbin.org/status/200", timeout=5)
        # For unit test, mock aiohttp.ClientSession
        assert ok is True

    @pytest.mark.asyncio
    async def test_404_returns_false(self):
        """HTTP 404 → (False, 'HTTP 404')."""
        ok, reason = await check_url_health("https://httpbin.org/status/404", timeout=5)
        assert ok is False
        assert "404" in reason
```

由於網路測試不穩定，改用 mock 方式：

```python
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

class TestCheckUrlHealth:
    @pytest.mark.asyncio
    async def test_2xx_is_healthy(self):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.head.return_value = mock_resp

        ok, reason = await check_url_health("https://example.com/data", session=mock_session, timeout=10)
        assert ok is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_3xx_is_healthy(self):
        mock_resp = AsyncMock()
        mock_resp.status = 301
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.head.return_value = mock_resp

        ok, reason = await check_url_health("https://example.com/data", session=mock_session, timeout=10)
        assert ok is True

    @pytest.mark.asyncio
    async def test_4xx_is_unhealthy(self):
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.head.return_value = mock_resp

        ok, reason = await check_url_health("https://example.com/missing", session=mock_session, timeout=10)
        assert ok is False
        assert "404" in reason

    @pytest.mark.asyncio
    async def test_timeout_is_unhealthy(self):
        mock_session = AsyncMock()
        mock_session.head.side_effect = asyncio.TimeoutError()

        ok, reason = await check_url_health("https://example.com/slow", session=mock_session, timeout=10)
        assert ok is False
        assert "timeout" in reason.lower()

    @pytest.mark.asyncio
    async def test_connection_error_is_unhealthy(self):
        """DNS failure / connection refused → unhealthy."""
        import aiohttp
        mock_session = AsyncMock()
        mock_session.head.side_effect = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError("DNS resolution failed"))

        ok, reason = await check_url_health("https://nonexistent.example.com", session=mock_session, timeout=10)
        assert ok is False
        assert reason is not None
```

Run: `uv run pytest tests/test_fetcher.py::TestCheckUrlHealth -v`
Expected: FAIL — function does not exist

- [ ] **Step 2: 實作 `check_url_health`**

在 `src/tw_odc/fetcher.py` 新增：

```python
async def check_url_health(
    url: str,
    session: aiohttp.ClientSession | None = None,
    timeout: int = 10,
) -> tuple[bool, str | None]:
    """HEAD check on a URL. Returns (is_healthy, reason_if_not).

    Healthy: 2xx or 3xx.
    Unhealthy: 4xx, 5xx, timeout, connection error.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False) as resp:
            if resp.status < 400:
                return True, None
            return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, "Timeout"
    except aiohttp.ClientError as e:
        return False, str(e)
    finally:
        if close_session:
            await session.close()
```

Run: `uv run pytest tests/test_fetcher.py::TestCheckUrlHealth -v`
Expected: PASS

- [ ] **Step 3: 整合到 `fetch_all` — 下載前 HEAD 預檢**

在 `fetch_all` 裡，下載迴圈前加入預檢。使用單一 session 避免為每個 URL 建立新連線：

```python
# Inside fetch_all, after building the downloads list and after the `only` filter:
unhealthy: list[tuple[str, str]] = []
async with aiohttp.ClientSession() as check_session:
    for url, dest in downloads:
        ok, reason = await check_url_health(url, session=check_session)
        if not ok:
            print(f"W003: {t('W003', url=url, reason=reason)}", file=sys.stderr)
            unhealthy.append((url, reason))

# Filter out unhealthy URLs
if unhealthy:
    unhealthy_urls = {u for u, _ in unhealthy}
    downloads = [(url, dest) for url, dest in downloads if url not in unhealthy_urls]
```

注意：預檢要用已解析的 URL（template 已替換後的），且在 `only` filter 之後執行。

同時在 locale 檔案（`src/tw_odc/locales/en.json` 和 `src/tw_odc/locales/zh-TW.json`）新增 `W003` 翻譯：

- en: `"W003": "URL unreachable: {url} — {reason}"`
- zh-TW: `"W003": "URL 無法連線：{url} — {reason}"`

- [ ] **Step 4: 跑全部測試確認無 regression**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "feat: add URL HEAD health check before downloading"
```

---

## Chunk 6: `_load_export_json_lookup` 更新、`config show` 子指令

### Task 9: 更新 `_load_export_json_lookup` 使用 `data_dir()`

**Files:**
- Modify: `src/tw_odc/cli.py:360-382`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 寫測試 — metadata 在 config dir 時 gov-tw scoring 仍能找到 export-json**

```python
class TestLoadExportJsonWithDataDir:
    def test_gov_tw_score_uses_data_dir(self, tmp_path, monkeypatch):
        """gov-tw scoring should find export-json.json via data_dir()."""
        # Metadata in a separate config dir
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        root_manifest = {
            "type": "metadata", "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (config_dir / "manifest.json").write_text(json.dumps(root_manifest))
        export_data = [
            {"資料集識別碼": "1001", "資料集名稱": "D", "提供機關": "T",
             "檔案格式": "CSV", "資料下載網址": "http://x",
             "編碼格式": "UTF-8", "主要欄位說明": "a、b",
             "更新頻率": "每1月", "詮釋資料更新時間": "2026-03-10 00:00:00.000000"},
        ]
        (config_dir / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))

        # Provider in $PWD
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        pkg_dir = work_dir / "t"
        pkg_dir.mkdir()
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001.csv").write_text("a,b\n1,2\n")

        monkeypatch.chdir(work_dir)
        # Patch data_dir to return config_dir
        monkeypatch.setattr("tw_odc.cli.data_dir", lambda: config_dir)

        result = runner.invoke(app, ["dataset", "--dir", "t", "score", "--method", "gov-tw"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["method"] == "gov-tw"
```

Run: `uv run pytest tests/test_cli.py::TestLoadExportJsonWithDataDir -v`
Expected: FAIL

- [ ] **Step 2: 重寫 `_load_export_json_lookup`**

```python
def _load_export_json_lookup() -> dict[str, dict]:
    """Load export-json.json from metadata dir and build a lookup by dataset ID.

    Returns empty dict if file not found (graceful degradation).
    """
    from tw_odc.paths import data_dir

    metadata_dir = data_dir()
    manifest_path = metadata_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"W001: {t('W001')}", file=sys.stderr)
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"W001: {t('W001')}", file=sys.stderr)
        return {}

    # Find export-json entry
    export_path = None
    for ds in manifest.get("datasets", []):
        if ds["id"] == "export-json":
            export_path = metadata_dir / f"{ds['id']}.{ds['format']}"
            break

    if export_path is None or not export_path.exists():
        print(f"W002: {t('W002')}", file=sys.stderr)
        return {}

    data = json.loads(export_path.read_text(encoding="utf-8"))
    return {str(d["資料集識別碼"]): d for d in data}
```

- [ ] **Step 3: 跑測試確認**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py
git commit -m "refactor: _load_export_json_lookup uses data_dir() instead of parent-walking"
```

### Task 10: 加入 `config show` 子指令

**Files:**
- Modify: `src/tw_odc/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: 寫 config show 測試**

```python
class TestConfigShow:
    def test_config_show_json_output(self, tmp_path, monkeypatch):
        """config show outputs JSON with version, metadata_dir, cwd, local_metadata."""
        manifest = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data
        assert data["metadata_dir"] == str(tmp_path)
        assert data["cwd"] == str(tmp_path)
        assert data["local_metadata"] is True

    def test_config_show_no_local_metadata(self, tmp_path, monkeypatch):
        """When no local metadata manifest, local_metadata should be False."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["local_metadata"] is False

    def test_config_show_version_field(self, tmp_path, monkeypatch):
        """Version should be a string (either semver or 'dev')."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "show"])
        data = json.loads(result.output)
        assert isinstance(data["version"], str)
```

Run: `uv run pytest tests/test_cli.py::TestConfigShow -v`
Expected: FAIL — no config subcommand

- [ ] **Step 2: 實作 config show**

在 `src/tw_odc/cli.py` 加入：

```python
config_app = typer.Typer(help="Configuration info")
app.add_typer(config_app, name="config")


def _get_version() -> str:
    """Get installed package version, or 'dev' if running from source."""
    try:
        from importlib.metadata import version
        return version("tw-odc")
    except Exception:
        return "dev"


def _has_local_metadata() -> bool:
    """Check if $PWD has a valid metadata manifest."""
    manifest_path = Path.cwd() / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("type") == "metadata"
    except (json.JSONDecodeError, OSError):
        return False


@config_app.command("show")
def config_show() -> None:
    """Show configuration and path info."""
    result = {
        "version": _get_version(),
        "metadata_dir": str(data_dir()),
        "cwd": str(Path.cwd()),
        "local_metadata": _has_local_metadata(),
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
```

- [ ] **Step 3: 跑測試確認**

Run: `uv run pytest tests/test_cli.py::TestConfigShow -v`
Expected: PASS

- [ ] **Step 4: 跑全部測試確認無 regression**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py
git commit -m "feat: add 'config show' subcommand for diagnostic info"
```

---

## Chunk 7: Build 驗證與收尾

### Task 11: 驗證 `uv build` 產出正確

**Files:**
- No code changes (validation only)

- [ ] **Step 1: 執行 build**

Run: `uv build`
Expected: 產出 `dist/tw_odc-0.1.0.tar.gz` 和 `dist/tw_odc-0.1.0-py3-none-any.whl`

- [ ] **Step 2: 檢查 wheel 內容**

```bash
python -m zipfile -l dist/tw_odc-0.1.0-py3-none-any.whl
```

Expected:
- 包含 `tw_odc/*.py`、`tw_odc/locales/*.json`、`tw_odc/default_manifest.json`
- **不包含** provider 資料夾、`tests/`、`docs/`

- [ ] **Step 3: 驗證 build 不含 uv-specific sources**

Run: `uv build --no-sources`
Expected: 成功，確保無 path dependency 問題

- [ ] **Step 4: Smoke test — 從 wheel 安裝並執行**

```bash
uv run --isolated --no-project --with dist/tw_odc-0.1.0-py3-none-any.whl tw-odc config show
```

Expected: 輸出 JSON 包含 `"version": "0.1.0"`

- [ ] **Step 5: 跑全部測試最終確認**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Commit（如有任何修正）**

```bash
git add -A
git commit -m "build: verify package build output"
```

### Task 12:（可選）發布到 TestPyPI 驗證

- [ ] **Step 1: 發布到 TestPyPI**

```bash
uv publish --publish-url https://test.pypi.org/legacy/
```

- [ ] **Step 2: 從 TestPyPI 安裝驗證**

```bash
uv run --isolated --no-project --index-url https://test.pypi.org/simple/ --with tw-odc tw-odc config show
```

- [ ] **Step 3: 確認無問題後發布到 PyPI**

```bash
uv publish
```
