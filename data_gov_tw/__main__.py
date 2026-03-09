import asyncio

import typer

from shared.fetcher import fetch_all

app = typer.Typer()


@app.command()
def crawl() -> None:
    """下載 data.gov.tw 的資料集匯出檔案（JSON、CSV、XML）。"""
    asyncio.run(fetch_all(__file__))


if __name__ == "__main__":
    app()
