import asyncio

import typer

from shared.fetcher import fetch_all

app = typer.Typer()


@app.callback(invoke_without_command=True)
def crawl() -> None:
    """下載此機關的所有開放資料集。"""
    asyncio.run(fetch_all(__file__))


if __name__ == "__main__":
    app()
