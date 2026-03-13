# ROC Open Data Checker

自動化稽核政府開放資料平台，以 Tim Berners-Lee 的五星開放資料模型評估資料集品質。

從[政府資料開放平臺](https://data.gov.tw/)開始，爬蟲收集資料集清單，再以確定性規則檢查格式、驗證連結、偵測常見問題（如 PDF、試算表當資料庫、下載失敗等）。評分結果以結構化 JSON 輸出，讓資料品質可以被大規模量測。

tw-odc 本身不包含 LLM 程式碼。所有評估皆為確定性、基於規則的分析。CLI 輸出結構化 JSON（評分、問題、資料集 metadata），供任何 LLM agent 或人工流程消費——產出報告、草擬改善建議信、建立儀表板。這個分離讓稽核管線可重現，同時保持下游使用的彈性。

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

### 3. 下載、檢查與評分 dataset

```bash
# 下載 provider 的所有資料集
tw-odc dataset --dir cwa_gov_tw download

# 只下載特定 ID
tw-odc dataset --dir cwa_gov_tw download --id 12345

# 忽略 ETag 快取
tw-odc dataset --dir cwa_gov_tw download --no-cache

# 列出 dataset manifest 中的資料集
tw-odc dataset --dir cwa_gov_tw list

# 檢查已下載的資料集
tw-odc dataset --dir cwa_gov_tw check

# 五星評分（預設）
tw-odc dataset --dir cwa_gov_tw score

# 政府資料品質指標評分
tw-odc dataset --dir cwa_gov_tw score --method gov-tw

# 查看原始資料內容（搭配 grep/jq/head 使用）
tw-odc dataset --dir cwa_gov_tw view --id 12345
tw-odc dataset --dir cwa_gov_tw view --id 12345 | jq '.'

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
│   ├── __init__.py            # FORMAT_ALIASES（中文格式名對照）
│   ├── __main__.py            # python -m tw_odc 進入點
│   ├── cli.py                 # typer app，metadata/dataset 子命令
│   ├── fetcher.py             # 非同期下載（aiohttp, etag 快取）
│   ├── inspector.py           # 檔案格式偵測與驗證
│   ├── scorer.py              # 五星評分引擎
│   ├── gov_tw_scorer.py       # 政府資料品質指標評分
│   ├── manifest.py            # manifest 讀寫、RFC 6902 patch、scaffolding
│   ├── i18n.py                # 語系偵測與翻譯
│   └── locales/               # en.json, zh-TW.json
├── <provider_slug>/           # 每個提供機關一個資料夾
│   ├── manifest.json          # type: dataset（committed）
│   ├── patch.json             # RFC 6902 patch（可選，committed）
│   └── datasets/              # 下載的檔案（gitignored）
└── tests/
    ├── test_cli.py
    ├── test_fetcher.py
    ├── test_i18n.py
    ├── test_inspector.py
    ├── test_manifest.py
    ├── test_scorer.py
    └── test_gov_tw_scorer.py
```

### 評分方法

支援兩種獨立的評分方法，透過 `--method` 選擇：

- **5-stars**（預設）：Tim Berners-Lee 五星開放資料模型
  - ★ 資料上線（任意格式）
  - ★★ 機器可讀（結構化格式）
  - ★★★ 開放格式（非專有格式）
  - ★★★★ RDF/URI（規劃中）
  - ★★★★★ Linked Data（規劃中）
- **gov-tw**：數位發展部「政府資料品質提升機制運作指引」6 項品質指標

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

### Pipeline

完整稽核流程：`metadata download → manifest scaffolding → dataset download → check → score → JSON output`

增量更新：`metadata download --only daily-changed-json.json → metadata apply-daily`

## 設計原則

- **確定性評分**：問題分類與星級評分不使用 LLM，純規則邏輯
- **禮貌爬蟲**：並行數限制（預設 5）、路徑穿越防護、錯誤隔離
- **無資料庫**：所有資料以檔案形式儲存
- **JSON 優先輸出**：所有指令預設輸出 JSON（`--format text` 提供人類可讀格式）；日誌與進度輸出至 stderr
- **Unix 哲學**：`dataset view` 輸出原始內容至 stdout，不做解析；搭配 `grep`、`jq`、`head` 等工具使用
- **RFC 6902 patch**：透過 `patch.json` 調整個別 provider 的 manifest
- **i18n**：支援英文與繁體中文，自動偵測系統語系

## 專案狀態

開發中。已完成：

- 統一 CLI（`tw-odc`）與 manifest-based 架構
- 格式偵測與驗證（inspector）
- 五星評分模型（scorer，★1–★3，★4/★5 規劃中）
- 政府資料品質指標評分（gov-tw scorer）
- 每日異動資料集下載（`params` URL 模板）與增量更新（`apply-daily`）
- 原始資料內容查看（`dataset view`）
- 國際化（i18n，en / zh-TW）

詳見 `docs/plans/`。
