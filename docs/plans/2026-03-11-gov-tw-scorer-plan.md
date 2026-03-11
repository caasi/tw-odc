# gov-tw Quality Scorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--method gov-tw` option to `dataset score` that evaluates 6 quality indicators from the 政府資料品質提升機制運作指引.

**Architecture:** New `tw_odc/gov_tw_scorer.py` module with `GovTwScore` dataclass and `gov_tw_score_dataset()` function. CLI `dataset score` gets a `--method` enum option (default `5-stars`). The gov-tw method requires export-json metadata for encoding, field descriptions, and update frequency checks. New dependency: `chardet` for encoding detection.

**Tech Stack:** Python 3.13, chardet (new dep), existing inspector/fetcher/cli

---

### Task 1: Add chardet dependency

**Files:**
- Modify: `pyproject.toml:7-14`

**Step 1: Add chardet to dependencies**

```bash
uv add chardet
```

**Step 2: Verify install**

Run: `uv run python -c "import chardet; print(chardet.__version__)"`
Expected: version string printed

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add chardet dependency for encoding detection"
```

---

### Task 2: GovTwScore dataclass and basic indicator functions

**Files:**
- Create: `tw_odc/gov_tw_scorer.py`
- Create: `tests/test_gov_tw_scorer.py`

**Step 1: Write failing tests for indicators 1-3**

Create `tests/test_gov_tw_scorer.py`:

```python
"""Tests for gov-tw quality scoring method."""

from tw_odc.gov_tw_scorer import (
    GovTwScore,
    check_link_valid,
    check_direct_download,
    check_structured,
)
from tw_odc.inspector import InspectionResult


class TestCheckLinkValid:
    def test_existing_file_is_valid(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        assert check_link_valid(inspection) is True

    def test_missing_file_is_invalid(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
        )
        assert check_link_valid(inspection) is False


class TestCheckDirectDownload:
    def test_existing_csv_is_downloadable(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        assert check_direct_download(inspection) is True

    def test_html_response_is_not_downloadable(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["html"],
            file_exists=True, file_empty=False,
        )
        assert check_direct_download(inspection) is False

    def test_missing_file_is_not_downloadable(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
        )
        assert check_direct_download(inspection) is False


class TestCheckStructured:
    def test_csv_is_structured(self):
        assert check_structured(["csv"]) is True

    def test_json_is_structured(self):
        assert check_structured(["json"]) is True

    def test_xml_is_structured(self):
        assert check_structured(["xml"]) is True

    def test_xlsx_is_structured(self):
        assert check_structured(["xlsx"]) is True

    def test_geojson_is_structured(self):
        assert check_structured(["geojson"]) is True

    def test_pdf_is_not_structured(self):
        assert check_structured(["pdf"]) is False

    def test_missing_is_not_structured(self):
        assert check_structured(["missing"]) is False

    def test_mixed_uses_intersection(self):
        """If any format is unstructured, result is False (intersection rule)."""
        assert check_structured(["csv", "pdf"]) is False

    def test_all_structured(self):
        assert check_structured(["csv", "json"]) is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gov_tw_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tw_odc.gov_tw_scorer'`

**Step 3: Write minimal implementation**

Create `tw_odc/gov_tw_scorer.py`:

```python
"""Score datasets using the gov-tw quality indicators.

Implements 6 of 7 indicators from 數位發展部「政府資料品質提升機制運作指引」.
Indicator 7 (民眾回饋意見之回復效率) requires manual review and is not included.
"""

from dataclasses import dataclass, field

from tw_odc.inspector import InspectionResult

# Formats considered structured per the guideline
STRUCTURED_FORMATS = {"csv", "json", "xml", "geojson", "xlsx", "xls", "kmz", "kml", "shp"}


def check_link_valid(inspection: InspectionResult) -> bool:
    """Indicator 1: 連結有效性 — resource URL returns success status."""
    return inspection.file_exists


def check_direct_download(inspection: InspectionResult) -> bool:
    """Indicator 2: 資料可直接下載 — URL directly downloads data without login."""
    if not inspection.file_exists:
        return False
    # If detected format is HTML, likely a login/redirect page
    return "html" not in inspection.detected_formats


def check_structured(detected_formats: list[str]) -> bool:
    """Indicator 3: 結構化檔案類型 — intersection rule: all must be structured."""
    real = [f for f in detected_formats if f not in ("missing", "empty")]
    if not real:
        return False
    return all(f in STRUCTURED_FORMATS for f in real)


@dataclass
class GovTwScore:
    """Scoring result for a single dataset using gov-tw indicators."""

    dataset_id: str
    dataset_name: str
    link_valid: bool
    direct_download: bool
    structured: bool
    encoding_match: bool | None
    fields_match: bool | None
    update_timeliness: bool | None
    issues: list[str] = field(default_factory=list)

    @property
    def indicators(self) -> dict[str, bool | None]:
        return {
            "link_valid": self.link_valid,
            "direct_download": self.direct_download,
            "structured": self.structured,
            "encoding_match": self.encoding_match,
            "fields_match": self.fields_match,
            "update_timeliness": self.update_timeliness,
        }

    @property
    def pass_count(self) -> int:
        return sum(1 for v in self.indicators.values() if v is True)

    @property
    def total_count(self) -> int:
        return sum(1 for v in self.indicators.values() if v is not None)

    def to_dict(self) -> dict:
        return {
            "id": self.dataset_id,
            "name": self.dataset_name,
            "method": "gov-tw",
            "indicators": self.indicators,
            "pass_count": self.pass_count,
            "total_count": self.total_count,
            "issues": self.issues,
        }
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_gov_tw_scorer.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/gov_tw_scorer.py tests/test_gov_tw_scorer.py
git commit -m "feat: add gov-tw scorer with indicators 1-3 (link, download, structured)"
```

---

### Task 3: Indicator 4 — encoding match

**Files:**
- Modify: `tw_odc/gov_tw_scorer.py`
- Modify: `tests/test_gov_tw_scorer.py`

**Step 1: Write failing tests**

Add to `tests/test_gov_tw_scorer.py`:

```python
from tw_odc.gov_tw_scorer import check_encoding_match


class TestCheckEncodingMatch:
    def test_utf8_file_matches_utf8_metadata(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("名稱,數值\n測試,1\n", encoding="utf-8")
        assert check_encoding_match(f, "UTF-8") is True

    def test_utf8_file_with_empty_metadata_passes(self, tmp_path):
        """Empty encoding metadata → just check if UTF-8."""
        f = tmp_path / "data.csv"
        f.write_text("名稱,數值\n測試,1\n", encoding="utf-8")
        assert check_encoding_match(f, "") is True

    def test_big5_file_matches_big5_metadata(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes("名稱,數值\n測試,1\n".encode("big5"))
        assert check_encoding_match(f, "BIG5") is True

    def test_big5_file_does_not_match_utf8_metadata(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes("名稱,數值\n測試,1\n".encode("big5"))
        assert check_encoding_match(f, "UTF-8") is False

    def test_missing_file_returns_none(self, tmp_path):
        f = tmp_path / "nonexistent.csv"
        assert check_encoding_match(f, "UTF-8") is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestCheckEncodingMatch -v`
Expected: FAIL with `ImportError: cannot import name 'check_encoding_match'`

**Step 3: Implement check_encoding_match**

Add to `tw_odc/gov_tw_scorer.py`:

```python
from pathlib import Path

import chardet

_ENCODING_BUFFER_SIZE = 8192

# Mapping from metadata encoding names to chardet-compatible names
_ENCODING_ALIASES: dict[str, set[str]] = {
    "UTF-8": {"utf-8", "ascii", "utf-8-sig"},
    "BIG5": {"big5", "big5hkscs", "cp950"},
}


def _normalize_encoding(detected: str) -> str:
    """Normalize a chardet encoding name to uppercase canonical form."""
    detected_lower = detected.lower().replace("-", "").replace("_", "")
    for canonical, aliases in _ENCODING_ALIASES.items():
        normalized_aliases = {a.lower().replace("-", "").replace("_", "") for a in aliases}
        if detected_lower in normalized_aliases or detected_lower == canonical.lower().replace("-", ""):
            return canonical
    return detected.upper()


def check_encoding_match(file_path: Path, declared_encoding: str) -> bool | None:
    """Indicator 4: 編碼描述與資料相符.

    Returns True if detected encoding matches declared, False if mismatch,
    None if file is missing or detection fails.
    """
    if not file_path.exists():
        return None
    buf = file_path.read_bytes()[:_ENCODING_BUFFER_SIZE]
    if not buf:
        return None
    result = chardet.detect(buf)
    detected = result.get("encoding")
    if not detected:
        return None
    normalized = _normalize_encoding(detected)
    if not declared_encoding or not declared_encoding.strip():
        # No declared encoding → pass if UTF-8 (guideline recommends UTF-8)
        return normalized == "UTF-8"
    declared_upper = declared_encoding.strip().upper().replace("-", "").replace("_", "")
    canonical_declared = None
    for canonical, aliases in _ENCODING_ALIASES.items():
        normalized_aliases = {a.lower().replace("-", "").replace("_", "") for a in aliases}
        if declared_upper.lower() in normalized_aliases or declared_upper == canonical.upper().replace("-", ""):
            canonical_declared = canonical
            break
    if canonical_declared is None:
        canonical_declared = declared_encoding.strip().upper()
    return normalized == canonical_declared
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestCheckEncodingMatch -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/gov_tw_scorer.py tests/test_gov_tw_scorer.py
git commit -m "feat: add encoding match indicator (gov-tw indicator 4)"
```

---

### Task 4: Indicator 5 — fields match

**Files:**
- Modify: `tw_odc/gov_tw_scorer.py`
- Modify: `tests/test_gov_tw_scorer.py`

**Step 1: Write failing tests**

Add to `tests/test_gov_tw_scorer.py`:

```python
from tw_odc.gov_tw_scorer import check_fields_match, parse_field_description


class TestParseFieldDescription:
    def test_fullwidth_separator(self):
        assert parse_field_description("名稱、數值、日期") == ["名稱", "數值", "日期"]

    def test_comma_separator(self):
        assert parse_field_description("名稱,數值,日期") == ["名稱", "數值", "日期"]

    def test_empty_string(self):
        assert parse_field_description("") == []

    def test_none(self):
        assert parse_field_description(None) == []

    def test_strips_whitespace(self):
        assert parse_field_description(" 名稱 、 數值 ") == ["名稱", "數值"]


class TestCheckFieldsMatch:
    def test_csv_all_fields_present(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("名稱,數值,日期\na,1,2026-01-01\n", encoding="utf-8")
        assert check_fields_match(f, "csv", "名稱、數值、日期") is True

    def test_csv_missing_field(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("名稱,數值\na,1\n", encoding="utf-8")
        assert check_fields_match(f, "csv", "名稱、數值、日期") is False

    def test_json_all_fields_present(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[{"名稱": "a", "數值": 1}]', encoding="utf-8")
        assert check_fields_match(f, "json", "名稱、數值") is True

    def test_json_missing_field(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[{"名稱": "a"}]', encoding="utf-8")
        assert check_fields_match(f, "json", "名稱、數值") is False

    def test_empty_field_description_returns_none(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n", encoding="utf-8")
        assert check_fields_match(f, "csv", "") is None

    def test_pdf_returns_none(self, tmp_path):
        f = tmp_path / "data.pdf"
        f.write_bytes(b"%PDF-1.4")
        assert check_fields_match(f, "pdf", "名稱、數值") is None

    def test_missing_file_returns_none(self, tmp_path):
        f = tmp_path / "nonexistent.csv"
        assert check_fields_match(f, "csv", "名稱、數值") is None

    def test_xml_all_fields_present(self, tmp_path):
        f = tmp_path / "data.xml"
        f.write_text('<?xml version="1.0"?><root><row><名稱>a</名稱><數值>1</數值></row></root>', encoding="utf-8")
        assert check_fields_match(f, "xml", "名稱、數值") is True

    def test_xml_missing_field(self, tmp_path):
        f = tmp_path / "data.xml"
        f.write_text('<?xml version="1.0"?><root><row><名稱>a</名稱></row></root>', encoding="utf-8")
        assert check_fields_match(f, "xml", "名稱、數值") is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestParseFieldDescription tests/test_gov_tw_scorer.py::TestCheckFieldsMatch -v`
Expected: FAIL with `ImportError`

**Step 3: Implement**

Add to `tw_odc/gov_tw_scorer.py`:

```python
import csv
import io
import json
import xml.etree.ElementTree as ET

# Formats that support field matching
_FIELD_MATCH_FORMATS = {"csv", "json", "xml"}


def parse_field_description(description: str | None) -> list[str]:
    """Parse 「主要欄位說明」 into a list of expected field names.

    Handles full-width separator「、」and comma separator.
    """
    if not description or not description.strip():
        return []
    # Replace full-width comma with regular comma, then split
    text = description.replace("、", ",")
    return [f.strip() for f in text.split(",") if f.strip()]


def check_fields_match(file_path: Path, fmt: str, field_description: str | None) -> bool | None:
    """Indicator 5: 欄位描述與資料相符.

    Returns True if all expected fields are found, False if any missing,
    None if not applicable (non-structured, empty description, missing file).
    """
    expected = parse_field_description(field_description)
    if not expected:
        return None
    if fmt not in _FIELD_MATCH_FORMATS:
        return None
    if not file_path.exists():
        return None

    try:
        actual_fields = _extract_fields(file_path, fmt)
    except Exception:
        return None

    if not actual_fields:
        return None

    return all(f in actual_fields for f in expected)


def _extract_fields(file_path: Path, fmt: str) -> set[str]:
    """Extract field names from a data file."""
    content = file_path.read_bytes()
    if fmt == "csv":
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        return set(h.strip() for h in header) if header else set()
    elif fmt == "json":
        data = json.loads(content)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return set(data[0].keys())
        elif isinstance(data, dict):
            return set(data.keys())
        return set()
    elif fmt == "xml":
        root = ET.fromstring(content)
        elements: set[str] = set()
        for elem in root.iter():
            if elem.tag:
                elements.add(elem.tag)
        return elements
    return set()
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestParseFieldDescription tests/test_gov_tw_scorer.py::TestCheckFieldsMatch -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/gov_tw_scorer.py tests/test_gov_tw_scorer.py
git commit -m "feat: add fields match indicator (gov-tw indicator 5)"
```

---

### Task 5: Indicator 6 — update timeliness

**Files:**
- Modify: `tw_odc/gov_tw_scorer.py`
- Modify: `tests/test_gov_tw_scorer.py`

**Step 1: Write failing tests**

Add to `tests/test_gov_tw_scorer.py`:

```python
import datetime
from tw_odc.gov_tw_scorer import check_update_timeliness, parse_update_frequency


class TestParseUpdateFrequency:
    def test_daily(self):
        assert parse_update_frequency("每1日") == datetime.timedelta(days=1)

    def test_monthly(self):
        assert parse_update_frequency("每1月") == datetime.timedelta(days=30)

    def test_yearly(self):
        assert parse_update_frequency("每1年") == datetime.timedelta(days=365)

    def test_every_3_months(self):
        assert parse_update_frequency("每3月") == datetime.timedelta(days=90)

    def test_hourly(self):
        assert parse_update_frequency("每1時") == datetime.timedelta(hours=1)

    def test_every_30_minutes(self):
        assert parse_update_frequency("每30分") == datetime.timedelta(minutes=30)

    def test_irregular_returns_none(self):
        assert parse_update_frequency("不定期更新") is None

    def test_empty_returns_none(self):
        assert parse_update_frequency("") is None

    def test_unknown_format_returns_none(self):
        assert parse_update_frequency("隨時") is None


class TestCheckUpdateTimeliness:
    def test_within_interval(self):
        now = datetime.datetime(2026, 3, 11, tzinfo=datetime.timezone.utc)
        last_update = "2026-03-10 12:00:00.000000"
        assert check_update_timeliness("每1日", last_update, now=now) is True

    def test_overdue(self):
        now = datetime.datetime(2026, 3, 11, tzinfo=datetime.timezone.utc)
        last_update = "2026-01-01 00:00:00.000000"
        assert check_update_timeliness("每1日", last_update, now=now) is False

    def test_irregular_returns_none(self):
        assert check_update_timeliness("不定期更新", "2026-01-01 00:00:00.000000") is None

    def test_empty_frequency_returns_none(self):
        assert check_update_timeliness("", "2026-01-01 00:00:00.000000") is None

    def test_empty_last_update_returns_none(self):
        assert check_update_timeliness("每1日", "") is None

    def test_monthly_within_interval(self):
        now = datetime.datetime(2026, 3, 11, tzinfo=datetime.timezone.utc)
        last_update = "2026-03-01 00:00:00.000000"
        assert check_update_timeliness("每1月", last_update, now=now) is True

    def test_monthly_overdue(self):
        now = datetime.datetime(2026, 3, 11, tzinfo=datetime.timezone.utc)
        last_update = "2025-12-01 00:00:00.000000"
        assert check_update_timeliness("每1月", last_update, now=now) is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestParseUpdateFrequency tests/test_gov_tw_scorer.py::TestCheckUpdateTimeliness -v`
Expected: FAIL with `ImportError`

**Step 3: Implement**

Add to `tw_odc/gov_tw_scorer.py`:

```python
import re
from datetime import datetime, timedelta, timezone

_FREQ_PATTERN = re.compile(r"每(\d+)(分|時|日|月|年)")

_FREQ_UNITS: dict[str, str] = {
    "分": "minutes",
    "時": "hours",
    "日": "days",
    "月": "days",  # multiplied by 30
    "年": "days",  # multiplied by 365
}

_FREQ_MULTIPLIERS: dict[str, int] = {
    "分": 1,
    "時": 1,
    "日": 1,
    "月": 30,
    "年": 365,
}


def parse_update_frequency(frequency: str | None) -> timedelta | None:
    """Parse 「更新頻率」 into a timedelta.

    Returns None for irregular/unknown frequencies.
    """
    if not frequency or not frequency.strip():
        return None
    m = _FREQ_PATTERN.search(frequency)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    multiplier = _FREQ_MULTIPLIERS[unit]
    kwargs = {_FREQ_UNITS[unit]: n * multiplier}
    return timedelta(**kwargs)


def check_update_timeliness(
    frequency: str | None,
    last_update: str | None,
    now: datetime | None = None,
) -> bool | None:
    """Indicator 6: 資料更新時效性.

    Returns True if within expected interval, False if overdue, None if unknown.
    Adds a 1.5x grace period to the interval to allow reasonable delay.
    """
    interval = parse_update_frequency(frequency)
    if interval is None:
        return None
    if not last_update or not last_update.strip():
        return None
    try:
        update_time = datetime.strptime(
            last_update.strip()[:19], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    elapsed = now - update_time
    # 1.5x grace period
    return elapsed <= interval * 1.5
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestParseUpdateFrequency tests/test_gov_tw_scorer.py::TestCheckUpdateTimeliness -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/gov_tw_scorer.py tests/test_gov_tw_scorer.py
git commit -m "feat: add update timeliness indicator (gov-tw indicator 6)"
```

---

### Task 6: gov_tw_score_dataset orchestrator function

**Files:**
- Modify: `tw_odc/gov_tw_scorer.py`
- Modify: `tests/test_gov_tw_scorer.py`

**Step 1: Write failing tests**

Add to `tests/test_gov_tw_scorer.py`:

```python
from tw_odc.gov_tw_scorer import gov_tw_score_dataset


class TestGovTwScoreDataset:
    def test_full_pass_csv(self, tmp_path):
        """CSV dataset with matching metadata scores all True."""
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        f = datasets_dir / "1001.csv"
        f.write_text("名稱,數值\na,1\n", encoding="utf-8")

        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test CSV",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        metadata = {
            "編碼格式": "UTF-8",
            "主要欄位說明": "名稱、數值",
            "更新頻率": "每1月",
            "詮釋資料更新時間": "2026-03-10 00:00:00.000000",
        }
        score = gov_tw_score_dataset(inspection, metadata, datasets_dir)
        assert score.link_valid is True
        assert score.direct_download is True
        assert score.structured is True
        assert score.encoding_match is True
        assert score.fields_match is True
        assert score.pass_count >= 5
        d = score.to_dict()
        assert d["method"] == "gov-tw"

    def test_missing_file_all_false_or_none(self):
        """Missing file → link_valid=False, most others None."""
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
        )
        score = gov_tw_score_dataset(inspection, {}, None)
        assert score.link_valid is False
        assert score.direct_download is False
        assert score.structured is False
        assert score.pass_count == 0

    def test_no_metadata_returns_none_for_metadata_indicators(self, tmp_path):
        """Without metadata, encoding/fields/timeliness should be None."""
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        f = datasets_dir / "1001.csv"
        f.write_text("a,b\n1,2\n", encoding="utf-8")

        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        score = gov_tw_score_dataset(inspection, None, datasets_dir)
        assert score.link_valid is True
        assert score.encoding_match is None
        assert score.fields_match is None
        assert score.update_timeliness is None

    def test_pdf_not_structured(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.pdf").write_bytes(b"%PDF-1.4")

        inspection = InspectionResult(
            dataset_id="1001", dataset_name="PDF Report",
            declared_format="pdf", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
        )
        score = gov_tw_score_dataset(inspection, {}, datasets_dir)
        assert score.structured is False
        assert score.encoding_match is None  # non-structured → None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gov_tw_scorer.py::TestGovTwScoreDataset -v`
Expected: FAIL with `ImportError: cannot import name 'gov_tw_score_dataset'`

**Step 3: Implement**

Add to `tw_odc/gov_tw_scorer.py`:

```python
# Formats where encoding check is meaningful (text-based structured formats)
_TEXT_STRUCTURED_FORMATS = {"csv", "json", "xml"}


def gov_tw_score_dataset(
    inspection: InspectionResult,
    metadata: dict | None,
    datasets_dir: Path | None,
) -> GovTwScore:
    """Score a dataset using the gov-tw quality indicators.

    Args:
        inspection: InspectionResult from inspector.
        metadata: Raw export-json entry for this dataset (may be None).
        datasets_dir: Path to datasets/ directory (for reading file content).
    """
    meta = metadata or {}

    # Indicators 1-3: based on inspection only
    link_valid = check_link_valid(inspection)
    direct_download = check_direct_download(inspection)
    structured = check_structured(inspection.detected_formats)

    # Determine primary format and file path for content-based checks
    real_formats = [f for f in inspection.detected_formats if f not in ("missing", "empty")]
    primary_fmt = real_formats[0] if real_formats else None
    file_path = None
    if datasets_dir and primary_fmt:
        dataset_id = inspection.dataset_id
        urls_count = len([f for f in inspection.detected_formats])
        if urls_count == 1:
            file_path = datasets_dir / f"{dataset_id}.{inspection.declared_format}"
        else:
            file_path = datasets_dir / f"{dataset_id}.{inspection.declared_format}"
        if not file_path.exists():
            file_path = None

    # Indicator 4: encoding match (text structured only)
    encoding_match: bool | None = None
    if structured and primary_fmt in _TEXT_STRUCTURED_FORMATS and file_path:
        encoding_match = check_encoding_match(file_path, meta.get("編碼格式", ""))

    # Indicator 5: fields match
    fields_match: bool | None = None
    if structured and primary_fmt in _FIELD_MATCH_FORMATS and file_path:
        fields_match = check_fields_match(
            file_path, primary_fmt, meta.get("主要欄位說明", "")
        )

    # Indicator 6: update timeliness
    update_timeliness = check_update_timeliness(
        meta.get("更新頻率", ""),
        meta.get("詮釋資料更新時間", ""),
    )

    return GovTwScore(
        dataset_id=inspection.dataset_id,
        dataset_name=inspection.dataset_name,
        link_valid=link_valid,
        direct_download=direct_download,
        structured=structured,
        encoding_match=encoding_match,
        fields_match=fields_match,
        update_timeliness=update_timeliness,
        issues=list(inspection.issues),
    )
```

**Step 4: Run ALL gov-tw scorer tests**

Run: `uv run pytest tests/test_gov_tw_scorer.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/gov_tw_scorer.py tests/test_gov_tw_scorer.py
git commit -m "feat: add gov_tw_score_dataset orchestrator function"
```

---

### Task 7: Add --method option to CLI dataset score

**Files:**
- Modify: `tw_odc/cli.py:288-315`
- Modify: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestDatasetScoreMethod:
    def test_default_method_is_five_stars(self, tmp_path, monkeypatch):
        """Without --method, score uses 5-stars (existing behavior)."""
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001.csv").write_text("a,b\n1,2\n")
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "score"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        # 5-stars output has star_score field
        assert "star_score" in data[0]

    def test_method_gov_tw(self, tmp_path, monkeypatch):
        """--method gov-tw outputs gov-tw indicators."""
        # Need root manifest + export-json for metadata lookup
        root = tmp_path
        root_manifest = {
            "type": "metadata", "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (root / "manifest.json").write_text(json.dumps(root_manifest))
        export_data = [
            {"資料集識別碼": "1001", "資料集名稱": "D", "提供機關": "T",
             "檔案格式": "CSV", "資料下載網址": "http://x",
             "編碼格式": "UTF-8", "主要欄位說明": "a、b",
             "更新頻率": "每1月", "詮釋資料更新時間": "2026-03-10 00:00:00.000000"},
        ]
        (root / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))

        pkg_dir = root / "t"
        pkg_dir.mkdir()
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001.csv").write_text("a,b\n1,2\n")
        monkeypatch.chdir(root)

        result = runner.invoke(app, ["dataset", "--dir", "t", "score", "--method", "gov-tw"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["method"] == "gov-tw"
        assert "indicators" in data[0]
        assert data[0]["indicators"]["link_valid"] is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestDatasetScoreMethod -v`
Expected: FAIL — `--method` option doesn't exist yet

**Step 3: Update CLI**

In `tw_odc/cli.py`, add `ScoringMethod` enum after `OutputFormat` and update `dataset_score`:

```python
class ScoringMethod(StrEnum):
    FIVE_STARS = "5-stars"
    GOV_TW = "gov-tw"
```

Replace the existing `dataset_score` function:

```python
@dataset_app.command("score")
def dataset_score(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="Score only this dataset ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    method: ScoringMethod = typer.Option(ScoringMethod.FIVE_STARS, "--method", help="Scoring method: 5-stars, gov-tw"),
) -> None:
    """Score downloaded datasets using the 5-Star model or gov-tw quality indicators."""
    from tw_odc.inspector import inspect_dataset

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    targets = manifest["datasets"]
    if dataset_id:
        targets = [ds for ds in targets if str(ds["id"]) == dataset_id]
        if not targets:
            print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)
            raise typer.Exit(code=1)

    if method == ScoringMethod.GOV_TW:
        from tw_odc.gov_tw_scorer import gov_tw_score_dataset

        # Load export-json metadata for gov-tw scoring
        metadata_lookup = _load_export_json_lookup()

        results = []
        for ds in targets:
            inspection = inspect_dataset(ds, datasets_dir)
            meta = metadata_lookup.get(str(ds["id"]))
            score = gov_tw_score_dataset(inspection, meta, datasets_dir)
            results.append(score.to_dict())
    else:
        from tw_odc.scorer import score_dataset

        results = []
        for ds in targets:
            inspection = inspect_dataset(ds, datasets_dir)
            score = score_dataset(inspection)
            results.append(score.to_dict())

    _output(results, fmt)
```

Add helper function `_load_export_json_lookup`:

```python
def _load_export_json_lookup() -> dict[str, dict]:
    """Load export-json.json from project root and build a lookup by dataset ID.

    Returns empty dict if file not found (graceful degradation).
    """
    # Walk up from cwd to find root manifest
    cwd = Path.cwd()
    root_manifest_path = cwd / "manifest.json"
    if not root_manifest_path.exists():
        # Try parent (if we're in a provider dir)
        root_manifest_path = cwd.parent / "manifest.json"
    if not root_manifest_path.exists():
        print(f"W001: {t('W001')}", file=sys.stderr)
        return {}

    root_dir = root_manifest_path.parent
    export_path = root_dir / "export-json.json"
    if not export_path.exists():
        print(f"W002: {t('W002')}", file=sys.stderr)
        return {}

    data = json.loads(export_path.read_text(encoding="utf-8"))
    return {str(d["資料集識別碼"]): d for d in data}
```

**Step 4: Run ALL tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tw_odc/cli.py tests/test_cli.py
git commit -m "feat: add --method option to dataset score (5-stars default, gov-tw)"
```

---

### Task 8: Add i18n warning keys and update CLAUDE.md

**Files:**
- Modify: `tw_odc/locales/en.json`
- Modify: `tw_odc/locales/zh-TW.json`
- Modify: `CLAUDE.md`

**Step 1: Add warning translation keys**

Add to `tw_odc/locales/en.json`:
```json
"W001": "Root manifest.json not found; gov-tw metadata indicators will be unavailable",
"W002": "export-json.json not found; run 'tw-odc metadata download' first"
```

Add to `tw_odc/locales/zh-TW.json`:
```json
"W001": "找不到根目錄 manifest.json；gov-tw 詮釋資料相關指標將無法使用",
"W002": "找不到 export-json.json；請先執行 'tw-odc metadata download'"
```

**Step 2: Update CLAUDE.md**

In the Commands section, add:
```bash
# Score with gov-tw quality indicators
tw-odc dataset --dir <provider_slug> score --method gov-tw
tw-odc dataset --dir <provider_slug> score --method gov-tw --id <dataset_id>
```

In Key Design Decisions, add:
- **Dual scoring**: `5-stars` (Tim Berners-Lee) and `gov-tw` (數位發展部品質指引) are independent scoring methods selectable via `--method`

**Step 3: Run all tests to verify nothing broke**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tw_odc/locales/en.json tw_odc/locales/zh-TW.json CLAUDE.md
git commit -m "docs: add gov-tw scoring to i18n and CLAUDE.md"
```
