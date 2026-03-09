import asyncio
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

    async def _download(session: aiohttp.ClientSession, url: str, progress: Progress) -> None:
        filename = _filename_from_url(url)
        dest = output_dir / filename

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    progress.console.print(f"[red]✗[/red] {filename}: HTTP {resp.status}")
                    return

                total = resp.content_length
                task = progress.add_task(filename, total=total or None)

                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

                size = dest.stat().st_size
                progress.remove_task(task)
                progress.console.print(f"[green]✓[/green] {filename} ({size:,} bytes)")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            progress.console.print(f"[red]✗[/red] {filename}: {type(exc).__name__}: {exc}")

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[_download(session, url, progress) for url in EXPORTS])
