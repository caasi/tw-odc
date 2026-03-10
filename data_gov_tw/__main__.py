import asyncio

import typer

from shared.fetcher import clean, fetch_all

app = typer.Typer()


@app.callback(invoke_without_command=True)
def crawl(
    ctx: typer.Context,
    only: str | None = typer.Option(None, "--only", help="只下載指定檔案（datasets/ 中的檔名）"),
    no_cache: bool = typer.Option(False, "--no-cache", help="忽略 ETag 快取，強制重新下載"),
) -> None:
    """下載 data.gov.tw 的資料集匯出檔案（JSON、CSV、XML）。"""
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


if __name__ == "__main__":
    app()
