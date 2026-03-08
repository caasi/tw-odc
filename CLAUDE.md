# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

This project builds an automated system to audit government open data portals and evaluate datasets using Tim Berners-Lee's Five-Star Open Data model. Starting from the Taiwan government open data portal (https://data.gov.tw/), a crawler collects dataset entries while deterministic rules inspect formats, validate links, and detect common issues such as PDFs, spreadsheets used as databases, or broken downloads. Results are stored and scored so that dataset quality becomes measurable at scale, allowing systematic evaluation of how close public data ecosystems come to machine-readable and open formats.

Large language models are used only for communication, not evaluation. After rule-based analysis identifies issues, an LLM helps draft clear and polite improvement requests that a human can review and send to data providers. This approach allows a single individual to audit many datasets and apply gentle, continuous pressure for improvement, while also observing how institutions respond. Over time, such audits can improve public data quality and strengthen the feedback loop between open data availability and the capabilities of AI systems that rely on machine-readable information.

## Tech Stack

- Python >=3.13, managed with `uv` (see `.python-version`)
- SQLite for storage
- Async crawling (aiohttp, asyncio, aiolimiter)
- CLI via typer

## Commands

```bash
# Run the project
uv run python main.py

# Add dependencies
uv add <package>

# Run with uv
uv run <command>
```

## Architecture

The system follows a pipeline: `crawl → inspect → evaluate → report → draft emails`

Planned module structure under `src/`:

| Module | Purpose |
|---|---|
| `crawler/` | Crawl portal catalogs, extract dataset metadata and download URLs |
| `inspector/` | HTTP validation, format detection (extension/content-type/magic bytes), machine readability check |
| `scoring/` | Rule-based 5-star evaluation (no LLM) |
| `storage/` | SQLite database (datasets, evaluation, issues tables) |
| `reporting/` | Dataset/agency/national summary reports |
| `email/` | LLM-drafted improvement request emails (human review required before sending) |
| `cli.py` | CLI entry point (typer) |

## Key Design Decisions

- **Deterministic scoring**: Issue classification and star scoring must NOT use LLMs — pure rule-based logic only
- **Polite crawling**: Rate-limited (2 req/s, max concurrency 5), robots.txt compliant, retry with backoff on 429
- **LLM only for email drafting**: Converts structured issue data into polite messages; human must review before sending
- **5-Star model**: ★ online → ★★ machine-readable → ★★★ open format → ★★★★ RDF/URI → ★★★★★ linked data

## Language

Use Traditional Chinese (zh-TW) for user-facing text and documentation where appropriate, as this targets ROC/Taiwan government data.
