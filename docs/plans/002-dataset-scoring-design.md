# Dataset Scoring System Design

## Goal

Implement rule-based dataset scoring using Tim Berners-Lee's 5-Star Open Data model (★1~★3 for v1). Score downloaded datasets by inspecting actual file content and comparing against manifest metadata.

## Architecture: Inspector + Scorer Separation

Two modules with distinct responsibilities:

- **`shared/inspector.py`** — Detects facts: actual file format via magic bytes, ZIP content listing, file existence/size
- **`shared/scorer.py`** — Evaluates facts: assigns star scores and classifies issues based on inspection results

### Why separated

Inspector answers "what is this file?" — Scorer answers "how good is this dataset?" Each can be tested independently. Inspector is reusable for future features (format migration tracking, content analysis).

## File Layout

```
shared/
├── inspector.py    # Format detection, magic bytes, ZIP inspection
├── scorer.py       # Star scoring + issue classification
└── __main__.py     # CLI: add `score` subcommand

<provider>/
├── manifest.json
├── datasets/       # Downloaded raw files
├── scores.json     # Scoring results (NEW)
├── issues.jsonl    # Download issues (existing)
└── etags.json      # Conditional request cache (existing)
```

## Data Flow

```
manifest.json + datasets/*
        ↓
   inspector.py
   - Read manifest format field
   - Verify actual format via magic bytes
   - ZIP → list contents, detect inner formats
   - Output: InspectionResult per dataset
        ↓
   scorer.py
   - ★1: File exists and was downloadable
   - ★2: Machine-readable (CSV, JSON, XML, XLSX)
   - ★3: Open format (CSV, JSON, XML)
   - Classify issues
   - Output: scores.json
```

## scores.json Structure

```json
{
  "provider": "警政署",
  "slug": "opdadm_moi_gov_tw",
  "scored_at": "2026-03-09T12:00:00",
  "datasets": [
    {
      "id": "12818",
      "name": "即時交通事故資料(A1類)",
      "declared_format": "CSV",
      "detected_format": "csv",
      "star_score": 3,
      "stars": {
        "available_online": true,
        "machine_readable": true,
        "open_format": true
      },
      "issues": []
    },
    {
      "id": "176648",
      "name": "某份報告",
      "declared_format": "PDF",
      "detected_format": "pdf",
      "star_score": 1,
      "stars": {
        "available_online": true,
        "machine_readable": false,
        "open_format": false
      },
      "issues": ["PDF_DATASET"]
    }
  ]
}
```

## CLI

```bash
# Score a single provider
uv run python -m shared score opdadm_moi_gov_tw

# Score all providers
uv run python -m shared score --all
```

## Format Classification Rules

| Format | Stars | Machine-Readable | Open Format | Notes |
|--------|-------|-----------------|-------------|-------|
| CSV    | 3     | Yes             | Yes         |       |
| JSON   | 3     | Yes             | Yes         |       |
| XML    | 3     | Yes             | Yes         |       |
| KMZ    | 2     | Yes             | No          | Google proprietary |
| XLSX   | 2     | Yes             | No          |       |
| PDF    | 1     | No              | No          | Issue: PDF_DATASET |
| 其他   | 1     | No              | No          | Unknown format |
| API    | —     | Special         | Special     | Needs per-case handling |
| ZIP    | —     | By contents     | By contents | Decompress and score inner files |

## Issue Types

| Issue | Trigger |
|-------|---------|
| `FORMAT_MISMATCH` | Manifest declared format ≠ magic bytes detection |
| `PDF_DATASET` | Dataset provided as PDF |
| `NOT_MACHINE_READABLE` | Format is not machine-readable (PDF, images) |
| `DOWNLOAD_FAILED` | No file found in datasets/ (cross-reference issues.jsonl) |
| `EMPTY_FILE` | File size is 0 bytes |
| `ZIP_CONTAINS_NON_OPEN` | ZIP contains non-open-format files |

## Inspector Details

### Magic Bytes Detection

Use `python-magic` (libmagic wrapper) for reliable format detection. Fallback to extension-based detection if magic is unavailable.

Key signatures:
- PDF: `%PDF`
- ZIP: `PK\x03\x04`
- XML: `<?xml` or BOM + `<?xml`
- JSON: starts with `{` or `[` (after whitespace/BOM)
- CSV: heuristic (no magic bytes — check for comma/tab delimiters in first few lines)

### ZIP Handling

1. Open ZIP with `zipfile` stdlib
2. List all entries
3. Detect format of each entry by extension + magic bytes
4. Score based on the "worst" format found (conservative)
5. If ZIP cannot be opened → issue: `CORRUPT_ZIP`

### API Format

Datasets with format "API" in manifest are skipped in v1 — marked as `unscored` with reason "api_endpoint". Future versions may probe the endpoint.

## Scorer Details

### Star Assignment Logic

```python
def score(inspection: InspectionResult) -> int:
    if not inspection.file_exists:
        return 0  # not even online
    if not inspection.machine_readable:
        return 1  # online but not machine-readable
    if not inspection.open_format:
        return 2  # machine-readable but proprietary
    return 3      # open format
```

### Multi-URL Datasets

Some datasets have multiple URLs (e.g., monthly data splits). Score each file individually, then take the **minimum** score for the dataset (conservative — weakest link determines overall quality).

## Testing Strategy

- Unit tests for inspector: feed known file bytes, verify detected format
- Unit tests for scorer: feed InspectionResult objects, verify star scores and issues
- Integration test: use opdadm_moi_gov_tw as real-world example (a few sample files)
- No network access needed — all tests operate on local files or fixtures

## Out of Scope (v1)

- ★4 (RDF/URI) and ★5 (Linked Data) detection
- Deep content validation (CSV column parsing, JSON schema validation)
- API endpoint probing
- Report generation (separate future feature)
- LLM email drafting (separate future feature)
