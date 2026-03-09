import asyncio
import importlib

import typer

# Portal packages live at the project root and expose an async run().
PORTAL_PACKAGES = [
    "data_gov_tw",
]

app = typer.Typer()


async def _run_all(concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)

    async def _run_portal(name: str) -> None:
        async with sem:
            print(f"=== {name} ===")
            mod = importlib.import_module(name)
            await mod.run()

    tasks = [_run_portal(name) for name in PORTAL_PACKAGES]
    await asyncio.gather(*tasks)


@app.command()
def main(concurrency: int = typer.Option(3, help="同時執行的 portal 數量上限")) -> None:
    """執行所有 portal 的爬蟲。"""
    asyncio.run(_run_all(concurrency))


if __name__ == "__main__":
    app()
