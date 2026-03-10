"""tw-odc CLI: Taiwan Open Data Checker."""

import asyncio
import json
import sys
from enum import StrEnum
from pathlib import Path

import typer

from tw_odc.manifest import (
    ManifestType,
    create_dataset_manifest,
    group_by_provider,
    load_manifest,
)

app = typer.Typer(name="tw-odc")
metadata_app = typer.Typer(help="metadata 資料來源操作")
dataset_app = typer.Typer(help="dataset 資料集操作")
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
            f"錯誤: 預期 manifest type 為 '{expected_type}'，實際為 '{actual}'",
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
    print("錯誤: manifest 中找不到 export-json 資料集", file=sys.stderr)
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
                        parts.append(f"({extra['count']} 筆)")
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
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
    only: str | None = typer.Option(None, "--only", help="只下載指定檔案"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取"),
) -> None:
    """下載 metadata 檔案。"""
    from tw_odc.fetcher import fetch_all

    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    asyncio.run(fetch_all(manifest, cwd, only=only, no_cache=no_cache, cache_path=cwd / "etags.json"))


@metadata_app.command("list")
def metadata_list(
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """列出 metadata 中的所有機關。"""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"錯誤: {export_path} 不存在，請先執行 tw-odc metadata download", file=sys.stderr)
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
    provider: str = typer.Option(..., "--provider", "-p", help="機關名稱"),
) -> None:
    """從 metadata 建立 dataset manifest。輸出資料夾路徑到 stdout。"""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"錯誤: {export_path} 不存在，請先執行 tw-odc metadata download", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if provider not in groups:
        print(f"錯誤: 找不到機關「{provider}」", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(cwd, provider, groups[provider])
    print(slug)


@metadata_app.command("update")
def metadata_update(
    provider: str | None = typer.Option(None, "--provider", "-p", help="機關名稱"),
    dir_path: str | None = typer.Option(None, "--dir", help="目標資料夾"),
) -> None:
    """更新既有的 dataset manifest。"""
    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    export_path = _find_export_json(manifest, cwd)
    if not export_path.exists():
        print(f"錯誤: {export_path} 不存在，請先執行 tw-odc metadata download", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(export_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    if dir_path:
        target_dir = cwd / dir_path
        target_manifest = load_manifest(target_dir)
        provider = target_manifest["provider"]

    if not provider:
        print("錯誤: 請指定 --provider 或 --dir", file=sys.stderr)
        raise typer.Exit(code=1)

    if provider not in groups:
        print(f"錯誤: 找不到機關「{provider}」", file=sys.stderr)
        raise typer.Exit(code=1)

    slug = create_dataset_manifest(cwd, provider, groups[provider])
    print(slug, file=sys.stderr)


# ─── dataset commands ───

_dataset_dir_option = typer.Option(None, "--dir", help="dataset 資料夾路徑")


@dataset_app.callback()
def dataset_callback(
    ctx: typer.Context,
    dir_path: str | None = _dataset_dir_option,
) -> None:
    """dataset 操作共用的 --dir 參數。"""
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
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """列出 dataset manifest 中的資料集。"""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    _output(manifest["datasets"], fmt)


@dataset_app.command("download")
def dataset_download(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="只下載指定 ID 的資料集"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取"),
) -> None:
    """下載 dataset 資料集。"""
    from tw_odc.fetcher import fetch_all

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    output_dir = pkg_dir / "datasets"

    dl_manifest = manifest
    if dataset_id:
        filtered = [ds for ds in manifest["datasets"] if str(ds["id"]) == dataset_id]
        if not filtered:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
            raise typer.Exit(code=1)
        dl_manifest = {**manifest, "datasets": filtered}

    asyncio.run(fetch_all(dl_manifest, output_dir, no_cache=no_cache, cache_path=pkg_dir / "etags.json"))


@dataset_app.command("check")
def dataset_check(
    ctx: typer.Context,
    dataset_id: str | None = typer.Option(None, "--id", help="只檢查指定 ID 的資料集"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """檢查已下載的資料集。"""
    from tw_odc.inspector import inspect_dataset

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    targets = manifest["datasets"]
    if dataset_id:
        targets = [ds for ds in targets if str(ds["id"]) == dataset_id]
        if not targets:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
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
    dataset_id: str | None = typer.Option(None, "--id", help="只評分指定 ID 的資料集"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    from tw_odc.inspector import inspect_dataset
    from tw_odc.scorer import score_dataset

    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    targets = manifest["datasets"]
    if dataset_id:
        targets = [ds for ds in targets if str(ds["id"]) == dataset_id]
        if not targets:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
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
    dataset_id: str | None = typer.Option(None, "--id", help="只清除指定 ID 的檔案"),
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="輸出格式"),
) -> None:
    """清除下載的檔案。"""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)

    if dataset_id:
        from tw_odc.fetcher import clean_dataset

        matched = [ds for ds in manifest["datasets"] if str(ds["id"]) == dataset_id]
        if not matched:
            print(f"錯誤: 找不到 ID 為 {dataset_id} 的資料集", file=sys.stderr)
            raise typer.Exit(code=1)
        urls = matched[0].get("urls", [])
        removed = clean_dataset(pkg_dir, dataset_id, urls)
        _output({"removed": removed}, fmt)
    else:
        from tw_odc.fetcher import clean
        removed = clean(pkg_dir)
        _output({"removed": removed}, fmt)
