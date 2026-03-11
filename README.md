# ROC Open Data Checker

自動化稽核政府開放資料平台，以 Tim Berners-Lee 的五星開放資料模型評估資料集品質。

從[政府資料開放平臺](https://data.gov.tw/)開始，爬蟲收集資料集清單，再以確定性規則檢查格式、驗證連結、偵測常見問題（如 PDF、試算表當資料庫、下載失敗等）。評分結果以檔案形式儲存，讓資料品質可以被大規模量測。

LLM 只用於溝通，不用於評估——規則分析找出問題後，LLM 協助撰寫禮貌的改善建議信，由人工審核後寄出。

## 使用方式

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.13+。

```bash
# 安裝依賴
uv sync
```

### 1. 下載 data.gov.tw 匯出檔

```bash
tw-odc metadata download
tw-odc metadata download --only export-json.json   # 只下載一個檔案
tw-odc metadata download --no-cache                 # 忽略 ETag 快取
```

下載 JSON、CSV、XML 三份匯出檔到專案根目錄。

### 1b. 下載每日異動資料集

```bash
# 下載今天的異動清單
tw-odc metadata download --only daily-changed-json.json

# 指定日期
tw-odc metadata download --only daily-changed-json.json --date 2026-03-10

# 套用到已存在的 provider manifests
tw-odc metadata apply-daily
tw-odc metadata apply-daily --date 2026-03-10
```

`apply-daily` 讀取 `daily-changed-json.json`，將異動資料集合併進已存在的 provider manifest，輸出 JSON 摘要（updated / skipped / warnings）。

### 2. 查詢機關與建立 provider

```bash
# 列出所有提供機關（JSON 輸出）
tw-odc metadata list

# 人類可讀格式
tw-odc metadata list --format text

# 從 metadata 建立指定機關的 dataset manifest
tw-odc metadata create --provider "交通部中央氣象署"

# 更新既有的 dataset manifest
tw-odc metadata update --provider "交通部中央氣象署"
tw-odc metadata update --dir cwa_gov_tw
```

### 3. 下載與檢查 dataset

```bash
# 下載 provider 的所有資料集
tw-odc dataset --dir cwa_gov_tw download

# 只下載特定 ID
tw-odc dataset --dir cwa_gov_tw download --id 12345

# 列出 dataset manifest 中的資料集
tw-odc dataset --dir cwa_gov_tw list

# 檢查已下載的資料集
tw-odc dataset --dir cwa_gov_tw check

# 五星評分
tw-odc dataset --dir cwa_gov_tw score

# 清除下載的檔案
tw-odc dataset --dir cwa_gov_tw clean
```

所有指令也可以用 `uv run python -m tw_odc` 取代 `tw-odc`。

### 4. 測試

```bash
uv run pytest -v
```

## 架構

統一的 CLI 工具 `tw-odc`，支援兩種 manifest 類型：`metadata`（根目錄，管理匯出檔）和 `dataset`（provider 資料夾，管理資料集）。

```
tw-odc/
├── manifest.json              # type: metadata（data.gov.tw 匯出 URL）
├── tw_odc/                    # CLI 套件
│   ├── cli.py                 # typer app，metadata/dataset 子命令
│   ├── fetcher.py             # 非同期下載（aiohttp, etag 快取）
│   ├── inspector.py           # 檔案格式檢查
│   ├── scorer.py              # 五星評分
│   └── manifest.py            # manifest 讀寫、RFC 6902 patch
├── <provider_slug>/           # 每個提供機關一個資料夾
│   ├── manifest.json          # type: dataset（committed）
│   ├── patch.json             # RFC 6902 patch（可選，committed）
│   └── datasets/              # 下載的檔案（gitignored）
└── tests/
```

### manifest.json 格式

**Metadata**（根目錄）：
```json
{
  "type": "metadata",
  "provider": "data.gov.tw",
  "datasets": [
    { "id": "export-json", "name": "全站資料集匯出 JSON", "format": "json", "urls": ["..."] },
    {
      "id": "daily-changed-json", "name": "每日異動資料集 JSON", "format": "json",
      "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
      "params": { "date": "today" }
    }
  ]
}
```

**Dataset**（provider 資料夾）：
```json
{
  "type": "dataset",
  "provider": "財政部",
  "slug": "mof_gov_tw",
  "datasets": [
    { "id": "21001", "name": "綜合所得稅申報核定統計專冊", "format": "csv", "urls": ["..."] }
  ]
}
```

## 專案狀態

開發中。已完成 CLI 重構（`tw-odc`）、manifest-based 架構、格式檢查（inspector）、五星評分（scorer）、每日異動資料集下載（`params` URL 模板）與增量更新（`apply-daily`）。下一步是 report 產出與改善建議信草稿。詳見 `docs/plans/`。
