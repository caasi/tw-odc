"""tw-odc CLI: Taiwan Open Data Checker."""

import asyncio
import json
import sys
from enum import StrEnum
from pathlib import Path

import typer

from tw_odc.i18n import setup_locale, t
from tw_odc.manifest import (
    ManifestType,
    create_dataset_manifest,
    group_by_provider,
    load_manifest,
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
app.add_typer(metadata_app, name="metadata")
app.add_typer(dataset_app, name="dataset")


class OutputFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


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
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    only: str | None = typer.Option(None, "--only", help="Download only this file"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
) -> None:
    """Download metadata files."""
    from tw_odc.fetcher import fetch_all

    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    asyncio.run(fetch_all(manifest, cwd, only=only, no_cache=no_cache, cache_path=cwd / "etags.json"))


@metadata_app.command("list")
def metadata_list(
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """List all providers in metadata."""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
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


@metadata_app.command("create")
def metadata_create(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
) -> None:
    """Create a dataset manifest from metadata. Prints directory slug to stdout."""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if provider not in groups:
        print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(cwd, provider, groups[provider])
    print(slug)


@metadata_app.command("update")
def metadata_update(
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider name"),
    dir_path: str | None = typer.Option(None, "--dir", help="Target directory"),
) -> None:
    """Update an existing dataset manifest."""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"E003: {t('E003', path=export_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if dir_path:
        target_dir = cwd / dir_path
        target_manifest = load_manifest(target_dir)
        provider = target_manifest["provider"]

    if not provider:
        print(f"E005: {t('E005')}", file=sys.stderr)
        raise typer.Exit(code=1)

    if provider not in groups:
        print(f"E004: {t('E004', provider=provider)}", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(cwd, provider, groups[provider])
    print(slug, file=sys.stderr)


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


@dataset_app.command("score")
def dataset_score(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="Score only this dataset ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """Score downloaded datasets using the 5-Star model."""
    from tw_odc.inspector import inspect_dataset
    from tw_odc.scorer import score_dataset

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
        inspection = inspect_dataset(ds, datasets_dir)
        score = score_dataset(inspection)
        results.append(score.to_dict())

    _output(results, fmt)


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
