# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

This project builds an automated system to audit government open data portals and evaluate datasets using Tim Berners-Lee's Five-Star Open Data model. Starting from the Taiwan government open data portal (https://data.gov.tw/), a crawler collects dataset entries while deterministic rules inspect formats, validate links, and detect common issues such as PDFs, spreadsheets used as databases, or broken downloads. Results are stored and scored so that dataset quality becomes measurable at scale, allowing systematic evaluation of how close public data ecosystems come to machine-readable and open formats.

Large language models are used only for communication, not evaluation. After rule-based analysis identifies issues, an LLM helps draft clear and polite improvement requests that a human can review and send to data providers. This approach allows a single individual to audit many datasets and apply gentle, continuous pressure for improvement, while also observing how institutions respond. Over time, such audits can improve public data quality and strengthen the feedback loop between open data availability and the capabilities of AI systems that rely on machine-readable information.

## Tech Stack

- Python >=3.13, managed with `uv` (see `.python-version`)
- Filesystem-based storage (no database)
- Async crawling (aiohttp, asyncio, aiolimiter)
- CLI via typer

## Commands

```bash
# Run single portal
uv run python -m data_gov_tw crawl

# Run all portals
uv run python main.py --concurrency 3

# Add dependencies
uv add <package>
```

## Architecture

### Portal-based structure

Each government open data portal is an independent Python package at the project root. Shared logic lives in `shared/`.

```
roc-open-data-checker/
├── main.py              # Orchestrator: discovers & runs all portals
├── shared/              # Shared scoring, utilities (future)
├── data_gov_tw/         # data.gov.tw portal
│   ├── __init__.py      # Exposes run() for orchestrator
│   ├── crawler.py       # Downloads export URLs
│   └── datasets/        # Raw downloaded files (gitignored)
├── data_taipei/         # Future: data.taipei portal
└── ...
```

### Why this structure

- Different portals have very different APIs and structures — each needs custom crawl logic
- Shared code (scoring, reporting) stays in `shared/`
- Each portal can run independently (`python -m data_gov_tw crawl`) or together via `main.py`

### Storage

- **Filesystem only, no database** — raw downloads in `datasets/`, future evaluation results as JSON files
- `datasets/` directories are gitignored

### Pipeline

`crawl → inspect → evaluate → report → draft emails`

### data.gov.tw specifics

The portal provides bulk export of all dataset metadata:
- `https://data.gov.tw/datasets/export/json`
- `https://data.gov.tw/datasets/export/csv`
- `https://data.gov.tw/datasets/export/xml`

These three exports are themselves open data and should be evaluated as datasets.

## Key Design Decisions

- **Deterministic scoring**: Issue classification and star scoring must NOT use LLMs — pure rule-based logic only
- **Polite crawling**: Rate-limited (2 req/s, max concurrency 5), robots.txt compliant, retry with backoff on 429
- **LLM only for email drafting**: Converts structured issue data into polite messages; human must review before sending
- **5-Star model**: ★ online → ★★ machine-readable → ★★★ open format → ★★★★ RDF/URI → ★★★★★ linked data
- **No database**: All data stored as files on the filesystem for simplicity
- **Portal as package**: Each portal is a top-level Python package, runnable independently or via orchestrator

## Language

Use Traditional Chinese (zh-TW) for user-facing text and documentation where appropriate, as this targets ROC/Taiwan government data.
