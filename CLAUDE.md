# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

This project builds an automated system to audit government open data portals and evaluate datasets using Tim Berners-Lee's Five-Star Open Data model. Starting from the Taiwan government open data portal (https://data.gov.tw/), a crawler collects dataset entries while deterministic rules inspect formats, validate links, and detect common issues such as PDFs, spreadsheets used as databases, or broken downloads. Results are stored and scored so that dataset quality becomes measurable at scale, allowing systematic evaluation of how close public data ecosystems come to machine-readable and open formats.

Large language models are used only for communication, not evaluation. After rule-based analysis identifies issues, an LLM helps draft clear and polite improvement requests that a human can review and send to data providers. This approach allows a single individual to audit many datasets and apply gentle, continuous pressure for improvement, while also observing how institutions respond. Over time, such audits can improve public data quality and strengthen the feedback loop between open data availability and the capabilities of AI systems that rely on machine-readable information.

## Tech Stack

- Python >=3.13, managed with `uv` (see `.python-version`)
- Filesystem-based storage (no database)
- Async crawling (aiohttp, asyncio, aiolimiter)
- CLI via typer (`tw-odc` command)

## Commands

```bash
# Download data.gov.tw exports (JSON/CSV/XML) to project root
tw-odc metadata download
tw-odc metadata download --only export-json.json   # download one file only
tw-odc metadata download --no-cache                 # bypass ETag cache

# List providers from downloaded metadata (JSON output by default)
tw-odc metadata list
tw-odc metadata list --format text

# Create a dataset manifest for a provider
tw-odc metadata create --provider "機關名稱"

# Update an existing dataset manifest
tw-odc metadata update --provider "機關名稱"
tw-odc metadata update --dir <provider_slug>

# Download a provider's datasets
tw-odc dataset --dir <provider_slug> download
tw-odc dataset --dir <provider_slug> download --id <dataset_id>
tw-odc dataset --dir <provider_slug> download --no-cache

# List datasets in a provider manifest
tw-odc dataset --dir <provider_slug> list

# Inspect downloaded datasets
tw-odc dataset --dir <provider_slug> check
tw-odc dataset --dir <provider_slug> check --id <dataset_id>

# Score datasets (5-Star model)
tw-odc dataset --dir <provider_slug> score
tw-odc dataset --dir <provider_slug> score --id <dataset_id>

# Clean downloaded files
tw-odc dataset --dir <provider_slug> clean

# All commands also work via: uv run python -m tw_odc ...

# Run tests
uv run pytest -v

# Add dependencies
uv add <package>
```

## Architecture

### Unified CLI (`tw-odc`)

The CLI has two subcommand groups: `metadata` (operates on the root manifest for data.gov.tw exports) and `dataset` (operates on provider-level manifests for individual datasets).

### Directory structure

```
roc-open-data-checker/
├── manifest.json              # type: metadata — data.gov.tw export URLs
├── pyproject.toml             # registers tw-odc CLI entry point
├── tw_odc/                    # CLI package
│   ├── __init__.py            # FORMAT_ALIASES (中文格式名對照)
│   ├── __main__.py            # python -m tw_odc entry point
│   ├── cli.py                 # typer app — metadata/dataset subcommands
│   ├── fetcher.py             # async downloader (aiohttp, etag caching)
│   ├── inspector.py           # file format detection & validation
│   ├── scorer.py              # 5-Star scoring engine
│   └── manifest.py            # manifest I/O, RFC 6902 patch, scaffolding
├── <provider_slug>/           # one directory per provider organization
│   ├── manifest.json          # type: dataset — committed
│   ├── patch.json             # RFC 6902 patch — optional, committed
│   └── datasets/              # downloaded files — gitignored
└── tests/
    ├── test_cli.py
    ├── test_fetcher.py
    ├── test_inspector.py
    ├── test_manifest.py
    └── test_scorer.py
```

### How it works

- `tw_odc/manifest.py` reads `export-json.json` (downloaded metadata), groups datasets by provider (提供機關), derives a slug from download URLs, and creates/updates `manifest.json` per provider
- `tw_odc/fetcher.py` reads `manifest.json` from a directory and downloads all listed URLs with concurrency control, ETag caching, error isolation, and path traversal protection
- `tw_odc/inspector.py` detects actual file formats (via magic bytes), validates against declared format, inspects ZIP contents
- `tw_odc/scorer.py` scores datasets using the 5-Star Open Data model based on inspection results
- Provider directories contain only `manifest.json` (and optional `patch.json`) — no Python code

### Manifest types

Two manifest types distinguished by the `type` field:
- **metadata** (`manifest.json` in root): lists data.gov.tw bulk exports
- **dataset** (`manifest.json` in provider dirs): lists individual datasets for a provider

### Storage

- **Filesystem only, no database** — downloaded files in `datasets/`, metadata exports in project root
- `datasets/` directories and export files are gitignored

### Pipeline

`crawl → inspect → evaluate → report → draft emails`

### data.gov.tw specifics

The portal provides bulk export of all dataset metadata (defined in root `manifest.json`):
- `https://data.gov.tw/datasets/export/json` → `export-json.json`
- `https://data.gov.tw/datasets/export/csv` → `export-csv.csv`
- `https://data.gov.tw/datasets/export/xml` → `export-xml.xml`

The JSON export is the input for creating provider manifests.

## Key Design Decisions

- **Deterministic scoring**: Issue classification and star scoring must NOT use LLMs — pure rule-based logic only
- **Polite crawling**: Concurrency-limited (default 5), path-traversal-safe filenames, error isolation per download
- **LLM only for email drafting**: Converts structured issue data into polite messages; human must review before sending
- **5-Star model**: ★ online → ★★ machine-readable → ★★★ open format → ★★★★ RDF/URI → ★★★★★ linked data
- **No database**: All data stored as files on the filesystem for simplicity
- **Manifest-based providers**: Each provider has only `manifest.json` (+ optional `patch.json`); all logic in `tw_odc/`
- **Incremental scaffolding**: Providers are created one at a time via `metadata create --provider`
- **JSON-first output**: All commands output JSON by default (`--format text` for human-readable); logs/progress go to stderr
- **RFC 6902 patches**: Provider-specific manifest adjustments via `patch.json`

## Language

Use Traditional Chinese (zh-TW) for user-facing text and documentation where appropriate, as this targets ROC/Taiwan government data.
