# Open Data Audit System – Implementation Plan

## 1. Project Goal

Build an automated system that:

1. Crawls government open data portals.
2. Inspects datasets and evaluates them using **Tim Berners-Lee’s 5-Star Open Data model**.
3. Records dataset quality metrics in a database.
4. Generates structured issue reports.
5. Uses an LLM only to draft **polite improvement request emails**.
6. Allows a human operator to review and send emails to dataset providers.

The system should minimize LLM usage and rely primarily on **deterministic rules**.

---

# 2. System Architecture

```
crawler
  ↓
dataset inspector
  ↓
rule-based scoring engine
  ↓
dataset database
  ↓
report generator
  ↓
LLM email drafting
  ↓
human review + send
```

---

# 3. Technology Stack

Recommended stack for fast development and long-term maintainability.

## Language

Python (>=3.11)

Reason:

* Strong ecosystem for data formats
* Async crawling support
* Good RDF libraries
* Fast iteration speed

## Core Libraries

| Purpose             | Library                   |
| ------------------- | ------------------------- |
| HTTP crawling       | `aiohttp`                 |
| Async control       | `asyncio`                 |
| Rate limiting       | `aiolimiter`              |
| HTML parsing        | `beautifulsoup4`          |
| CSV/XLSX parsing    | `pandas`, `openpyxl`      |
| RDF detection       | `rdflib`                  |
| File type detection | `python-magic`            |
| Database            | `sqlite`                  |
| CLI                 | `typer`                   |
| LLM interface       | optional (`openai`, etc.) |

---

# 4. Repository Layout

```
open-data-audit/
│
├─ pyproject.toml
├─ README.md
│
├─ src/
│   ├─ crawler/
│   │   └─ crawl_portal.py
│   │
│   ├─ inspector/
│   │   ├─ detect_format.py
│   │   ├─ parse_dataset.py
│   │   └─ validate_links.py
│   │
│   ├─ scoring/
│   │   └─ star_evaluator.py
│   │
│   ├─ storage/
│   │   └─ database.py
│   │
│   ├─ reporting/
│   │   └─ generate_reports.py
│   │
│   ├─ email/
│   │   └─ draft_email.py
│   │
│   └─ cli.py
│
└─ data/
    └─ audit.db
```

---

# 5. Database Schema

Use SQLite for simplicity.

### datasets

| column       | description          |
| ------------ | -------------------- |
| dataset_id   | unique identifier    |
| title        | dataset name         |
| agency       | provider             |
| source_url   | dataset page         |
| download_url | data file URL        |
| format       | detected file format |
| http_status  | HTTP status code     |
| size_bytes   | file size            |
| last_checked | timestamp            |

### evaluation

| column           | description |
| ---------------- | ----------- |
| dataset_id       | FK          |
| star_score       | 1–5         |
| machine_readable | bool        |
| open_format      | bool        |
| rdf_detected     | bool        |
| linked_data      | bool        |
| dead_links       | bool        |
| notes            | text        |

### issues

| column      | description    |
| ----------- | -------------- |
| dataset_id  | FK             |
| issue_type  | e.g. DEAD_LINK |
| description | explanation    |

---

# 6. Crawler Design

Crawler should be **low-concurrency and polite**.

Example limits:

```
2 requests / second
max concurrency = 5
```

Steps:

1. Fetch portal catalog pages
2. Extract dataset metadata
3. Extract download URLs
4. Store dataset record
5. Send URLs to inspector

Crawler should support:

* pagination
* retries
* backoff on `429`
* robots.txt compliance

---

# 7. Dataset Inspection

Inspector analyzes each dataset URL.

Checks include:

### HTTP Validation

```
200 → valid
404 → dead dataset
timeout → unreliable
```

### Format Detection

Determine file type using:

* file extension
* content-type header
* magic bytes

Common types:

```
CSV
JSON
XML
XLSX
PDF
HTML table
API endpoint
```

### Machine Readability

Machine readable formats:

```
CSV
JSON
XML
XLSX
GeoJSON
```

Not machine readable:

```
PDF
image
scanned document
```

### Open Format

Open formats:

```
CSV
JSON
XML
GeoJSON
```

Closed formats:

```
XLS
XLSX
DOC
PDF
```

### Link Validation

For datasets containing links:

* verify embedded URLs
* detect broken links

---

# 8. Five-Star Evaluation Rules

Use rule-based scoring.

### ★

Data exists online.

### ★★

Machine readable format.

```
CSV
JSON
XML
XLSX
```

### ★★★

Open format.

```
CSV
JSON
XML
```

### ★★★★

RDF / URI-based identifiers detected.

Indicators:

```
RDF
Turtle
JSON-LD
SPARQL endpoint
```

### ★★★★★

Linked data.

Detection:

```
external URIs
linked datasets
RDF triples referencing other domains
```

---

# 9. Issue Classification

Typical issue types:

```
DEAD_LINK
PDF_DATASET
EXCEL_ONLY
MISSING_METADATA
BROKEN_DOWNLOAD
NO_MACHINE_FORMAT
```

These should be deterministic.

LLMs must **not decide issues**.

---

# 10. Report Generation

Reports should include:

### Dataset Report

```
dataset title
agency
star score
detected issues
download URL
inspection timestamp
```

### Agency Summary

```
total datasets
average star score
dead link rate
machine-readable ratio
```

### National Summary

```
dataset distribution by format
star score distribution
dead dataset ratio
```

---

# 11. LLM Email Drafting

LLM should only convert structured issues into polite messages.

Input:

```
agency: Ministry of X
dataset: air quality statistics
issues:
 - Excel format
 - dead download link
score: ★★
```

LLM output:

```
Dear Data Provider,

During a routine open data audit we noticed several issues with the dataset "Air Quality Statistics".

Observed issues:
- Download link returns 404
- Dataset only provided in Excel format

Providing the dataset in CSV or JSON format would improve accessibility and machine usability.

Thank you for maintaining this dataset.
```

Human operator must review before sending.

---

# 12. CLI Commands

Example CLI interface:

```
audit crawl
audit inspect
audit evaluate
audit report
audit draft-emails
```

Typical workflow:

```
crawl → inspect → evaluate → report → draft emails
```

---

# 13. Initial Development Milestones

### Phase 1

* basic crawler
* SQLite database
* dataset metadata collection

### Phase 2

* format detection
* star scoring engine

### Phase 3

* issue detection
* reporting dashboard

### Phase 4

* LLM email drafting

### Phase 5

* incremental crawling
* long-term monitoring

---

# 14. Long-Term Enhancements

Possible improvements:

* dataset change detection
* API discovery
* semantic dataset linking
* historical trend reports
* public transparency dashboard

---

# 15. Expected Outcomes

The system should produce:

1. Quantitative measurements of open data quality
2. Dataset issue tracking
3. Agency-level data quality comparison
4. Automated but human-supervised improvement requests

This transforms open data evaluation into a **continuous auditing system**.
