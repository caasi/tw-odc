# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

This project builds an automated system to audit government open data portals and evaluate datasets using Tim Berners-Lee's Five-Star Open Data model. Starting from the Taiwan government open data portal (https://data.gov.tw/), a crawler collects dataset entries while deterministic rules inspect formats, validate links, and detect common issues such as PDFs, spreadsheets used as databases, or broken downloads. Results are stored and scored so that dataset quality becomes measurable at scale, allowing systematic evaluation of how close public data ecosystems come to machine-readable and open formats.

tw-odc itself contains no LLM code. All evaluation is deterministic and rule-based. The CLI outputs structured JSON (scores, issues, dataset metadata) that any LLM agent can consume to generate reports, draft improvement request emails, or build dashboards. This separation keeps the audit pipeline reproducible while allowing flexible downstream use by any AI agent or human workflow.

## Tech Stack

- Python >=3.13, managed with `uv` (see `.python-version`)
- Filesystem-based storage (no database)
- Async crawling (aiohttp, asyncio, aiolimiter)
- CLI via typer (`tw-odc` command)

## Commands

```bash
# Show configuration and path info
tw-odc config show

# Download data.gov.tw exports (JSON/CSV/XML)
tw-odc metadata download
tw-odc metadata download --only export-json.json   # download one file only
tw-odc metadata download --no-cache                 # bypass ETag cache
tw-odc metadata download --dir /path/to/dir         # specify metadata directory

# Download daily changed datasets (uses today's date by default)
tw-odc metadata download --only daily-changed-json.json
tw-odc metadata download --only daily-changed-csv.csv --date 2026-03-10

# Apply daily changes to existing provider manifests
tw-odc metadata apply-daily                          # uses today's date
tw-odc metadata apply-daily --date 2026-03-10        # specific date

# List providers from downloaded metadata (JSON output by default)
tw-odc metadata list
tw-odc metadata list --format text

# Search datasets in metadata
tw-odc metadata search <keywords...>
tw-odc metadata search 國防 採購                    # multiple keywords (AND)
tw-odc metadata search 臺中 --field provider        # restrict to provider name
tw-odc metadata search 工廠登記 --format text        # human-readable output

# Create a dataset manifest for a provider
tw-odc metadata create --provider "機關名稱"

# Update an existing dataset manifest
tw-odc metadata update --provider "機關名稱"
tw-odc metadata update --provider-dir <provider_slug>

# Download a provider's datasets
tw-odc dataset --dir <provider_slug> download
tw-odc dataset --dir <provider_slug> download --id <dataset_id>
tw-odc dataset --dir <provider_slug> download --no-cache

# List datasets in a provider manifest
tw-odc dataset --dir <provider_slug> list

# Inspect downloaded datasets
tw-odc dataset --dir <provider_slug> check
tw-odc dataset --dir <provider_slug> check --id <dataset_id>

# Score datasets (5-Star model, default)
tw-odc dataset --dir <provider_slug> score
tw-odc dataset --dir <provider_slug> score --id <dataset_id>

# Score with gov-tw quality indicators
tw-odc dataset --dir <provider_slug> score --method gov-tw
tw-odc dataset --dir <provider_slug> score --method gov-tw --id <dataset_id>

# View raw dataset content (pipe to grep/jq/head)
tw-odc dataset --dir <provider_slug> view --id <dataset_id>
tw-odc dataset --dir <provider_slug> view --id <dataset_id> | grep 關鍵字
tw-odc dataset --dir <provider_slug> view --id <dataset_id> | jq '.'

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

The CLI has three subcommand groups: `metadata` (operates on metadata manifests for data.gov.tw exports), `dataset` (operates on provider-level manifests for individual datasets), and `config` (shows configuration info).

### Directory structure

```
tw-odc/
├── manifest.json              # type: metadata — data.gov.tw export URLs (dev use)
├── pyproject.toml             # registers tw-odc CLI entry point (uv_build)
├── src/tw_odc/                # CLI package (src layout)
│   ├── __init__.py            # FORMAT_ALIASES (中文格式名對照)
│   ├── __main__.py            # python -m tw_odc entry point
│   ├── cli.py                 # typer app — metadata/dataset/config subcommands
│   ├── paths.py               # cross-platform path resolution (data_dir, ensure_manifest)
│   ├── fetcher.py             # async downloader (aiohttp, etag caching, HEAD health check)
│   ├── inspector.py           # file format detection & validation
│   ├── scorer.py              # 5-Star scoring engine
│   ├── gov_tw_scorer.py       # gov-tw quality indicators scoring
│   ├── manifest.py            # manifest I/O, RFC 6902 patch, scaffolding
│   ├── i18n.py                # locale detection and translation
│   ├── locales/               # en.json, zh-TW.json
│   └── default_manifest.json  # bundled default metadata manifest (bootstrapped on first run)
├── <provider_slug>/           # one directory per provider organization
│   ├── manifest.json          # type: dataset — committed
│   ├── patch.json             # RFC 6902 patch — optional, committed
│   └── datasets/              # downloaded files — gitignored
└── tests/
    ├── test_cli.py
    ├── test_fetcher.py
    ├── test_i18n.py
    ├── test_inspector.py
    ├── test_manifest.py
    ├── test_paths.py
    ├── test_scorer.py
    └── test_gov_tw_scorer.py
```

### How it works

- `src/tw_odc/paths.py` resolves the metadata storage directory: prefers `$PWD` if it contains a metadata manifest, otherwise falls back to `~/.config/tw-odc/` (cross-platform via platformdirs); `ensure_manifest` bootstraps the default manifest from bundled `default_manifest.json` on first run
- `src/tw_odc/manifest.py` reads `export-json.json` (downloaded metadata), groups datasets by provider (提供機關), derives a slug from download URLs, and creates/updates `manifest.json` per provider; `update_dataset_manifest` merges daily-changed entries incrementally; `find_existing_providers` maps provider names to local `pkg_dir` paths
- `src/tw_odc/fetcher.py` reads `manifest.json` from a directory and downloads all listed URLs with concurrency control, ETag caching, error isolation, HEAD health checks, and path traversal protection; `resolve_params` resolves URL template variables (e.g. `"today"` → `YYYY-MM-DD`); parameterized datasets bypass ETag caching entirely
- `src/tw_odc/inspector.py` detects actual file formats (via magic bytes), validates against declared format, inspects ZIP contents
- `src/tw_odc/scorer.py` scores datasets using the 5-Star Open Data model based on inspection results
- `src/tw_odc/gov_tw_scorer.py` scores datasets using 6 quality indicators from 數位發展部「政府資料品質提升機制運作指引」; requires export-json metadata for encoding, field, and timeliness checks
- Provider directories contain only `manifest.json` (and optional `patch.json`) — no Python code

### Manifest types

Two manifest types distinguished by the `type` field:
- **metadata** (`manifest.json` in metadata dir): lists data.gov.tw bulk exports; entries may include an optional `params` dict for URL template substitution (e.g., `{"date": "today"}`). Metadata dir is resolved by `data_dir()`: `$PWD` if local metadata manifest exists, otherwise `~/.config/tw-odc/`; overridable via `--dir`
- **dataset** (`manifest.json` in provider dirs): lists individual datasets for a provider

### Storage

- **Filesystem only, no database** — downloaded files in `datasets/`, metadata exports in metadata dir (may be `~/.config/tw-odc/` or project root)
- `datasets/` directories and export files are gitignored

### Pipeline

Full audit: `metadata download → manifest scaffolding → dataset download → inspect → score → JSON output`

Incremental update: `metadata download --only daily-changed-json.json → metadata apply-daily`

### data.gov.tw specifics

The portal provides bulk export of all dataset metadata (defined in root `manifest.json`):
- `https://data.gov.tw/datasets/export/json` → `export-json.json`
- `https://data.gov.tw/datasets/export/csv` → `export-csv.csv`
- `https://data.gov.tw/datasets/export/xml` → `export-xml.xml`

Daily changed datasets (parameterized — require `report_date`):
- `https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}` → `daily-changed-json.json`
- `https://data.gov.tw/api/front/dataset/changed/export?format=csv&report_date={date}` → `daily-changed-csv.csv`

The JSON export is the input for creating provider manifests. The daily-changed JSON has the same field structure as `export-json.json` plus an extra `資料集變動狀態` field (新增/修改/刪除).

## Key Design Decisions

- **Deterministic scoring**: Issue classification and star scoring must NOT use LLMs — pure rule-based logic only
- **Polite crawling**: Concurrency-limited (default 5), path-traversal-safe filenames, error isolation per download
- **No LLM in pipeline**: All evaluation is deterministic; any external LLM agent can consume the JSON output
- **5-Star model**: ★ online → ★★ machine-readable → ★★★ open format → ★★★★ RDF/URI → ★★★★★ linked data
- **No database**: All data stored as files on the filesystem for simplicity
- **Manifest-based providers**: Each provider has only `manifest.json` (+ optional `patch.json`); all logic in `src/tw_odc/`
- **src layout**: Package code lives in `src/tw_odc/`, built with `uv_build`
- **Cross-platform metadata**: `data_dir()` resolves metadata storage location; `~/.config/tw-odc/` as fallback; `--dir` override on metadata subcommands
- **Bootstrap on first run**: `ensure_manifest` copies bundled `default_manifest.json` to metadata dir if no manifest exists
- **HEAD health check**: URLs are checked with HEAD before downloading; 405/501 treated as healthy (server doesn't support HEAD)
- **Incremental scaffolding**: Providers are created one at a time via `metadata create --provider`
- **JSON-first output**: All commands output JSON by default (`--format text` for human-readable); logs/progress go to stderr
- **RFC 6902 patches**: Provider-specific manifest adjustments via `patch.json`
- **Stable filenames for parameterized datasets**: `params` affect URL template substitution only; filenames are always `{id}.{format}` regardless of resolved param values
- **ETag bypass for parameterized datasets**: Parameterized downloads always bypass conditional requests and are never written to the ETag cache; cache entries are only removed for parameterized URLs downloaded in the current run (older entries may remain)
- **Unix philosophy for data viewing**: `dataset view` outputs raw file content to stdout without parsing; use external tools (`grep`, `jq`, `head`) for filtering/formatting. Multi-file datasets print filenames to stderr to keep stdout clean for piping
- **Dual scoring**: `5-stars` (Tim Berners-Lee) and `gov-tw` (數位發展部品質指引) are independent scoring methods selectable via `--method`
- **Search index**: `metadata download` generates `export-search.jsonl` (slim JSONL with search fields only) for fast keyword search; `metadata search` falls back to full `export-json.json` parsing if index is missing

## Plans (RFC-style)

Design documents and implementation plans live in `docs/plans/` with RFC-style numbering:

```
docs/plans/
├── NNN-<topic>-design.md    # design document (brainstorming output)
└── NNN-<topic>-plan.md      # implementation plan (TDD tasks)
```

- **Numbering**: 3-digit zero-padded, monotonically increasing (001, 002, ...)
- **Naming**: `NNN-<kebab-case-topic>-{design,plan}.md`
- **Each feature gets a pair**: design doc first, then implementation plan
- **New plans**: use the next available number; check `ls docs/plans/` for the current max
- **Never reuse numbers**: even if a plan is superseded or abandoned

## Language

Use Traditional Chinese (zh-TW) for user-facing text and documentation where appropriate, as this targets ROC/Taiwan government data.
