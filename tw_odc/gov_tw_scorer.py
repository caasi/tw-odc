"""Score datasets using the gov-tw quality indicators.

Implements 6 of 7 indicators from 數位發展部「政府資料品質提升機制運作指引」.
Indicator 7 (民眾回饋意見之回復效率) requires manual review and is not included.
"""

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import chardet

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
        file_path = datasets_dir / f"{inspection.dataset_id}.{inspection.declared_format}"
        if not file_path.exists():
            file_path = None

    # Indicators 4-6 require metadata; skip if not provided
    encoding_match: bool | None = None
    fields_match: bool | None = None
    update_timeliness: bool | None = None

    if metadata is not None:
        # Indicator 4: encoding match (text structured only)
        if structured and primary_fmt in _TEXT_STRUCTURED_FORMATS and file_path:
            encoding_match = check_encoding_match(file_path, meta.get("編碼格式", ""))

        # Indicator 5: fields match
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
