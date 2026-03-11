"""Score datasets using the gov-tw quality indicators.

Implements 6 of 7 indicators from 數位發展部「政府資料品質提升機制運作指引」.
Indicator 7 (民眾回饋意見之回復效率) requires manual review and is not included.
"""

from dataclasses import dataclass, field
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
