# Dataset Scoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Score downloaded datasets on a 1-3 star scale using rule-based format inspection and the 5-Star Open Data model.

**Architecture:** Two modules — `shared/inspector.py` detects actual file formats via magic bytes and ZIP inspection; `shared/scorer.py` assigns star scores and classifies issues. A new `score` CLI subcommand in `shared/__main__.py` triggers scoring per provider. Results are written to `scores.json` in each provider directory.

**Tech Stack:** Python 3.13, python-magic (libmagic), zipfile (stdlib), pytest, typer

**Design doc:** `docs/plans/2026-03-09-dataset-scoring-design.md`

---

## Background Context

### Project structure

```
roc-open-data-checker/
├── shared/
│   ├── __init__.py      # FORMAT_ALIASES dict
│   ├── __main__.py      # CLI: `list` and `scaffold` subcommands (typer)
│   ├── fetcher.py       # Download logic, reads manifest.json
│   └── scaffold.py      # Provider package generator
├── opdadm_moi_gov_tw/   # Example provider (警政署, 120 datasets)
│   ├── manifest.json    # {"provider", "slug", "datasets": [{id, name, format, urls}]}
│   ├── datasets/        # Downloaded files (gitignored)
│   ├── issues.jsonl     # Download errors (line-delimited JSON)
│   └── etags.json       # Conditional request cache
├── tests/
│   ├── test_fetcher.py
│   ├── test_scaffold.py
│   ├── test_data_gov_tw.py
│   └── test_main.py
└── pyproject.toml       # deps: aiohttp, rich, typer; dev: pytest, pytest-asyncio
```

### manifest.json dataset entry format

```json
{
  "id": "12818",
  "name": "即時交通事故資料(A1類)",
  "format": "csv",
  "urls": ["https://..."]
}
```

### Filename convention in datasets/

- Single URL: `{id}.{format}` (e.g., `12818.csv`)
- Multiple URLs: `{id}-{index}.{format}` (e.g., `13139-1.zip`, `13139-2.zip`)
- Format is lowercased from manifest

### Existing test pattern

Tests use `pytest` with `tmp_path` fixtures. See `tests/test_fetcher.py` for the pattern — create a minimal package dir with manifest.json, then test functions against it.

---

## Task 1: Add python-magic dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the dependency**

```bash
uv add python-magic
```

**Step 2: Verify it installs and works**

```bash
uv run python -c "import magic; print(magic.from_buffer(b'%PDF-1.4', mime=True))"
```

Expected output: `application/pdf`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add python-magic dependency for format detection"
```

---

## Task 2: Implement inspector — format detection

**Files:**
- Create: `shared/inspector.py`
- Create: `tests/test_inspector.py`

### Step 1: Write failing tests for format detection

Create `tests/test_inspector.py`:

```python
import pytest
from shared.inspector import detect_format


class TestDetectFormat:
    """detect_format(file_path) returns the detected format string."""

    def test_csv_file(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\n")
        assert detect_format(f) == "csv"

    def test_json_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        assert detect_format(f) == "json"

    def test_json_array(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[{"key": "value"}]')
        assert detect_format(f) == "json"

    def test_xml_file(self, tmp_path):
        f = tmp_path / "data.xml"
        f.write_text('<?xml version="1.0"?><root/>')
        assert detect_format(f) == "xml"

    def test_pdf_file(self, tmp_path):
        f = tmp_path / "data.pdf"
        f.write_bytes(b"%PDF-1.4 fake pdf content")
        assert detect_format(f) == "pdf"

    def test_zip_file(self, tmp_path):
        import zipfile
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("inner.csv", "a,b\n1,2\n")
        assert detect_format(f) == "zip"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"")
        assert detect_format(f) == "empty"

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "missing.csv"
        assert detect_format(f) == "missing"

    def test_xlsx_file(self, tmp_path):
        """XLSX files are ZIP-based but should be detected as xlsx."""
        f = tmp_path / "data.xlsx"
        # XLSX is a ZIP with specific structure; minimal PK header + xl/ entry
        import zipfile
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("xl/workbook.xml", "<workbook/>")
            zf.writestr("[Content_Types].xml", "<Types/>")
        assert detect_format(f) == "xlsx"
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_inspector.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shared.inspector'`

### Step 3: Implement detect_format

Create `shared/inspector.py`:

```python
"""Inspect downloaded dataset files to detect actual formats."""

import zipfile
from pathlib import Path

import magic


def detect_format(file_path: Path) -> str:
    """Detect the actual format of a file using magic bytes.

    Returns one of: csv, json, xml, pdf, zip, xlsx, kmz, xls, or the
    MIME subtype for unknown types. Returns 'empty' for zero-byte files
    and 'missing' if the file does not exist.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return "missing"
    if file_path.stat().st_size == 0:
        return "empty"

    mime = magic.from_file(str(file_path), mime=True)

    # ZIP-based formats need further inspection
    if mime == "application/zip" or mime == "application/x-zip-compressed":
        return _classify_zip(file_path)

    return _MIME_TO_FORMAT.get(mime, mime.split("/")[-1])


_MIME_TO_FORMAT: dict[str, str] = {
    "text/csv": "csv",
    "text/plain": "csv",  # magic often detects CSV as text/plain
    "application/json": "json",
    "text/json": "json",
    "text/xml": "xml",
    "application/xml": "xml",
    "application/pdf": "pdf",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.google-earth.kmz": "kmz",
}


def _classify_zip(file_path: Path) -> str:
    """Distinguish ZIP from XLSX/KMZ by inspecting archive contents."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            # XLSX: contains xl/ directory
            if any(n.startswith("xl/") for n in names):
                return "xlsx"
            # KMZ: contains .kml file
            if any(n.endswith(".kml") for n in names):
                return "kmz"
            return "zip"
    except (zipfile.BadZipFile, OSError):
        return "zip"
```

**Important note for the implementer:** The `text/plain` → `csv` mapping is a simplification. libmagic cannot reliably distinguish CSV from plain text. This is acceptable because we cross-reference with the manifest's declared format in the scorer. If magic says `text/plain` and manifest says `csv`, we trust it. If manifest says something else, it becomes a `FORMAT_MISMATCH`.

### Step 4: Run tests

```bash
uv run pytest tests/test_inspector.py -v
```

Expected: All PASS. Note: the `text/plain` vs `text/csv` detection depends on libmagic version. If `test_csv_file` fails because magic returns `text/plain`, the implementation already handles this (mapped to `csv`). If it returns something else unexpected, adjust `_MIME_TO_FORMAT`.

### Step 5: Commit

```bash
git add shared/inspector.py tests/test_inspector.py
git commit -m "feat: add inspector module with magic-bytes format detection"
```

---

## Task 3: Implement inspector — ZIP content inspection

**Files:**
- Modify: `shared/inspector.py`
- Modify: `tests/test_inspector.py`

### Step 1: Write failing tests for ZIP content listing

Append to `tests/test_inspector.py`:

```python
from shared.inspector import inspect_zip_contents


class TestInspectZipContents:
    """inspect_zip_contents returns list of detected formats inside a ZIP."""

    def test_zip_with_csv(self, tmp_path):
        import zipfile
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("data.csv", "a,b\n1,2\n")
        result = inspect_zip_contents(f)
        assert result == ["csv"]

    def test_zip_with_mixed_formats(self, tmp_path):
        import zipfile
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("data.csv", "a,b\n1,2\n")
            zf.writestr("report.pdf", "%PDF-1.4 fake")
        result = sorted(inspect_zip_contents(f))
        assert result == ["csv", "pdf"]

    def test_zip_with_nested_zip(self, tmp_path):
        """Nested ZIPs are reported as 'zip', not recursed into."""
        import zipfile
        inner = tmp_path / "inner.zip"
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("x.csv", "a\n1\n")
        f = tmp_path / "outer.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.write(inner, "inner.zip")
        result = inspect_zip_contents(f)
        assert result == ["zip"]

    def test_corrupt_zip(self, tmp_path):
        f = tmp_path / "bad.zip"
        f.write_bytes(b"not a zip")
        result = inspect_zip_contents(f)
        assert result == []

    def test_zip_ignores_directories(self, tmp_path):
        """Directory entries inside ZIP should be skipped."""
        import zipfile
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("subdir/data.json", '{"a": 1}')
        result = inspect_zip_contents(f)
        assert result == ["json"]
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_inspector.py::TestInspectZipContents -v
```

Expected: FAIL — `ImportError: cannot import name 'inspect_zip_contents'`

### Step 3: Implement inspect_zip_contents

Add to `shared/inspector.py`:

```python
import tempfile


def inspect_zip_contents(file_path: Path) -> list[str]:
    """List detected formats of files inside a ZIP archive.

    Returns a list of format strings (one per file in the archive).
    Skips directory entries. Returns empty list for corrupt ZIPs.
    Does NOT recurse into nested ZIPs.
    """
    file_path = Path(file_path)
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            formats = []
            with tempfile.TemporaryDirectory() as tmpdir:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    extracted = Path(zf.extract(info, tmpdir))
                    fmt = detect_format(extracted)
                    formats.append(fmt)
            return formats
    except (zipfile.BadZipFile, OSError):
        return []
```

### Step 4: Run tests

```bash
uv run pytest tests/test_inspector.py -v
```

Expected: All PASS.

### Step 5: Commit

```bash
git add shared/inspector.py tests/test_inspector.py
git commit -m "feat: add ZIP content inspection to inspector"
```

---

## Task 4: Implement inspector — inspect_dataset (full inspection per dataset)

**Files:**
- Modify: `shared/inspector.py`
- Modify: `tests/test_inspector.py`

### Step 1: Write failing tests for inspect_dataset

Append to `tests/test_inspector.py`:

```python
from shared.inspector import inspect_dataset, InspectionResult


class TestInspectDataset:
    """inspect_dataset checks a single dataset entry against its files."""

    def test_csv_dataset_single_file(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_text("a,b\n1,2\n")

        dataset = {"id": "1001", "name": "Test", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert isinstance(result, InspectionResult)
        assert result.dataset_id == "1001"
        assert result.declared_format == "csv"
        assert result.detected_formats == ["csv"]
        assert result.file_exists is True
        assert result.file_empty is False
        assert result.issues == []

    def test_missing_file(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()

        dataset = {"id": "9999", "name": "Missing", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.file_exists is False
        assert result.detected_formats == ["missing"]
        assert "DOWNLOAD_FAILED" in result.issues

    def test_empty_file(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_bytes(b"")

        dataset = {"id": "1001", "name": "Empty", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.file_empty is True
        assert "EMPTY_FILE" in result.issues

    def test_format_mismatch(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_bytes(b"%PDF-1.4 fake pdf")

        dataset = {"id": "1001", "name": "Sneaky PDF", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.declared_format == "csv"
        assert result.detected_formats == ["pdf"]
        assert "FORMAT_MISMATCH" in result.issues

    def test_zip_dataset_inspects_contents(self, tmp_path):
        import zipfile
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        zf_path = datasets_dir / "2001.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("data.csv", "a,b\n1,2\n")

        dataset = {"id": "2001", "name": "Zipped CSV", "format": "zip", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.detected_formats == ["csv"]
        assert result.zip_contents == ["csv"]

    def test_multi_url_dataset(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "3001-1.csv").write_text("a\n1\n")
        (datasets_dir / "3001-2.csv").write_text("b\n2\n")

        dataset = {"id": "3001", "name": "Multi", "format": "csv", "urls": ["http://a", "http://b"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.file_exists is True
        assert result.detected_formats == ["csv", "csv"]

    def test_pdf_dataset_issue(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "5001.pdf").write_bytes(b"%PDF-1.4 real pdf")

        dataset = {"id": "5001", "name": "Report", "format": "pdf", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert "PDF_DATASET" in result.issues
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_inspector.py::TestInspectDataset -v
```

Expected: FAIL — `ImportError: cannot import name 'inspect_dataset'`

### Step 3: Implement InspectionResult and inspect_dataset

Add to `shared/inspector.py`:

```python
from dataclasses import dataclass, field


@dataclass
class InspectionResult:
    """Result of inspecting a single dataset."""
    dataset_id: str
    dataset_name: str
    declared_format: str
    detected_formats: list[str]
    file_exists: bool
    file_empty: bool
    zip_contents: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def inspect_dataset(dataset: dict, datasets_dir: Path) -> InspectionResult:
    """Inspect a dataset entry by examining its downloaded files.

    Args:
        dataset: A dataset dict from manifest.json with keys: id, name, format, urls.
        datasets_dir: Path to the provider's datasets/ directory.

    Returns:
        InspectionResult with detected formats, file status, and issues.
    """
    dataset_id = str(dataset["id"])
    declared_fmt = dataset["format"].lower()
    urls = dataset["urls"]
    url_count = len(urls)

    detected_formats: list[str] = []
    zip_contents: list[str] = []
    issues: list[str] = []
    any_exists = False
    any_empty = False

    for i in range(url_count):
        if url_count == 1:
            filename = f"{dataset_id}.{declared_fmt}"
        else:
            filename = f"{dataset_id}-{i + 1}.{declared_fmt}"

        file_path = datasets_dir / filename
        fmt = detect_format(file_path)

        if fmt == "missing":
            detected_formats.append("missing")
            continue

        any_exists = True

        if fmt == "empty":
            any_empty = True
            detected_formats.append("empty")
            continue

        # For ZIP files, inspect contents
        if fmt == "zip":
            contents = inspect_zip_contents(file_path)
            zip_contents.extend(contents)
            # Use inner formats for scoring (not "zip" itself)
            detected_formats.extend(contents if contents else ["zip"])
        else:
            detected_formats.append(fmt)

    # Classify issues
    if not any_exists:
        issues.append("DOWNLOAD_FAILED")
    if any_empty:
        issues.append("EMPTY_FILE")

    # Format mismatch: declared vs detected (skip for ZIP since we look inside)
    if declared_fmt != "zip" and any_exists:
        for fmt in detected_formats:
            if fmt not in ("missing", "empty") and fmt != declared_fmt:
                # text/plain detected as csv is acceptable when declared csv
                if not (declared_fmt == "csv" and fmt == "csv"):
                    issues.append("FORMAT_MISMATCH")
                    break

    # PDF-specific issue
    if declared_fmt == "pdf" or "pdf" in detected_formats:
        issues.append("PDF_DATASET")

    # ZIP contains non-open formats
    if zip_contents:
        non_open = [f for f in zip_contents if f not in ("csv", "json", "xml")]
        if non_open:
            issues.append("ZIP_CONTAINS_NON_OPEN")

    return InspectionResult(
        dataset_id=dataset_id,
        dataset_name=dataset["name"],
        declared_format=declared_fmt,
        detected_formats=detected_formats,
        file_exists=any_exists,
        file_empty=any_empty,
        zip_contents=zip_contents,
        issues=issues,
    )
```

### Step 4: Run tests

```bash
uv run pytest tests/test_inspector.py -v
```

Expected: All PASS. Some tests may need minor adjustments depending on how libmagic classifies small text files. The `text/plain` → `csv` mapping handles the most common case. If a test fails, check what `magic.from_file()` returns for that fixture and adjust `_MIME_TO_FORMAT` accordingly.

### Step 5: Commit

```bash
git add shared/inspector.py tests/test_inspector.py
git commit -m "feat: add inspect_dataset with format mismatch and issue detection"
```

---

## Task 5: Implement scorer — star scoring logic

**Files:**
- Create: `shared/scorer.py`
- Create: `tests/test_scorer.py`

### Step 1: Write failing tests

Create `tests/test_scorer.py`:

```python
import pytest
from shared.inspector import InspectionResult
from shared.scorer import score_dataset, DatasetScore


# -- Format classification helpers --

class TestScoreDataset:
    """score_dataset(InspectionResult) -> DatasetScore with star rating."""

    def test_csv_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        score = score_dataset(inspection)
        assert score.star_score == 3
        assert score.stars["available_online"] is True
        assert score.stars["machine_readable"] is True
        assert score.stars["open_format"] is True

    def test_json_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="1002", dataset_name="Test",
            declared_format="json", detected_formats=["json"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 3

    def test_xml_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="1003", dataset_name="Test",
            declared_format="xml", detected_formats=["xml"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 3

    def test_xlsx_gets_2_stars(self):
        inspection = InspectionResult(
            dataset_id="1004", dataset_name="Test",
            declared_format="xlsx", detected_formats=["xlsx"],
            file_exists=True, file_empty=False,
        )
        score = score_dataset(inspection)
        assert score.star_score == 2
        assert score.stars["machine_readable"] is True
        assert score.stars["open_format"] is False

    def test_pdf_gets_1_star(self):
        inspection = InspectionResult(
            dataset_id="1005", dataset_name="Test",
            declared_format="pdf", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
            issues=["PDF_DATASET"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 1
        assert score.stars["available_online"] is True
        assert score.stars["machine_readable"] is False

    def test_missing_file_gets_0_stars(self):
        inspection = InspectionResult(
            dataset_id="1006", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
            issues=["DOWNLOAD_FAILED"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 0
        assert score.stars["available_online"] is False

    def test_empty_file_gets_0_stars(self):
        inspection = InspectionResult(
            dataset_id="1007", dataset_name="Test",
            declared_format="csv", detected_formats=["empty"],
            file_exists=True, file_empty=True,
            issues=["EMPTY_FILE"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 0

    def test_zip_with_csv_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="2001", dataset_name="Test",
            declared_format="zip", detected_formats=["csv"],
            file_exists=True, file_empty=False,
            zip_contents=["csv"],
        )
        assert score_dataset(inspection).star_score == 3

    def test_zip_with_pdf_gets_1_star(self):
        inspection = InspectionResult(
            dataset_id="2002", dataset_name="Test",
            declared_format="zip", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
            zip_contents=["pdf"],
            issues=["PDF_DATASET", "ZIP_CONTAINS_NON_OPEN"],
        )
        assert score_dataset(inspection).star_score == 1

    def test_zip_with_mixed_uses_minimum(self):
        """ZIP with CSV + PDF → score by worst format (PDF = 1 star)."""
        inspection = InspectionResult(
            dataset_id="2003", dataset_name="Test",
            declared_format="zip", detected_formats=["csv", "pdf"],
            file_exists=True, file_empty=False,
            zip_contents=["csv", "pdf"],
            issues=["ZIP_CONTAINS_NON_OPEN"],
        )
        assert score_dataset(inspection).star_score == 1

    def test_multi_url_uses_minimum(self):
        """Multiple files → score by worst file."""
        inspection = InspectionResult(
            dataset_id="3001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv", "csv"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 3

    def test_unknown_format_gets_1_star(self):
        inspection = InspectionResult(
            dataset_id="4001", dataset_name="Test",
            declared_format="其他", detected_formats=["octet-stream"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 1

    def test_score_preserves_issues(self):
        inspection = InspectionResult(
            dataset_id="5001", dataset_name="Test",
            declared_format="csv", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
            issues=["FORMAT_MISMATCH", "PDF_DATASET"],
        )
        score = score_dataset(inspection)
        assert "FORMAT_MISMATCH" in score.issues
        assert "PDF_DATASET" in score.issues


class TestDatasetScoreToDict:
    """DatasetScore.to_dict() produces the scores.json entry format."""

    def test_to_dict(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test Data",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        score = score_dataset(inspection)
        d = score.to_dict()

        assert d["id"] == "1001"
        assert d["name"] == "Test Data"
        assert d["declared_format"] == "csv"
        assert d["detected_format"] == "csv"
        assert d["star_score"] == 3
        assert d["stars"]["available_online"] is True
        assert d["stars"]["machine_readable"] is True
        assert d["stars"]["open_format"] is True
        assert d["issues"] == []
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_scorer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shared.scorer'`

### Step 3: Implement scorer

Create `shared/scorer.py`:

```python
"""Score datasets using the 5-Star Open Data model (★1-★3 for v1)."""

from dataclasses import dataclass, field

from shared.inspector import InspectionResult


# Formats that are machine-readable (★2)
MACHINE_READABLE = {"csv", "json", "xml", "xlsx", "xls", "kmz", "geojson"}

# Formats that are open (★3) — subset of machine-readable
OPEN_FORMATS = {"csv", "json", "xml", "geojson"}


def _format_star(fmt: str) -> int:
    """Return star score for a single detected format."""
    if fmt in ("missing", "empty"):
        return 0
    if fmt in OPEN_FORMATS:
        return 3
    if fmt in MACHINE_READABLE:
        return 2
    return 1  # online but not machine-readable (PDF, unknown, etc.)


@dataclass
class DatasetScore:
    """Scoring result for a single dataset."""
    dataset_id: str
    dataset_name: str
    declared_format: str
    detected_format: str  # primary detected format (or comma-separated for multi)
    star_score: int
    stars: dict[str, bool]
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.dataset_id,
            "name": self.dataset_name,
            "declared_format": self.declared_format,
            "detected_format": self.detected_format,
            "star_score": self.star_score,
            "stars": self.stars,
            "issues": self.issues,
        }


def score_dataset(inspection: InspectionResult) -> DatasetScore:
    """Score a dataset based on its inspection result.

    Uses the minimum star score across all detected formats
    (conservative — weakest link determines quality).
    """
    formats = [f for f in inspection.detected_formats if f not in ("missing", "empty")]

    if not inspection.file_exists or not formats:
        star = 0
    else:
        star = min(_format_star(f) for f in formats)

    # Handle empty files as 0 stars
    if inspection.file_empty and not formats:
        star = 0

    available = inspection.file_exists and not inspection.file_empty
    machine_readable = star >= 2
    open_format = star >= 3

    # Determine primary detected format for display
    if formats:
        detected_fmt = formats[0] if len(formats) == 1 else ",".join(sorted(set(formats)))
    else:
        detected_fmt = "missing" if not inspection.file_exists else "empty"

    return DatasetScore(
        dataset_id=inspection.dataset_id,
        dataset_name=inspection.dataset_name,
        declared_format=inspection.declared_format,
        detected_format=detected_fmt,
        star_score=star,
        stars={
            "available_online": available,
            "machine_readable": machine_readable,
            "open_format": open_format,
        },
        issues=list(inspection.issues),
    )
```

### Step 4: Run tests

```bash
uv run pytest tests/test_scorer.py -v
```

Expected: All PASS.

### Step 5: Commit

```bash
git add shared/scorer.py tests/test_scorer.py
git commit -m "feat: add scorer module with 5-Star scoring logic (★1-★3)"
```

---

## Task 6: Implement score_provider — orchestrate inspection + scoring for a provider

**Files:**
- Modify: `shared/scorer.py`
- Modify: `tests/test_scorer.py`

### Step 1: Write failing test

Append to `tests/test_scorer.py`:

```python
import json
from shared.scorer import score_provider


class TestScoreProvider:
    """score_provider reads manifest + datasets, writes scores.json."""

    def test_scores_json_output(self, tmp_path):
        # Set up a minimal provider directory
        pkg_dir = tmp_path / "test_provider"
        pkg_dir.mkdir()

        manifest = {
            "provider": "測試機關",
            "slug": "test_provider",
            "datasets": [
                {"id": "1001", "name": "CSV Data", "format": "csv", "urls": ["http://x"]},
                {"id": "1002", "name": "PDF Report", "format": "pdf", "urls": ["http://y"]},
            ],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))

        datasets_dir = pkg_dir / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_text("a,b\n1,2\n")
        (datasets_dir / "1002.pdf").write_bytes(b"%PDF-1.4 content")

        score_provider(pkg_dir)

        scores_path = pkg_dir / "scores.json"
        assert scores_path.exists()
        scores = json.loads(scores_path.read_text())

        assert scores["provider"] == "測試機關"
        assert scores["slug"] == "test_provider"
        assert "scored_at" in scores
        assert len(scores["datasets"]) == 2

        csv_score = next(d for d in scores["datasets"] if d["id"] == "1001")
        assert csv_score["star_score"] == 3

        pdf_score = next(d for d in scores["datasets"] if d["id"] == "1002")
        assert pdf_score["star_score"] == 1
        assert "PDF_DATASET" in pdf_score["issues"]
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_scorer.py::TestScoreProvider -v
```

Expected: FAIL — `ImportError: cannot import name 'score_provider'`

### Step 3: Implement score_provider

Add to `shared/scorer.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from shared.inspector import inspect_dataset


def score_provider(pkg_dir: Path) -> dict:
    """Score all datasets for a provider and write scores.json.

    Args:
        pkg_dir: Path to the provider package directory (containing manifest.json).

    Returns:
        The scores dict that was written to scores.json.
    """
    pkg_dir = Path(pkg_dir)
    manifest_path = pkg_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    datasets_dir = pkg_dir / "datasets"

    scored_datasets = []
    for dataset in manifest["datasets"]:
        inspection = inspect_dataset(dataset, datasets_dir)
        score = score_dataset(inspection)
        scored_datasets.append(score.to_dict())

    scores = {
        "provider": manifest["provider"],
        "slug": manifest["slug"],
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "datasets": scored_datasets,
    }

    scores_path = pkg_dir / "scores.json"
    scores_path.write_text(
        json.dumps(scores, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return scores
```

### Step 4: Run tests

```bash
uv run pytest tests/test_scorer.py -v
```

Expected: All PASS.

### Step 5: Commit

```bash
git add shared/scorer.py tests/test_scorer.py
git commit -m "feat: add score_provider to orchestrate scoring and write scores.json"
```

---

## Task 7: Add `score` CLI subcommand

**Files:**
- Modify: `shared/__main__.py`
- Create: `tests/test_score_cli.py`

### Step 1: Write failing test

Create `tests/test_score_cli.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from shared.__main__ import app

runner = CliRunner()


def _make_provider(tmp_path, slug="test_provider", datasets=None):
    """Create a minimal provider directory with manifest and datasets."""
    pkg_dir = tmp_path / slug
    pkg_dir.mkdir()
    if datasets is None:
        datasets = [{"id": "1001", "name": "Test", "format": "csv", "urls": ["http://x"]}]
    manifest = {"provider": "測試機關", "slug": slug, "datasets": datasets}
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "1001.csv").write_text("a,b\n1,2\n")
    return pkg_dir


def test_score_single_provider(tmp_path):
    pkg_dir = _make_provider(tmp_path)

    with patch("shared.__main__.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["score", str(pkg_dir)])

    assert result.exit_code == 0
    assert (pkg_dir / "scores.json").exists()
    scores = json.loads((pkg_dir / "scores.json").read_text())
    assert scores["datasets"][0]["star_score"] == 3


def test_score_all_providers(tmp_path):
    _make_provider(tmp_path, slug="provider_a")
    _make_provider(tmp_path, slug="provider_b")

    with patch("shared.__main__.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["score", "--all"], catch_exceptions=False)

    assert result.exit_code == 0
    assert (tmp_path / "provider_a" / "scores.json").exists()
    assert (tmp_path / "provider_b" / "scores.json").exists()
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_score_cli.py -v
```

Expected: FAIL — `No such command 'score'` or similar

### Step 3: Implement score subcommand

Modify `shared/__main__.py` — add the `score` command. The file currently has `list` and `scaffold`. Add:

```python
from shared.scorer import score_provider

@app.command("score")
def score(
    provider_dir: Path = typer.Argument(
        None, help="要評分的 provider 目錄路徑（例如 opdadm_moi_gov_tw）"
    ),
    all_providers: bool = typer.Option(
        False, "--all", help="評分所有有 manifest.json 的 provider"
    ),
) -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    if all_providers:
        cwd = Path.cwd()
        provider_dirs = sorted(
            p.parent for p in cwd.glob("*/manifest.json")
            if p.parent.name != "data_gov_tw"  # skip the portal itself
        )
        if not provider_dirs:
            print("找不到任何 provider 目錄")
            raise typer.Exit(1)
        for pkg_dir in provider_dirs:
            _score_one(pkg_dir)
    elif provider_dir is not None:
        _score_one(Path(provider_dir))
    else:
        print("請指定 provider 目錄或使用 --all")
        raise typer.Exit(1)


def _score_one(pkg_dir: Path) -> None:
    """Score a single provider and print summary."""
    scores = score_provider(pkg_dir)
    total = len(scores["datasets"])
    scored = [d for d in scores["datasets"] if d["star_score"] > 0]
    avg = sum(d["star_score"] for d in scored) / len(scored) if scored else 0
    print(f"✓ {scores['provider']} — {total} 筆資料集, 平均 {avg:.1f} 星")
```

### Step 4: Run tests

```bash
uv run pytest tests/test_score_cli.py -v
```

Expected: All PASS.

### Step 5: Run full test suite

```bash
uv run pytest -v
```

Expected: All tests pass (including existing tests).

### Step 6: Commit

```bash
git add shared/__main__.py tests/test_score_cli.py
git commit -m "feat: add 'score' CLI subcommand for dataset evaluation"
```

---

## Task 8: Add scores.json to .gitignore

**Files:**
- Modify: `.gitignore`

### Step 1: Check current .gitignore

Read `.gitignore` and verify `scores.json` is not already listed.

### Step 2: Add scores.json pattern

Add `**/scores.json` to `.gitignore` (same pattern as `**/datasets/`), since scores are generated locally and may differ between runs.

### Step 3: Commit

```bash
git add .gitignore
git commit -m "chore: gitignore scores.json (generated per-provider)"
```

---

## Task 9: Integration test with real opdadm data (optional, manual)

This task is **manual verification only** — no automated test needed because it depends on downloaded data being present.

### Step 1: Run scorer against opdadm

```bash
uv run python -m shared score opdadm_moi_gov_tw
```

Expected output: A summary line like `✓ 警政署 — 120 筆資料集, 平均 X.X 星`

### Step 2: Inspect scores.json

```bash
python -c "
import json
scores = json.load(open('opdadm_moi_gov_tw/scores.json'))
from collections import Counter
stars = Counter(d['star_score'] for d in scores['datasets'])
issues = Counter(i for d in scores['datasets'] for i in d['issues'])
print('Star distribution:', dict(sorted(stars.items())))
print('Issue distribution:', dict(sorted(issues.items())))
"
```

### Step 3: Sanity check

Verify that:
- CSV datasets → 3 stars
- PDF datasets → 1 star
- ZIP datasets → scored by contents
- Missing files → 0 stars
- `FORMAT_MISMATCH` issues appear where expected

---

## Summary

| Task | Module | What it does |
|------|--------|-------------|
| 1 | pyproject.toml | Add python-magic dependency |
| 2 | shared/inspector.py | Magic-bytes format detection |
| 3 | shared/inspector.py | ZIP content inspection |
| 4 | shared/inspector.py | Full dataset inspection with issue detection |
| 5 | shared/scorer.py | Star scoring logic (★0-★3) |
| 6 | shared/scorer.py | Provider-level scoring orchestration + scores.json output |
| 7 | shared/__main__.py | `score` CLI subcommand |
| 8 | .gitignore | Ignore generated scores.json |
| 9 | (manual) | Integration test with real opdadm data |

Total: 8 automated tasks + 1 manual verification. Each task is independently committable with passing tests.
