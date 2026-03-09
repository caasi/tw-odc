import json
from pathlib import Path

import typer

from shared.scaffold import group_by_provider, scaffold_provider
from shared.scorer import score_provider

app = typer.Typer()


@app.command("list")
def list_providers(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    query: str = typer.Option(
        "", help="篩選機關名稱（模糊比對）"
    ),
) -> None:
    """列出 export.json 中所有提供機關。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    for name, datasets in sorted(groups.items()):
        if query and query not in name:
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


@app.command("score")
def score(
    provider_dir: Path = typer.Argument(
        None, help="要評分的 provider 目錄路徑（例如 opdadm_moi_gov_tw）"
    ),
    all_providers: bool = typer.Option(
        False, "--all", help="評分所有有 manifest.json 的 provider"
    ),
) -> None:
    """對已下載的資料集進行 5-Star 評分。"""
    if all_providers:
        cwd = Path.cwd()
        provider_dirs = sorted(
            p.parent for p in cwd.glob("*/manifest.json")
            if p.parent.name != "data_gov_tw"
        )
        if not provider_dirs:
            print("找不到任何 provider 目錄")
            raise typer.Exit(1)
        for pkg_dir in provider_dirs:
            _score_one(pkg_dir)
    elif provider_dir is not None:
        _score_one(Path(provider_dir))
    else:
        print("請指定 provider 目錄或使用 --all")
        raise typer.Exit(1)


def _score_one(pkg_dir: Path) -> None:
    """Score a single provider and print per-file scores + summary."""
    scores = score_provider(pkg_dir)
    datasets_dir = pkg_dir / "datasets"

    for d in scores["datasets"]:
        star = d["star_score"]
        stars = "★" * star + "☆" * (3 - star) if star > 0 else "---"
        # Build relative path from the file's declared format and id
        fmt = d["declared_format"]
        file_path = datasets_dir / f"{d['id']}.{fmt}"
        rel = file_path.relative_to(Path.cwd()) if file_path.is_relative_to(Path.cwd()) else file_path
        print(f"{stars}  {rel}")

    total = len(scores["datasets"])
    scored = [d for d in scores["datasets"] if d["star_score"] > 0]
    avg = sum(d["star_score"] for d in scored) / len(scored) if scored else 0
    print(f"\n{scores['provider']} — {total} 筆資料集, 平均 {avg:.1f} 星")


if __name__ == "__main__":
    app()
