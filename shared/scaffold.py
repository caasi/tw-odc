import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_PATCHES_DIR: Path = Path(__file__).parent / "patches"


INIT_TEMPLATE = '''from shared.fetcher import fetch_all


async def run() -> None:
    await fetch_all(__file__)
'''

MAIN_TEMPLATE = '''import asyncio
from pathlib import Path

import typer

from shared.fetcher import clean, fetch_all
from shared.scorer import score_provider

app = typer.Typer()


@app.callback(invoke_without_command=True)
def crawl(
    ctx: typer.Context,
    only: str | None = typer.Option(None, "--only", help="只下載指定檔案（datasets/ 中的檔名）"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取，強制重新下載"),
) -> None:
    """下載此機關的所有開放資料集。"""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(fetch_all(__file__, only=only, no_cache=no_cache))


@app.command("clean")
def clean_cmd() -> None:
    """清理所有產出檔案（datasets/、etags.json、issues.jsonl、scores.json）。"""
    removed = clean(__file__)
    if removed:
        for name in removed:
            print(f"  已刪除 {name}")
    else:
        print("已經很乾淨了")


@app.command()
def score() -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    pkg_dir = Path(__file__).parent
    scores = score_provider(pkg_dir)
    datasets_dir = pkg_dir / "datasets"
    cwd = Path.cwd()

    for d in scores["datasets"]:
        star = d["star_score"]
        stars = "★" * star + "☆" * (5 - star) if star > 0 else "-----"
        fmt = d["declared_format"]
        file_path = datasets_dir / f"{d['id']}.{fmt}"
        rel = file_path.relative_to(cwd) if file_path.is_relative_to(cwd) else file_path
        print(f"{stars}  {rel}")

    total = len(scores["datasets"])
    scored = [d for d in scores["datasets"] if d["star_score"] > 0]
    avg = sum(d["star_score"] for d in scored) / len(scored) if scored else 0
    print(f"\\n{scores['provider']} — {total} 筆資料集, 平均 {avg:.1f} 星")


if __name__ == "__main__":
    app()
'''


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
            netloc = urlparse(url).netloc
            # Strip port
            netloc = netloc.split(":")[0]
            # Strip www.
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


def group_by_provider(datasets: list[dict]) -> dict[str, list[dict]]:
    """Group raw export.json entries by provider name."""
    groups: dict[str, list[dict]] = {}
    for d in datasets:
        provider = d["提供機關"]
        groups.setdefault(provider, []).append(d)
    return groups


def _parse_dataset(raw: dict) -> dict:
    """Convert a raw export.json entry to manifest dataset format."""
    from shared import FORMAT_ALIASES

    urls = [u.strip() for u in raw["資料下載網址"].split(";") if u.strip()]
    formats = [f.strip() for f in raw["檔案格式"].split(";") if f.strip()]
    fmt = formats[0].lower() if formats else "bin"
    fmt = FORMAT_ALIASES.get(fmt, fmt)
    return {
        "id": str(raw["資料集識別碼"]),
        "name": raw["資料集名稱"],
        "format": fmt,
        "urls": urls,
    }


def compute_slug(provider_name: str, urls: list[str]) -> str:
    """Return the slug for a provider: domain-based or org_<sha256> fallback."""
    slug = derive_slug(urls)
    if not slug:
        h = hashlib.sha256(provider_name.encode("utf-8")).hexdigest()[:16]
        slug = f"org_{h}"
    return slug


def _resolve_pointer(doc: Any, segments: list[str]) -> tuple[Any, str | int]:
    """Walk a JSON Pointer (RFC 6901) path and return (parent_node, last_key).

    The last_key is returned as an int when the parent is a list, unless the
    last segment is ``"-"`` (RFC 6902 end-of-array sentinel).
    """
    obj: Any = doc
    for seg in segments[:-1]:
        obj = obj[int(seg)] if isinstance(obj, list) else obj[seg]
    last_seg = segments[-1]
    last: str | int = last_seg if (not isinstance(obj, list) or last_seg == "-") else int(last_seg)
    return obj, last


def _json_pointer_segments(pointer: str) -> list[str]:
    """Split a JSON Pointer (RFC 6901) into path segments, unescaping ~ sequences.

    An empty string ``""`` refers to the whole document and returns ``[]``.
    """
    if not pointer:
        return []
    parts = pointer.split("/")[1:]  # drop the leading empty string before the first /
    return [seg.replace("~1", "/").replace("~0", "~") for seg in parts]


def apply_json_patch(doc: dict, operations: list[dict]) -> dict:
    """Apply RFC 6902 JSON Patch operations to *doc* and return the patched copy.

    Supports ``add``, ``remove``, ``replace``, and ``test`` operations.

    The ``add`` operation on a numeric array index is idempotent: if the element
    at the target index already equals the value being inserted, the insertion is
    skipped.  All other operations are naturally idempotent (overwriting with the
    same value has no observable effect).  The RFC 6902 end-of-array sentinel
    (``"-"``) always appends and is never subject to the idempotency check.
    """
    doc = copy.deepcopy(doc)

    for op_dict in operations:
        op = op_dict["op"]
        segments = _json_pointer_segments(op_dict["path"])
        parent, last = _resolve_pointer(doc, segments)

        if op == "replace":
            parent[last] = op_dict["value"]

        elif op == "add":
            if isinstance(parent, list):
                if last == "-":
                    # RFC 6902: "-" always appends to the end
                    parent.append(op_dict["value"])
                else:
                    idx = int(last)
                    # Idempotency: skip if value at that index already matches
                    if idx < len(parent) and parent[idx] == op_dict["value"]:
                        continue
                    parent.insert(idx, op_dict["value"])
            else:
                parent[last] = op_dict["value"]

        elif op == "remove":
            if isinstance(parent, list):
                del parent[int(last)]
            else:
                del parent[last]

        elif op == "test":
            try:
                actual = parent[last]
            except (KeyError, IndexError):
                raise ValueError(
                    f"JSON Patch test failed at {op_dict['path']!r}: path does not exist"
                )
            if actual != op_dict["value"]:
                raise ValueError(
                    f"JSON Patch test failed at {op_dict['path']!r}: "
                    f"expected {op_dict['value']!r}, got {actual!r}"
                )

    return doc


def apply_manifest_patch(pkg_dir: Path, slug: str) -> bool:
    """Apply shared/patches/<slug>/manifest.json (RFC 6902) to manifest.json if it exists.

    Reads the current manifest, applies the patch operations in-memory, and
    writes the result back.  Operations are applied to a deep copy so the file
    is only updated if parsing and patching succeed.

    Returns True if a patch file was found and applied, False if none exists.
    Raises ValueError / KeyError if a patch operation is invalid.
    """
    patch_file = _PATCHES_DIR / slug / "manifest.json"
    if not patch_file.exists():
        return False

    operations: list[dict] = json.loads(patch_file.read_text(encoding="utf-8"))
    manifest_path = pkg_dir / "manifest.json"
    doc: dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    patched = apply_json_patch(doc, operations)
    manifest_path.write_text(
        json.dumps(patched, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def scaffold_provider(
    base_dir: Path, provider_name: str, raw_datasets: list[dict]
) -> str:
    """Generate a provider package under base_dir. Returns the slug."""
    all_urls = []
    for d in raw_datasets:
        all_urls.extend(u.strip() for u in d["資料下載網址"].split(";") if u.strip())

    slug = compute_slug(provider_name, all_urls)

    pkg_dir = base_dir / slug
    if pkg_dir.exists():
        return slug

    pkg_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "provider": provider_name,
        "slug": slug,
        "datasets": [_parse_dataset(d) for d in raw_datasets],
    }

    (pkg_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    apply_manifest_patch(pkg_dir, slug)
    (pkg_dir / "__init__.py").write_text(INIT_TEMPLATE)
    (pkg_dir / "__main__.py").write_text(MAIN_TEMPLATE)

    return slug
