"""Score datasets using the 5-Star Open Data model (★1-★3 for v1)."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from shared.inspector import InspectionResult, inspect_dataset

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
    detected_format: str
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
