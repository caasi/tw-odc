import asyncio
import json
from pathlib import Path

import aiohttp
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn


def _load_manifest(init_file: str) -> tuple[Path, dict]:
    """Load manifest.json from the same directory as __init__.py."""
    pkg_dir = Path(init_file).parent
    manifest_path = pkg_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return pkg_dir, manifest


def _dest_filename(dataset: dict, url_index: int, url_count: int) -> str:
    """Derive destination filename from dataset id and format."""
    fmt = dataset["format"].lower()
    dataset_id = dataset["id"]
    if url_count == 1:
        return f"{dataset_id}.{fmt}"
    return f"{dataset_id}-{url_index + 1}.{fmt}"


async def fetch_all(init_file: str) -> None:
    """Download all datasets listed in manifest.json next to init_file."""
    pkg_dir, manifest = _load_manifest(init_file)
    output_dir = pkg_dir / "datasets"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all (url, dest) pairs
    downloads: list[tuple[str, Path]] = []
    for dataset in manifest["datasets"]:
        urls = dataset["urls"]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls))
            downloads.append((url, output_dir / filename))

    async def _download(
        session: aiohttp.ClientSession, url: str, dest: Path, progress: Progress
    ) -> None:
        filename = dest.name
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

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession() as session:
            await asyncio.gather(
                *[_download(session, url, dest, progress) for url, dest in downloads]
            )
