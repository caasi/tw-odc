# tw-odc i18n 設計

## 目標

為 tw-odc CLI 加入多語系支援，初期支援 `en`（預設）和 `zh-TW`。

## 決策摘要

| 項目 | 決定 |
|------|------|
| 框架 | `i18nice`（python-i18n 活躍 fork） |
| 翻譯檔格式 | JSON |
| 語言偵測順序 | `--lang` flag > `LANG`/`LC_ALL` 環境變數 > default `en` |
| Help text / docstring | 不翻譯，統一英文 |
| Runtime 訊息 | 翻譯（錯誤、進度、狀態、輸出格式化） |
| JSON 結構性 key / issue type | 不翻譯 |
| 錯誤編號 | 加，格式 `E0xx`/`E1xx`/`E2xx` |

## 翻譯涵蓋範圍

### 要翻譯

- 錯誤訊息（`cli.py` ~10 條、`fetcher.py` ~5 條）
- 進度/狀態文字（`未變更`、`已封鎖`、`SSL 驗證跳過` 等）
- 輸出格式化字串（`筆`、`部分`）
- fetcher stderr 摘要（`⚠ N 個問題已記錄到...`）

### 不翻譯

- `typer.Option(help=...)` 和 command docstring → 改寫為英文
- JSON output 的 key（`id`, `issue`, `detail`）
- Issue type 值（`rate_limited`, `ssl_error`, `network_error`）

## 錯誤編號

格式：`EXXX`，顯示為 `E001: message`。

分類：

- `E001–E099`：manifest / 設定錯誤
  - `E001`：manifest type 不符
  - `E002`：找不到 export-json 資料集
  - `E003`：檔案不存在（需先 download）
  - `E004`：找不到指定機關
  - `E005`：需指定 --provider 或 --dir
  - `E006`：找不到指定 ID 的資料集
- `E101–E199`：網路 / 下載錯誤
  - `E101`：HTTP 429 rate limited
  - `E102`：HTTP 非 200 錯誤
  - `E103`：SSL 錯誤
  - `E104`：網路錯誤
  - `E105`：非預期錯誤
  - `E106`：找不到指定下載檔案
- `E201–E299`：檢查 / 評分錯誤（預留）

## 架構

### 檔案結構

```
tw_odc/
├── i18n.py                    # locale 偵測、翻譯函數 t() 初始化
└── locales/
    ├── en.json                # 英文翻譯（預設）
    └── zh-TW.json             # 繁體中文翻譯
```

### `i18n.py` 職責

```python
import i18n

def setup_locale(lang: str | None = None) -> None:
    """初始化 locale。lang flag > LANG env > default en。"""
    ...

def t(key: str, **kwargs) -> str:
    """翻譯函數，包裝 i18n.t()。"""
    return i18n.t(key, **kwargs)
```

### 翻譯檔範例

`locales/en.json`:
```json
{
  "E001": "Expected manifest type '%{expected}', got '%{actual}'",
  "E004": "Provider not found: '%{provider}'",
  "E006": "Dataset not found: ID %{id}",
  "E106": "File not found: %{name}\nAvailable files: %{available}",
  "status.not_modified": "%{filename} (not modified)",
  "status.downloaded": "%{filename} (%{size} bytes)",
  "status.rate_limited": "%{filename}: HTTP 429 — blocked all requests for %{domain}",
  "status.skipped": "%{filename} (skipped, %{domain} blocked by 429)",
  "status.ssl_retry": "%{filename}: SSL error, retrying without verification",
  "status.ssl_skipped": "%{filename} (%{size} bytes) (SSL verification skipped)",
  "summary.issues": "%{count} issue(s) recorded to %{path}",
  "output.count_suffix": "(%{count} datasets)",
  "output.partial": "(partial)"
}
```

`locales/zh-TW.json`:
```json
{
  "E001": "預期 manifest type 為 '%{expected}'，實際為 '%{actual}'",
  "E004": "找不到機關「%{provider}」",
  "E006": "找不到 ID 為 %{id} 的資料集",
  "E106": "找不到檔案: %{name}\n可用的檔案: %{available}",
  "status.not_modified": "%{filename} (未變更)",
  "status.downloaded": "%{filename} (%{size} bytes)",
  "status.rate_limited": "%{filename}: HTTP 429 — 已封鎖 %{domain} 的所有請求",
  "status.skipped": "%{filename} (跳過, %{domain} 已被 429 封鎖)",
  "status.ssl_retry": "%{filename}: SSL 錯誤，嘗試跳過驗證重試",
  "status.ssl_skipped": "%{filename} (%{size} bytes) (SSL 驗證跳過)",
  "summary.issues": "⚠ %{count} 個問題已記錄到 %{path}",
  "output.count_suffix": "(%{count} 筆)",
  "output.partial": "(部分)"
}
```

### 語言切換機制

1. 在 `app` 的 callback 加 `--lang` option
2. `setup_locale()` 在 CLI 進入點最早呼叫
3. Locale 偵測邏輯：
   - `--lang` 有值 → 使用該值
   - 否則讀 `LANG` / `LC_ALL`，偵測 `zh_TW` → `zh-TW`
   - 都沒有 → `en`

### 使用方式（改動前後對比）

Before:
```python
print(f"錯誤: 找不到機關「{provider}」", file=sys.stderr)
```

After:
```python
print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)
```

## 對既有程式碼的影響

1. **`cli.py`**：所有 help text / docstring 改英文；錯誤訊息改用 `t()` + 錯誤編號
2. **`fetcher.py`**：進度/狀態訊息改用 `t()`
3. **`pyproject.toml`**：加 `i18nice` 依賴
4. **新增 `tw_odc/i18n.py`**：locale 偵測與 `t()` wrapper
5. **新增 `tw_odc/locales/`**：`en.json` + `zh-TW.json`
6. **測試**：新增 `tests/test_i18n.py`，既有測試可能需調整錯誤訊息比對
