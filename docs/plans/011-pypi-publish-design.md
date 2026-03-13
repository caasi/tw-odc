# 011 — 發布 tw-odc 到 PyPI

## 目標

將 tw-odc 發布為 PyPI 套件，讓使用者可透過 `pip install tw-odc` 或 `uv tool install tw-odc` 安裝，無需 clone repo 即可使用完整 CLI 功能。

## 需求

1. **src layout 遷移** — `tw_odc/` 搬到 `src/tw_odc/`
2. **Provider 資料夾不打包** — build 產出不包含任何 provider 目錄
3. **Metadata 路徑策略** — `$PWD` 有合法 metadata manifest 就用，否則 fallback 到 OS 使用者設定目錄
4. **跨平台路徑** — 用 `platformdirs` 處理 Linux / macOS / Windows 差異
5. **手動發布** — `uv build && uv publish`，暫不設 CI/CD

## 設計

### 1. 目錄結構

```
tw-odc/
├── src/
│   └── tw_odc/
│       ├── __init__.py          # FORMAT_ALIASES
│       ├── __main__.py
│       ├── cli.py
│       ├── fetcher.py
│       ├── inspector.py
│       ├── scorer.py
│       ├── gov_tw_scorer.py
│       ├── manifest.py
│       ├── i18n.py
│       ├── paths.py             # 新增 — data_dir() 路徑解析
│       ├── default_manifest.json # 新增 — 預設 root manifest（隨 package 打包）
│       └── locales/
│           ├── en.json
│           └── zh-TW.json
├── tests/                       # 不動，留在根目錄
├── docs/                        # 不動
├── manifest.json                # 不動（開發用，gitignore 不管它）
├── pyproject.toml
└── ...provider dirs...          # 不打包
```

`tw_odc/` 整個搬進 `src/tw_odc/`。所有 `from tw_odc.xxx` import 路徑不變。

### 2. `paths.py` — 路徑解析

新增 `src/tw_odc/paths.py`：

```python
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
        # Linux 和 macOS 都走 XDG
        from platformdirs.unix import Unix
        return Path(Unix(APP_NAME).user_config_dir)


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

**macOS 路徑策略**：`platformdirs` 預設在 macOS 回傳 `~/Library/Application Support/`，但我們的需求是 macOS 也走 `~/.config/`。做法是直接使用 `platformdirs.unix.Unix` 類別（強制 XDG 邏輯），只有 Windows 才用 `platformdirs.windows.Windows`。這是 platformdirs 官方支援的用法，不是 hack。

### 3. `pyproject.toml` 改動

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

重點：
- build-backend 改為 `uv_build`
- 新增 `platformdirs>=4.0` 依賴
- 刪除 `[tool.setuptools.*]` 區段
- `pythonpath` 改為 `["src"]`
- `default_manifest.json` 和 `locales/*.json` 作為 package data 打包（uv_build 自動處理 src layout 下的非 .py 檔案）

### 4. Metadata 子指令 `--dir` 選項

`metadata` callback 加上 `--dir` 選項：

```python
@metadata_app.callback()
def metadata_callback(
    ctx: typer.Context,
    dir: Annotated[Optional[Path], typer.Option("--dir", help="Metadata 目錄路徑")] = None,
):
    ctx.obj = ctx.obj or {}
    ctx.obj["metadata_dir"] = dir or data_dir()
```

所有 metadata 指令從 `ctx.obj["metadata_dir"]` 取路徑，不再硬寫 `Path(".")` 或 `Path.cwd()`。

### 5. `config show` 子指令

新增 `config` 子指令群，唯讀：

```
tw-odc config show
```

輸出 JSON：

```json
{
  "version": "0.1.0",
  "metadata_dir": "/home/user/.config/tw-odc",
  "cwd": "/home/user/projects/my-data",
  "local_metadata": false
}
```

- `version` — 已安裝的 tw-odc 版本（從 `importlib.metadata` 取得）
- `metadata_dir` — `data_dir()` 的結果
- `cwd` — 當前工作目錄
- `local_metadata` — `$PWD` 是否有合法的 metadata manifest（type == "metadata"）

### 6. 初次使用 Bootstrap

`src/tw_odc/default_manifest.json` 內嵌一份預設的 root manifest（type: metadata，5 個 data.gov.tw export URL）。讀取時使用 `importlib.resources.files("tw_odc")` 存取 package 內建檔案，避免 `__file__` 相對路徑在 zip import 或 editable install 下出問題。

`metadata download` 流程：

1. 解析 `metadata_dir`（`--dir` > `data_dir()` fallback）
2. 檢查 `metadata_dir/manifest.json` 是否存在
3. 不存在 → 從 package 內建的 `default_manifest.json` 複製一份到 `metadata_dir/manifest.json`
4. 讀取 manifest，正常下載（既有 ETag / fetch 邏輯不變）

### 7. URL 健康檢查

每次 `metadata download` 執行時，在實際下載前對每個 URL 發 HTTP HEAD 請求驗證可達性：

- **有效**：HTTP 2xx 或 3xx → 正常進入下載流程
- **無效**：HTTP 4xx / 5xx / 連線逾時 / DNS 失敗 → 印 warning 到 stderr（格式：`W0xx: {url} — {reason}`），跳過該項，不中斷整體流程
- **與 ETag 的關係**：HEAD check 僅做可達性預檢，不取代既有的 conditional GET（If-None-Match）邏輯。如果 HEAD 通過但後續 GET 回 304，正常處理
- **逾時**：HEAD 請求逾時設 10 秒，避免卡住整個流程

### 8. Provider / Dataset 指令

不受影響。繼續在 `$PWD` 操作，`--dir` 指定 provider 目錄。

**注意 `metadata create` 的行為**：`metadata create --provider "xxx"` 是 metadata 子指令，但它建立 provider 目錄。當 metadata 在 `~/.config/tw-odc/` 時，provider 目錄仍然建在 `$PWD`（不是 `~/.config/tw-odc/` 下）。`metadata create` 從 `metadata_dir` 讀取 `export-json.json`，但 provider 目錄輸出到 `$PWD`。

同理，`metadata apply-daily` 呼叫 `find_existing_providers()` 時搜尋 `$PWD` 下的 provider 目錄（不是 `metadata_dir`）。`metadata_dir` 只負責 metadata 檔案（manifest.json, export-json.json, daily-changed-*.json 等），provider 操作永遠在 `$PWD`。

### 9. `_load_export_json_lookup` 更新

現有的 `_load_export_json_lookup()` 用 parent-walking 尋找 `export-json.json`。改為使用 `data_dir()` 取得 metadata 目錄，從中讀取 `export-json.json`。不再需要 parent-walking 邏輯。

### 10. 統一使用 `importlib.resources` 存取 package data

所有需要讀取 package 內建檔案的地方統一使用 `importlib.resources.files("tw_odc")`，不再用 `Path(__file__).parent` 相對路徑。需更新的模組：

- **`paths.py`**（新增）：讀取 `default_manifest.json`
- **`i18n.py`**（既有）：載入 `locales/*.json`，目前用 `Path(__file__).parent / "locales"`，改為 `importlib.resources.files("tw_odc") / "locales"`

這確保 zip import、editable install、標準 pip install 下都能正確存取 package data。

### 11. `config show` version fallback

版本資訊透過 `importlib.metadata.version("tw-odc")` 取得。開發模式下（從 source 直接跑、未安裝）可能拋 `PackageNotFoundError`，fallback 策略：

1. 嘗試 `importlib.metadata.version("tw-odc")`
2. 失敗 → 回傳 `"dev"`

## 不做的事

- CI/CD publish workflow（以後再加）
- `config set` 等寫入型設定指令
- Package 拆分（CLI + core library）
- 版本自動化（手動 `uv version --bump`）

## 新增依賴

| 套件 | 用途 |
|------|------|
| `platformdirs>=4.0` | 跨平台使用者設定目錄 |

## 風險

- **macOS 路徑**：已解決。使用 `platformdirs.unix.Unix` 類別強制 XDG 路徑，macOS 和 Linux 統一走 `~/.config/tw-odc/`。
- **`python-magic` 在 Windows**：依賴 libmagic，Windows 上安裝可能需要額外步驟。這是既有問題，不在本次範圍，但發布後會更容易被觸發。
- **`uv_build` 版本**：使用 `>=0.10.9,<0.11.0` pin。若使用者的 uv 版本與此不符可能有問題，但這是目前 uv 生態的標準做法。
