import asyncio
import importlib
from pathlib import Path

import typer

app = typer.Typer()

PROJECT_ROOT = Path(__file__).parent


def discover_providers() -> list[str]:
    """Find all directories containing manifest.json."""
    providers = []
    for manifest in sorted(PROJECT_ROOT.glob("*/manifest.json")):
        pkg_name = manifest.parent.name
        providers.append(pkg_name)
    return providers


async def _run_all(concurrency: int) -> None:
    providers = discover_providers()
    print(f"發現 {len(providers)} 個 provider")
    sem = asyncio.Semaphore(concurrency)

    async def _run_provider(name: str) -> None:
        async with sem:
            print(f"=== {name} ===")
            mod = importlib.import_module(name)
            await mod.run()

    tasks = [_run_provider(name) for name in providers]
    await asyncio.gather(*tasks)


@app.callback(invoke_without_command=True)
def main(concurrency: int = typer.Option(3, help="同時執行的 provider 數量上限")) -> None:
    """執行所有 provider 的下載。"""
    asyncio.run(_run_all(concurrency))


if __name__ == "__main__":
    app()
