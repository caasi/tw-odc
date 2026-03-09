import asyncio

import typer

from data_gov_tw.crawler import crawl

app = typer.Typer()


@app.command()
def do_crawl() -> None:
    """下載 data.gov.tw 的資料集匯出檔案（JSON、CSV、XML）。"""
    asyncio.run(crawl())


if __name__ == "__main__":
    app()
