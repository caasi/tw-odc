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
