# Provider Scaffold — Design Document

## Goal

Auto-generate a top-level Python package for each provider organization (提供機關) from data.gov.tw metadata. Each package downloads that provider's datasets using shared logic. Refactor `data_gov_tw` to use the same architecture.

## Data Source

`data_gov_tw/datasets/export.json` — 53,227 datasets from 797 providers.

## Project Structure

```
roc-open-data-checker/
├── mofti_gov_tw/                # 財政部財政人員訓練所
│   ├── __init__.py              # Exposes run(), calls shared fetcher
│   ├── manifest.json            # Dataset list for this provider
│   └── datasets/                # Downloaded files (gitignored)
├── apiservice_mol_gov_tw/       # 勞動部勞動及職業安全衛生研究所
│   ├── __init__.py
│   ├── manifest.json
│   └── datasets/
├── data_gov_tw/                 # Refactored: same architecture as all others
│   ├── __init__.py
│   ├── manifest.json            # 3 bulk export URLs
│   └── datasets/
├── shared/
│   ├── __init__.py
│   ├── fetcher.py               # Generic download logic (reads manifest.json)
│   └── scaffold.py              # Reads export.json, generates all provider packages
└── main.py                      # Orchestrator discovers all packages with manifest.json
```

## Naming Convention

1. Extract domain from download URLs (strip `www.`, port; replace `.` with `_`)
2. Single domain → use directly (e.g., `mofti_gov_tw`)
3. Multiple domains → pick most frequent
4. Fallback → slugified Chinese name (pinyin or hash)

## manifest.json

```json
{
  "provider": "財政部財政人員訓練所",
  "slug": "mofti_gov_tw",
  "datasets": [
    {
      "id": 40344,
      "name": "財政部財政人員訓練所年度採購案資訊",
      "format": "CSV",
      "urls": ["https://www.mofti.gov.tw/download/eb96f510f00d411c8c3c1d80a715591d"]
    }
  ]
}
```

For `data_gov_tw`:

```json
{
  "provider": "data.gov.tw",
  "slug": "data_gov_tw",
  "datasets": [
    {"id": "export-json", "name": "全站資料集匯出 JSON", "format": "JSON", "urls": ["https://data.gov.tw/datasets/export/json"]},
    {"id": "export-csv", "name": "全站資料集匯出 CSV", "format": "CSV", "urls": ["https://data.gov.tw/datasets/export/csv"]},
    {"id": "export-xml", "name": "全站資料集匯出 XML", "format": "XML", "urls": ["https://data.gov.tw/datasets/export/xml"]}
  ]
}
```

## __init__.py (identical for all packages)

```python
from shared.fetcher import fetch_all

async def run() -> None:
    await fetch_all(__file__)
```

## shared/fetcher.py

- Reads `manifest.json` relative to the calling `__init__.py`
- Downloads each URL to `datasets/{id}-{filename}.{format}`
- Rich progress bar, concurrent downloads
- Handles errors gracefully

## shared/scaffold.py

- Reads `data_gov_tw/datasets/export.json`
- Groups datasets by provider
- Derives slug from domain (naming convention above)
- Generates `__init__.py` + `manifest.json` per provider
- Skips `data_gov_tw` (handled manually with its special manifest)

## CLI

```bash
# Scaffold all provider packages
uv run python -m shared.scaffold

# Run single provider
uv run python -m mofti_gov_tw

# Run all providers
uv run python main.py --concurrency 3
```

## main.py Changes

Discover providers dynamically by scanning for directories containing `manifest.json` instead of hardcoded list.

## Out of Scope

- Scoring / evaluation
- Parsing dataset contents
- Inspector, reporting, email drafting
