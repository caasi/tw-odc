import asyncio
from pathlib import Path

import typer

from shared.fetcher import clean, fetch_all
from shared.scorer import score_provider

app = typer.Typer()


@app.callback(invoke_without_command=True)
def crawl(
    ctx: typer.Context,
    only: str = typer.Option(None, "--only", help="只下載指定檔案（datasets/ 中的檔名）"),
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
        stars = "★" * star + "☆" * (3 - star) if star > 0 else "---"
        fmt = d["declared_format"]
        file_path = datasets_dir / f"{d['id']}.{fmt}"
        rel = file_path.relative_to(cwd) if file_path.is_relative_to(cwd) else file_path
        print(f"{stars}  {rel}")

    total = len(scores["datasets"])
    scored = [d for d in scores["datasets"] if d["star_score"] > 0]
    avg = sum(d["star_score"] for d in scored) / len(scored) if scored else 0
    print(f"\n{scores['provider']} — {total} 筆資料集, 平均 {avg:.1f} 星")


if __name__ == "__main__":
    app()
