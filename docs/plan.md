# tw-odc — Implementation Plan

## 1. Project Goal

Build an automated system that:

1. Downloads dataset metadata from the Taiwan government open data portal (data.gov.tw).
2. Scaffolds per-provider manifests and downloads individual datasets.
3. Inspects datasets and evaluates them using **Tim Berners-Lee's 5-Star Open Data model**.
4. Records issues and scores as structured JSON on the filesystem.

Issue classification and scoring are **purely deterministic** — no LLMs in the evaluation pipeline. The CLI outputs structured JSON that any LLM agent (or human) can consume to produce reports, draft emails, or perform further analysis.

---

## 2. System Architecture

```
metadata download (data.gov.tw bulk exports)
  ↓
provider manifest scaffolding
  ↓
dataset download (per provider)
  ↓
format inspection (magic bytes, ZIP contents)
  ↓
5-Star scoring engine
  ↓
structured JSON output (issues.jsonl, scores.json)
  ↓
any LLM agent or human → reports, emails, dashboards
```

---

## 3. Technology Stack

**Language:** Python >=3.13, managed with `uv`

| Purpose             | Library        |
| ------------------- | -------------- |
| HTTP crawling       | `aiohttp`      |
| Async control       | `asyncio`      |
| File type detection | `python-magic` |
| CLI                 | `typer`        |
| JSON patching       | `jsonpatch`    |
| Terminal UI         | `rich`         |
| i18n                | `i18nice`      |

**No database.** All data stored as files on the filesystem.

---

## 4. Repository Layout

```
tw-odc/
├── manifest.json              # type: metadata — data.gov.tw export URLs
├── pyproject.toml             # registers tw-odc CLI entry point
├── tw_odc/                    # CLI package
│   ├── __init__.py            # FORMAT_ALIASES (中文格式名對照)
│   ├── __main__.py            # python -m tw_odc entry point
│   ├── cli.py                 # typer app — metadata/dataset subcommands
│   ├── fetcher.py             # async downloader (aiohttp, ETag caching)
│   ├── inspector.py           # file format detection & validation
│   ├── scorer.py              # 5-Star scoring engine
│   ├── manifest.py            # manifest I/O, RFC 6902 patch, scaffolding
│   ├── i18n.py                # locale detection and translation
│   └── locales/               # translation files
│       ├── en.json
│       └── zh-TW.json
├── <provider_slug>/           # one directory per provider organization
│   ├── manifest.json          # type: dataset — committed
│   ├── patch.json             # RFC 6902 patch — optional, committed
│   └── datasets/              # downloaded files — gitignored
├── tests/
│   ├── test_cli.py
│   ├── test_fetcher.py
│   ├── test_i18n.py
│   ├── test_inspector.py
│   ├── test_manifest.py
│   └── test_scorer.py
└── docs/
    └── plan.md
```

---

## 5. Data Storage

**Filesystem only, no database.**

### Manifest types

Two manifest types distinguished by the `type` field:

- **metadata** (`manifest.json` in project root): lists data.gov.tw bulk export URLs
- **dataset** (`manifest.json` in provider dirs): lists individual datasets for a provider

### Per-provider files

| File             | Description                              | Committed |
| ---------------- | ---------------------------------------- | --------- |
| `manifest.json`  | Dataset list for this provider           | Yes       |
| `patch.json`     | RFC 6902 patch for manifest adjustments  | Yes       |
| `datasets/`      | Downloaded data files                    | No        |
| `etags.json`     | ETag cache for conditional downloads     | No        |
| `issues.jsonl`   | Download/format issues (one JSON per line) | No      |
| `scores.json`    | 5-Star evaluation results                | No        |

---

## 6. Crawler Design

tw-odc does **not** crawl portal HTML pages. Instead it downloads bulk metadata exports from data.gov.tw and scaffolds provider manifests from the JSON export.

Design constraints:

- Concurrency-limited (default 5 simultaneous downloads)
- ETag-based conditional requests to avoid re-downloading
- Automatic SSL retry without verification (many government servers have certificate issues)
- Domain blocking on HTTP 429 (rate limit) — stops all requests to that domain
- Path traversal protection on destination filenames
- Error isolation — one failed download does not abort others

---

## 7. Dataset Inspection

Inspector analyzes each downloaded file.

### Format Detection

Determines actual file type using:

- Magic bytes (via `python-magic`)
- Comparison against declared format from manifest

### Checks

- File exists and is non-empty
- Declared format matches detected format
- ZIP contents inspection (detects formats inside archives)
- PDF detection (flagged as non-machine-readable)

---

## 8. Five-Star Evaluation Rules

Deterministic, rule-based scoring. **No LLMs.**

### ★ Available online

Data exists and is downloadable (HTTP 200).

### ★★ Machine-readable

```
CSV, JSON, XML, XLSX, ODS
```

### ★★★ Open format

```
CSV, JSON, XML, ODS
```

### ★★★★ RDF / URI-based identifiers

```
RDF, Turtle, JSON-LD, SPARQL endpoint
```

### ★★★★★ Linked data

```
External URIs, linked datasets, RDF triples referencing other domains
```

Currently ★★★★ and ★★★★★ detection is not yet implemented.

---

## 9. Issue Classification

Issues are recorded in `issues.jsonl` with structured fields:

```json
{"file": "1001.csv", "url": "https://...", "issue": "http_error", "detail": "HTTP 404"}
{"file": "1002.csv", "url": "https://...", "issue": "ssl_error", "detail": "..."}
```

Issue types:

```
http_error        — non-200 response
ssl_error         — certificate verification failed
rate_limited      — HTTP 429 / domain blocked
network_error     — connection failure
unexpected_error  — unhandled exception
format_mismatch   — declared format differs from detected
```

Issues are deterministic. LLMs must **not decide issues**.

---

## 10. CLI Commands

```bash
# Metadata operations (project root)
tw-odc metadata download          # download data.gov.tw exports
tw-odc metadata list              # list providers from metadata
tw-odc metadata create -p "機關"  # scaffold provider manifest
tw-odc metadata update -p "機關"  # update existing manifest

# Dataset operations (per provider)
tw-odc dataset --dir <slug> download
tw-odc dataset --dir <slug> list
tw-odc dataset --dir <slug> check
tw-odc dataset --dir <slug> score
tw-odc dataset --dir <slug> clean

# Global options
tw-odc --lang zh-TW ...           # locale (en or zh-TW)
```

All commands output JSON by default (`--format text` for human-readable). Logs and progress go to stderr.

---

## 11. LLM Integration

tw-odc itself contains **no LLM code**. The CLI produces structured JSON output (scores, issues, dataset metadata) that any LLM agent can consume to:

- Generate quality reports
- Draft improvement request emails to data providers
- Build dashboards or summaries
- Compare providers or track quality over time

This separation keeps the audit pipeline deterministic and reproducible, while allowing flexible downstream use by any AI agent or human workflow.

---

## 12. i18n

The CLI supports English (`en`, default) and Traditional Chinese (`zh-TW`) via the `--lang` flag or `LANG`/`LC_ALL` environment variables.

- Translation files: `tw_odc/locales/{en,zh-TW}.json`
- Error codes (`E001`–`E106`) are locale-independent identifiers
- Help text and docstrings are English-only
- i18nice library with JSON format, fallback to `en`

---

## 13. Development Milestones

### Phase 1 — Done

- Bulk metadata download from data.gov.tw
- Provider manifest scaffolding
- Per-provider dataset download with ETag caching
- Format detection and inspection
- 5-Star scoring engine
- CLI with `metadata` and `dataset` subcommand groups
- i18n support (en/zh-TW)

### Phase 2 — Planned

- ★★★★/★★★★★ detection (RDF, linked data)
- Incremental re-checking (only re-inspect changed files)
- Provider-level and national-level aggregate statistics

### Phase 3 — Future

- Dataset change detection over time
- API endpoint discovery
- Historical trend tracking
- Public transparency dashboard
