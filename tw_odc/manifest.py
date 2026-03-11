"""Manifest loading, writing, and RFC 6902 patch support."""

import hashlib
import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

import jsonpatch

from tw_odc import FORMAT_ALIASES


class ManifestType(StrEnum):
    METADATA = "metadata"
    DATASET = "dataset"


def load_manifest(manifest_dir: Path) -> dict:
    """Load manifest.json from a directory, applying patch.json if present.

    Raises FileNotFoundError if manifest.json does not exist.
    """
    manifest_path = manifest_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {manifest_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    patch_path = manifest_dir / "patch.json"
    if patch_path.exists():
        patch_ops = json.loads(patch_path.read_text(encoding="utf-8"))
        manifest = jsonpatch.apply_patch(manifest, patch_ops)

    return manifest


def derive_slug(urls: list[str]) -> str:
    """Derive a Python-safe directory name from a list of URLs."""
    if not urls:
        return ""
    domains: list[str] = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            netloc = urlparse(url).netloc.split(":")[0]
            if netloc.startswith("www."):
                netloc = netloc[4:]
            if netloc:
                domains.append(netloc)
        except Exception:
            continue
    if not domains:
        return ""
    most_common = Counter(domains).most_common(1)[0][0]
    return most_common.replace(".", "_").replace("-", "_")


def compute_slug(provider_name: str, urls: list[str]) -> str:
    """Return the slug for a provider: <domain>_<hash8> or org_<hash16> fallback."""
    h = hashlib.sha256(provider_name.encode("utf-8")).hexdigest()
    slug = derive_slug(urls)
    if not slug:
        return f"org_{h[:16]}"
    return f"{slug}_{h[:8]}"


def group_by_provider(datasets: list[dict]) -> dict[str, list[dict]]:
    """Group raw export.json entries by provider name (提供機關)."""
    groups: dict[str, list[dict]] = {}
    for d in datasets:
        provider = d["提供機關"]
        groups.setdefault(provider, []).append(d)
    return groups


def parse_dataset(raw: dict) -> dict:
    """Convert a raw export.json entry to manifest dataset format."""
    raw_urls = raw.get("資料下載網址") or ""
    urls = [u.strip() for u in raw_urls.split(";") if u.strip()]
    raw_fmt = raw.get("檔案格式") or ""
    formats = [f.strip() for f in raw_fmt.split(";") if f.strip()]
    fmt = formats[0].lower() if formats else "bin"
    fmt = FORMAT_ALIASES.get(fmt, fmt)
    return {
        "id": str(raw["資料集識別碼"]),
        "name": raw["資料集名稱"],
        "format": fmt,
        "urls": urls,
    }


def create_dataset_manifest(
    base_dir: Path, provider_name: str, raw_datasets: list[dict]
) -> str:
    """Create or update a dataset manifest.json under base_dir/<slug>/. Returns slug."""
    all_urls = [
        u.strip()
        for d in raw_datasets
        for u in d["資料下載網址"].split(";")
        if u.strip()
    ]
    slug = compute_slug(provider_name, all_urls)
    pkg_dir = base_dir / slug
    pkg_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "type": ManifestType.DATASET,
        "provider": provider_name,
        "slug": slug,
        "datasets": [parse_dataset(d) for d in raw_datasets],
    }
    (pkg_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return slug


def find_existing_providers(base_dir: Path) -> dict[str, Path]:
    """Scan subdirectories for dataset manifests. Returns {provider_name: dir_path}."""
    providers: dict[str, Path] = {}
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if m.get("type") == ManifestType.DATASET and m.get("provider"):
            providers[m["provider"]] = child
    return providers


def update_dataset_manifest(pkg_dir: Path, changed_datasets: list[dict]) -> int:
    """Incrementally merge changed datasets into an existing manifest. Returns count of changes."""
    if not changed_datasets:
        return 0
    manifest_path = pkg_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    existing = {str(d["id"]): d for d in manifest["datasets"]}
    count = 0
    for ds in changed_datasets:
        ds_id = str(ds["id"])
        if existing.get(ds_id) != ds:
            existing[ds_id] = ds
            count += 1

    if count > 0:
        manifest["datasets"] = list(existing.values())
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return count
