"""Inspect downloaded dataset files to detect actual formats."""

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import magic as _magic
except ImportError:
    _magic = None  # type: ignore[assignment]
    _magic_import_error_msg = (
        "python-magic requires the system libmagic library. "
        "Install it with: apt-get install libmagic1  (Debian/Ubuntu) "
        "or brew install libmagic  (macOS)."
    )
else:
    _magic_import_error_msg = ""

# Number of bytes to read from ZIP members for magic-byte detection.
_MAGIC_BUFFER_SIZE = 4096


def _ensure_magic() -> None:
    """Raise ImportError with install guidance if libmagic is unavailable."""
    if _magic is None:
        raise ImportError(_magic_import_error_msg)

# Safe-character patterns (same as fetcher.py) to prevent path traversal.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_SAFE_FMT_RE = re.compile(r"^\w+$")

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

    _ensure_magic()
    mime = _magic.from_file(str(file_path), mime=True)

    # ZIP-based formats need further inspection
    if mime in ("application/zip", "application/x-zip-compressed"):
        return _classify_zip(file_path)

    return _MIME_TO_FORMAT.get(mime, mime.split("/")[-1])


def _classify_zip(file_path: Path) -> str:
    """Distinguish ZIP from XLSX/KMZ by inspecting archive contents."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            if any(n.startswith("xl/") for n in names):
                return "xlsx"
            if any(n.endswith(".kml") for n in names):
                return "kmz"
            return "zip"
    except (zipfile.BadZipFile, OSError):
        return "zip"


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
            for info in zf.infolist():
                if info.is_dir():
                    continue
                with zf.open(info) as member:
                    # Read a small buffer for magic-byte detection
                    buf = member.read(_MAGIC_BUFFER_SIZE)
                if not buf:
                    formats.append("empty")
                    continue
                _ensure_magic()
                mime = _magic.from_buffer(buf, mime=True)
                if mime in ("application/zip", "application/x-zip-compressed"):
                    # Do not recurse into nested ZIPs
                    formats.append("zip")
                else:
                    fmt = _MIME_TO_FORMAT.get(mime, mime.split("/")[-1])
                    formats.append(fmt)
            return formats
    except (zipfile.BadZipFile, OSError):
        return []


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
    declared_fmt = (dataset["format"] or "bin").lower()
    format_undeclared = dataset["format"] is None
    urls = dataset["urls"]
    url_count = len(urls)

    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(declared_fmt):
        raise ValueError(f"Unsafe dataset format: {declared_fmt!r}")

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
            detected_formats.extend(contents if contents else ["zip"])
        else:
            detected_formats.append(fmt)

    # Classify issues
    if not any_exists:
        issues.append("DOWNLOAD_FAILED")
    if any_empty:
        issues.append("EMPTY_FILE")

    # Format mismatch: declared vs detected (skip for ZIP and undeclared formats)
    if not format_undeclared and declared_fmt != "zip" and any_exists:
        for fmt in detected_formats:
            if fmt not in ("missing", "empty") and fmt != declared_fmt:
                issues.append("FORMAT_MISMATCH")
                break

    if format_undeclared:
        issues.append("FORMAT_UNDECLARED")

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
