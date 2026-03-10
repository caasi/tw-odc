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
uv run python -m data_gov_tw
```

下載 JSON、CSV、XML 三份匯出檔到 `data_gov_tw/datasets/`。

### 2. 查詢與產生 provider

```bash
# 列出所有提供機關
uv run python -m shared list data_gov_tw/datasets/export-json.json

# 搜尋特定機關
uv run python -m shared list data_gov_tw/datasets/export-json.json --query 交通部

# 只列出尚未產生 package 的機關（找出缺口）
uv run python -m shared list data_gov_tw/datasets/export-json.json --missing

# 產生指定機關的 package（可多個 -p）
uv run python -m shared scaffold data_gov_tw/datasets/export-json.json \
  -p "交通部中央氣象署"
```

### 3. 下載 provider 資料集

```bash
# 下載單一 provider
uv run python -m <provider_slug>

# 下載所有已產生的 provider（平行執行）
uv run python main.py --concurrency 3
```

### 4. 測試

```bash
uv run pytest -v
```

## 架構

每個提供機關是一個獨立的 Python package，包含 `manifest.json`（資料集清單）與 `__init__.py`。所有下載邏輯在 `shared/fetcher.py`，provider 產生器在 `shared/scaffold.py`。

```
roc-open-data-checker/
├── main.py              # 自動發現所有 provider 並執行下載
├── shared/
│   ├── fetcher.py       # 通用下載器（讀 manifest.json）
│   ├── scaffold.py      # 從 export.json 產生 provider package
│   └── __main__.py      # CLI: list / scaffold
├── data_gov_tw/         # data.gov.tw（手動維護）
│   ├── manifest.json    # 3 筆匯出 URL
│   └── datasets/        # 下載的檔案（gitignored）
├── <provider_slug>/     # 自動產生的 provider
│   ├── manifest.json
│   └── datasets/
└── tests/
```

## 專案狀態

開發中。已完成 manifest-based 架構與 provider scaffolding，下一步是實作格式檢查與評分。詳見 `docs/plans/`。
