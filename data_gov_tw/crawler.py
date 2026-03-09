from pathlib import Path

import aiohttp
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn

EXPORTS = [
    "https://data.gov.tw/datasets/export/json",
    "https://data.gov.tw/datasets/export/csv",
    "https://data.gov.tw/datasets/export/xml",
]

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "datasets"


def _filename_from_url(url: str) -> str:
    ext = url.rsplit("/", 1)[-1]
    return f"export.{ext}"


async def crawl(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession() as session:
            for url in EXPORTS:
                filename = _filename_from_url(url)
                dest = output_dir / filename

                async with session.get(url) as resp:
                    if resp.status != 200:
                        progress.console.print(f"[red]✗[/red] {filename}: HTTP {resp.status}")
                        continue

                    total = resp.content_length or 0
                    task = progress.add_task(filename, total=total)

                    with open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))

                    progress.console.print(f"[green]✓[/green] {filename} ({dest.stat().st_size:,} bytes)")
