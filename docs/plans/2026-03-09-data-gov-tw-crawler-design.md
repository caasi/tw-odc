# data.gov.tw Crawler — Design Document

## Goal

Build the first portal crawler: download all three bulk export files from data.gov.tw and save them locally. This is the foundation for future evaluation — the three exports (JSON, CSV, XML) are themselves open data to be scored.

## Data Source

data.gov.tw provides bulk export of all dataset metadata, updated daily:

- `https://data.gov.tw/datasets/export/json`
- `https://data.gov.tw/datasets/export/csv`
- `https://data.gov.tw/datasets/export/xml`

## Project Structure

```
roc-open-data-checker/
├── main.py                    # Orchestrator: discover & run all portals
├── shared/
│   └── __init__.py
├── data_gov_tw/
│   ├── __init__.py            # Exposes run() for orchestrator
│   ├── crawler.py             # Download logic
│   └── datasets/              # Downloaded files (gitignored)
│       ├── export.json
│       ├── export.csv
│       └── export.xml
├── docs/
└── pyproject.toml
```

## CLI Interface

### Single portal
```bash
uv run python -m data_gov_tw crawl
```

### All portals via orchestrator
```bash
uv run python main.py --concurrency 3
```

## Portal Convention

Each portal package must expose a `run()` async function in `__init__.py`. The orchestrator discovers all portal packages and calls `run()` with concurrency control.

## Crawler Behavior

1. Download each of the 3 export URLs
2. Save to `data_gov_tw/datasets/` with filenames `export.json`, `export.csv`, `export.xml`
3. Print progress to stdout
4. Handle errors gracefully (network timeout, HTTP errors)

## Storage

- Filesystem only, no database
- Raw files saved as-is from the server
- `datasets/` directories gitignored

## Out of Scope

- Scoring / evaluation of the exports
- Parsing the export contents to enumerate individual datasets
- Inspector, reporting, email drafting
- Other portals
