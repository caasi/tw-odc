import json
from pathlib import Path

import typer

from shared.scaffold import compute_slug, group_by_provider, scaffold_provider

app = typer.Typer()


@app.command("list")
def list_providers(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    query: str = typer.Option(
        "", help="篩選機關名稱（模糊比對）"
    ),
    missing: bool = typer.Option(
        False, "--missing", help="只顯示尚未產生 package 的機關"
    ),
    output_dir: Path = typer.Option(
        ".", help="掃描已存在 package 的根目錄（與 scaffold 的 --output-dir 相同）"
    ),
) -> None:
    """列出 export.json 中所有提供機關。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    for name, datasets in sorted(groups.items()):
        if query and query not in name:
            continue
        if missing:
            all_urls = [
                u.strip()
                for d in datasets
                for u in d["資料下載網址"].split(";")
                if u.strip()
            ]
            slug = compute_slug(name, all_urls)
            if (output_dir / slug).exists():
                continue
        print(f"{name} ({len(datasets)} 筆)")


@app.command("scaffold")
def scaffold(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    provider: list[str] = typer.Option(
        ..., "--provider", "-p", help="要產生的機關名稱（可重複指定）"
    ),
    output_dir: Path = typer.Option(
        ".", help="產生 package 的根目錄"
    ),
) -> None:
    """從 data.gov.tw export.json 產生指定機關的 package。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    for name in provider:
        if name not in groups:
            print(f"找不到機關: {name}")
            continue
        slug = scaffold_provider(output_dir, name, groups[name])
        pkg_dir = output_dir / slug
        n = len(groups[name])
        print(f"✓ {name} → {slug}/ ({n} 筆資料集)")


if __name__ == "__main__":
    app()
