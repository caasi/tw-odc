import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


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


def scaffold_provider(
    base_dir: Path, provider_name: str, raw_datasets: list[dict]
) -> str:
    """Generate a provider package under base_dir. Returns the slug."""
    all_urls = []
    for d in raw_datasets:
        all_urls.extend(u.strip() for u in d["資料下載網址"].split(";") if u.strip())

    slug = derive_slug(all_urls)
    if not slug:
        # Fallback: stable hash of provider name (SHA-256, first 16 hex chars)
        h = hashlib.sha256(provider_name.encode("utf-8")).hexdigest()[:16]
        slug = f"org_{h}"

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
    (pkg_dir / "__init__.py").write_text(INIT_TEMPLATE)
    (pkg_dir / "__main__.py").write_text(MAIN_TEMPLATE)

    return slug
