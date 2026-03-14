"""tw-odc CLI: Taiwan Open Data Checker."""

import asyncio
import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Optional

import typer

from tw_odc.i18n import setup_locale, t
from tw_odc.paths import data_dir, ensure_manifest
from tw_odc.manifest import (
    ManifestType,
    create_dataset_manifest,
    find_existing_providers,
    group_by_provider,
    load_manifest,
    parse_dataset,
    update_dataset_manifest,
)

app = typer.Typer(name="tw-odc")


class Lang(StrEnum):
    EN = "en"
    ZH_TW = "zh-TW"


@app.callback()
def main_callback(
    lang: Lang | None = typer.Option(None, "--lang", help="Language: en, zh-TW"),
) -> None:
    """Taiwan Open Data Checker CLI."""
    setup_locale(lang)


metadata_app = typer.Typer(help="Metadata source operations")
dataset_app = typer.Typer(help="Dataset operations")
config_app = typer.Typer(help="Configuration info")
app.add_typer(metadata_app, name="metadata")
app.add_typer(dataset_app, name="dataset")
app.add_typer(config_app, name="config")


def _get_version() -> str:
    """Get installed package version, or 'dev' if running from source."""
    try:
        from importlib.metadata import version
        return version("tw-odc")
    except Exception:
        return "dev"


def _has_local_metadata() -> bool:
    """Check if $PWD has a valid metadata manifest."""
    manifest_path = Path.cwd() / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("type") == "metadata"
    except (json.JSONDecodeError, OSError):
        return False


@config_app.command("show")
def config_show() -> None:
    """Show configuration and path info."""
    result = {
        "version": _get_version(),
        "metadata_dir": str(data_dir()),
        "cwd": str(Path.cwd()),
        "local_metadata": _has_local_metadata(),
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


@metadata_app.callback()
def metadata_callback(
    ctx: typer.Context,
    dir: Annotated[Optional[Path], typer.Option("--dir", help="Metadata 目錄路徑")] = None,
) -> None:
    """Metadata subcommand group."""
    ctx.ensure_object(dict)
    ctx.obj["metadata_dir"] = Path(dir) if dir else data_dir()


def _get_metadata_dir(ctx: typer.Context) -> Path:
    return ctx.obj["metadata_dir"]


class OutputFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


class ScoringMethod(StrEnum):
    FIVE_STARS = "5-stars"
    GOV_TW = "gov-tw"


def _load_and_check(manifest_dir: Path, expected_type: ManifestType) -> dict:
    """Load manifest and verify type matches expected."""
    manifest = load_manifest(manifest_dir)
    actual = manifest.get("type")
    if actual != expected_type:
        print(
            f"E001: {t('E001', expected=expected_type, actual=actual)}",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)
    return manifest


def _find_export_json(manifest: dict, manifest_dir: Path) -> Path:
    """Find the export-json file from a metadata manifest."""
    for ds in manifest["datasets"]:
        if ds["id"] == "export-json":
            filename = f"{ds['id']}.{ds['format']}"
            return manifest_dir / filename
    print(f"E002: {t('E002')}", file=sys.stderr)
    raise typer.Exit(code=1)


def _output(data, fmt: OutputFormat) -> None:
    """Write data to stdout in the requested format."""
    if fmt == OutputFormat.JSON:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("provider") or str(item)
                    extra = {k: v for k, v in item.items() if k not in ("name", "provider")}
                    parts = [name]
                    if "count" in extra:
                        parts.append(t("output.count_suffix", count=extra["count"]))
                    if "slug" in extra:
                        parts.append(f"[{extra['slug']}]")
                    print(" ".join(parts))
                else:
                    print(item)
        else:
            print(data)


# ─── metadata commands ───


@metadata_app.command("download")
def metadata_download(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    only: str | None = typer.Option(None, "--only", help="Download only this file"),
    all_formats: bool = typer.Option(False, "--all", help="Download all formats (default: JSON only)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
    date: str | None = typer.Option(None, "--date", help="Override {date} param (YYYY-MM-DD)"),
) -> None:
    """Download metadata files."""
    from tw_odc.fetcher import fetch_all

    if only and all_formats:
        print("Error: --only and --all are mutually exclusive", file=sys.stderr)
        raise typer.Exit(code=1)

    metadata_dir = _get_metadata_dir(ctx)
    ensure_manifest(metadata_dir)
    manifest = _load_and_check(metadata_dir, ManifestType.METADATA)

    # Filter to JSON-only by default (unless --only or --all)
    if not only and not all_formats:
        manifest = {
            **manifest,
            "datasets": [ds for ds in manifest["datasets"] if ds.get("format") == "json"],
        }

    param_overrides = {"date": date} if date else None
    asyncio.run(fetch_all(manifest, metadata_dir, only=only, no_cache=no_cache, cache_path=metadata_dir / "etags.json", param_overrides=param_overrides))

    # Rebuild search index if export-json.json exists
    export_json_path = metadata_dir / "export-json.json"
    if export_json_path.exists():
        from tw_odc.manifest import build_search_index
        build_search_index(metadata_dir)


@metadata_app.command("list")
def metadata_list(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """List all providers in metadata."""
    metadata_dir = _get_metadata_dir(ctx)
    manifest = _load_and_check(metadata_dir, ManifestType.METADATA)
    export_path = _find_export_json(manifest, metadata_dir)
    if not export_path.exists():
        print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    result = []
    for name, datasets in sorted(groups.items()):
        all_urls = [
            u.strip()
            for d in datasets
            for u in d["資料下載網址"].split(";")
            if u.strip()
        ]
        from tw_odc.manifest import compute_slug
        slug = compute_slug(name, all_urls)
        result.append({"provider": name, "slug": slug, "count": len(datasets)})

    _output(result, fmt)


@metadata_app.command("search")
def metadata_search(
    ctx: typer.Context,
    keywords: Annotated[list[str], typer.Argument(help="Search keywords (AND logic)")],
    field: Annotated[Optional[list[str]], typer.Option("--field", help="Restrict to field: provider, name, desc")] = None,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """Search datasets in metadata by keyword."""
    metadata_dir = _get_metadata_dir(ctx)
    index_path = metadata_dir / "export-search.jsonl"
    export_path = metadata_dir / "export-json.json"

    keywords_lower = [k.lower() for k in keywords]
    valid_fields = {"provider", "name", "desc"}
    if field:
        for f in field:
            if f not in valid_fields:
                print(f"Error: --field must be one of: {', '.join(sorted(valid_fields))}", file=sys.stderr)
                raise typer.Exit(code=1)

    results: list[dict] = []

    if index_path.exists():
        # Fast path: slim JSONL
        with open(index_path, encoding="utf-8") as fh:
            for line in fh:
                line_lower = line.lower()
                if not all(k in line_lower for k in keywords_lower):
                    continue
                entry = json.loads(line)
                if field:
                    haystack = " ".join(str(entry.get(f, "")) for f in field).lower()
                    if not all(k in haystack for k in keywords_lower):
                        continue
                results.append(entry)
    elif export_path.exists():
        # Fallback: full JSON parse
        data = json.loads(export_path.read_text(encoding="utf-8"))
        for ds in data:
            entry = {
                "id": ds.get("資料集識別碼", ""),
                "name": ds.get("資料集名稱", ""),
                "provider": ds.get("提供機關", ""),
                "desc": ds.get("資料集描述", ""),
                "format": ds.get("檔案格式", ""),
            }
            if field:
                haystack = " ".join(str(entry.get(f, "")) for f in field).lower()
            else:
                haystack = " ".join(str(v) for v in entry.values()).lower()
            if all(k in haystack for k in keywords_lower):
                results.append(entry)
    else:
        print(f"E009: {t('E009', path=metadata_dir)}", file=sys.stderr)
        raise typer.Exit(code=1)

    # Sort by provider, then id
    results.sort(key=lambda r: (str(r.get("provider", "")), str(r.get("id", ""))))

    print(t("search.count", count=len(results)), file=sys.stderr)
    _output(results, fmt)


@metadata_app.command("create")
def metadata_create(
    ctx: typer.Context,
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
) -> None:
    """Create a dataset manifest from metadata. Prints directory slug to stdout."""
    metadata_dir = _get_metadata_dir(ctx)
    manifest = _load_and_check(metadata_dir, ManifestType.METADATA)
    export_path = _find_export_json(manifest, metadata_dir)
    if not export_path.exists():
        print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if provider not in groups:
        print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(Path.cwd(), provider, groups[provider])
    print(slug)


@metadata_app.command("update")
def metadata_update(
    ctx: typer.Context,
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider name"),
    provider_dir: str | None = typer.Option(None, "--provider-dir", help="Target provider directory"),
) -> None:
    """Update an existing dataset manifest."""
    metadata_dir = _get_metadata_dir(ctx)
    manifest = _load_and_check(metadata_dir, ManifestType.METADATA)
    export_path = _find_export_json(manifest, metadata_dir)
    if not export_path.exists():
        print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if provider_dir:
        target_dir = Path.cwd() / provider_dir
        target_manifest = load_manifest(target_dir)
        provider = target_manifest["provider"]

    if not provider:
        print(f"E005: {t('E005')}", file=sys.stderr)
        raise typer.Exit(code=1)

    if provider not in groups:
        print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(Path.cwd(), provider, groups[provider])
    print(slug, file=sys.stderr)


@metadata_app.command("apply-daily")
def metadata_apply_daily(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    date: str | None = typer.Option(None, "--date", help="Date label for the output summary (YYYY-MM-DD); does not select a different input file"),
) -> None:
    """Apply daily changed datasets to existing provider manifests."""
    import datetime as _dt

    metadata_dir = _get_metadata_dir(ctx)
    _load_and_check(metadata_dir, ManifestType.METADATA)

    if not date:
        date = _dt.date.today().isoformat()

    daily_path = metadata_dir / "daily-changed-json.json"
    if not daily_path.exists():
        print(f"E107: {t('E107', path=daily_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(daily_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)
    providers = find_existing_providers(Path.cwd())

    updated: list[str] = []
    skipped: list[str] = []
    warnings: list[dict] = []

    for provider_name, datasets in sorted(groups.items()):
        # Check for deleted datasets
        has_deleted = any(d.get("資料集變動狀態") == "刪除" for d in datasets)
        if has_deleted:
            warnings.append({"provider": provider_name, "reason": "contains_deleted_datasets"})

        # Filter to non-deleted datasets
        active = [d for d in datasets if d.get("資料集變動狀態") != "刪除"]

        if provider_name not in providers:
            warnings.append({"provider": provider_name, "reason": "no_local_manifest"})
            continue

        if not active:
            pkg_dir = providers[provider_name]
            skipped.append(pkg_dir.name)
            continue

        pkg_dir = providers[provider_name]
        parsed = [parse_dataset(d) for d in active]
        count = update_dataset_manifest(pkg_dir, parsed)
        if count > 0:
            updated.append(pkg_dir.name)
        else:
            skipped.append(pkg_dir.name)

    result = {
        "date": date,
        "updated": updated,
        "skipped": skipped,
        "warnings": warnings,
    }
    _output(result, fmt)


# ─── dataset commands ───

_dataset_dir_option = typer.Option(None, "--dir", help="Dataset directory path")


@dataset_app.callback()
def dataset_callback(
    ctx: typer.Context,
    dir_path: str | None = _dataset_dir_option,
) -> None:
    """Shared --dir option for dataset commands."""
    ctx.ensure_object(dict)
    if dir_path:
        ctx.obj["dir"] = Path.cwd() / dir_path
    else:
        ctx.obj["dir"] = Path.cwd()


def _get_dataset_dir(ctx: typer.Context) -> Path:
    return ctx.obj["dir"]


@dataset_app.command("list")
def dataset_list(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """List datasets in a dataset manifest."""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    _output(manifest["datasets"], fmt)


@dataset_app.command("download")
def dataset_download(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="Download only this dataset ID"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
) -> None:
    """Download datasets."""
    from tw_odc.fetcher import fetch_all

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    output_dir = pkg_dir / "datasets"

    dl_manifest = manifest
    if dataset_id:
        filtered = [ds for ds in manifest["datasets"] if str(ds["id"]) == dataset_id]
        if not filtered:
            print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)
            raise typer.Exit(code=1)
        dl_manifest = {**manifest, "datasets": filtered}

    asyncio.run(fetch_all(dl_manifest, output_dir, no_cache=no_cache, cache_path=pkg_dir / "etags.json"))


@dataset_app.command("check")
def dataset_check(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="Check only this dataset ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """Check downloaded datasets."""
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

    results = []
    for ds in targets:
        result = inspect_dataset(ds, datasets_dir)
        results.append({
            "id": result.dataset_id,
            "name": result.dataset_name,
            "declared_format": result.declared_format,
            "detected_formats": result.detected_formats,
            "file_exists": result.file_exists,
            "file_empty": result.file_empty,
            "issues": result.issues,
        })

    _output(results, fmt)


def _load_export_json_lookup() -> dict[str, dict]:
    """Load export-json.json from metadata dir and build a lookup by dataset ID.

    Returns empty dict if file not found (graceful degradation).
    """
    metadata_dir = data_dir()
    root_manifest_path = metadata_dir / "manifest.json"
    if not root_manifest_path.exists():
        print(f"W001: {t('W001')}", file=sys.stderr)
        return {}

    export_path = metadata_dir / "export-json.json"
    if not export_path.exists():
        print(f"W002: {t('W002')}", file=sys.stderr)
        return {}

    data = json.loads(export_path.read_text(encoding="utf-8"))
    return {str(d["資料集識別碼"]): d for d in data}


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


@dataset_app.command("view")
def dataset_view(
    ctx: typer.Context,
    dataset_id: str = typer.Option(..., "--id", help="Dataset ID to view"),
) -> None:
    """Output raw dataset file content to stdout."""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    matched = [ds for ds in manifest["datasets"] if str(ds["id"]) == dataset_id]
    if not matched:
        print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)
        raise typer.Exit(code=1)

    from tw_odc.fetcher import _dest_filename

    ds = matched[0]
    url_count = len(ds["urls"])
    found_any = False

    datasets_dir_resolved = datasets_dir.resolve()
    for i in range(url_count):
        try:
            filename = _dest_filename(ds, i, url_count)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            raise typer.Exit(code=1)
        file_path = (datasets_dir / filename).resolve()
        try:
            file_path.relative_to(datasets_dir_resolved)
        except ValueError:
            print(f"Destination path escapes datasets directory: {filename}", file=sys.stderr)
            raise typer.Exit(code=1)

        if not file_path.exists():
            continue

        found_any = True
        if url_count > 1:
            print(f"--- {filename} ---", file=sys.stderr)
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sys.stdout.buffer.write(chunk)

    if not found_any:
        print(f"E008: {t('E008', id=dataset_id)}", file=sys.stderr)
        raise typer.Exit(code=1)


@dataset_app.command("clean")
def dataset_clean(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="Clean only this dataset ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """Clean downloaded files."""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)

    if dataset_id:
        from tw_odc.fetcher import clean_dataset

        matched = [ds for ds in manifest["datasets"] if str(ds["id"]) == dataset_id]
        if not matched:
            print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)
            raise typer.Exit(code=1)
        urls = matched[0].get("urls", [])
        removed = clean_dataset(pkg_dir, dataset_id, urls)
        _output({"removed": removed}, fmt)
    else:
        from tw_odc.fetcher import clean
        removed = clean(pkg_dir)
        _output({"removed": removed}, fmt)
