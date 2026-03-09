import asyncio
import json
import re
import ssl
from pathlib import Path

import aiohttp
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn

# Only allow alphanumeric, hyphen, and underscore in dataset ids and formats
# to prevent path traversal attacks.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_SAFE_FMT_RE = re.compile(r"^[A-Za-z0-9]+$")


def _load_manifest(init_file: str) -> tuple[Path, dict]:
    """Load manifest.json from the same directory as __init__.py."""
    pkg_dir = Path(init_file).parent
    manifest_path = pkg_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return pkg_dir, manifest


def _dest_filename(dataset: dict, url_index: int, url_count: int) -> str:
    """Derive destination filename from dataset id and format.

    Raises ValueError if the id or format contain unsafe characters that
    could lead to path traversal (e.g. '..', '/', absolute paths).
    """
    fmt = dataset["format"].lower()
    dataset_id = str(dataset["id"])

    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(fmt):
        raise ValueError(f"Unsafe dataset format: {fmt!r}")

    if url_count == 1:
        return f"{dataset_id}.{fmt}"
    return f"{dataset_id}-{url_index + 1}.{fmt}"


async def fetch_all(init_file: str, concurrency: int = 5) -> None:
    """Download all datasets listed in manifest.json next to init_file.

    Args:
        init_file: Path to the provider package's __init__.py (or __main__.py).
        concurrency: Maximum number of simultaneous downloads.
    """
    pkg_dir, manifest = _load_manifest(init_file)
    output_dir = pkg_dir / "datasets"
    output_dir.mkdir(parents=True, exist_ok=True)
    issues_path = pkg_dir / "issues.jsonl"

    # Load cached ETags / Last-Modified for conditional requests
    cache_path = pkg_dir / "etags.json"
    cache: dict[str, dict[str, str]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    # Collect all (url, dest) pairs
    downloads: list[tuple[str, Path]] = []
    for dataset in manifest["datasets"]:
        urls = dataset["urls"]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls))
            dest = (output_dir / filename).resolve()
            # Guard against path traversal after filename construction
            try:
                dest.relative_to(output_dir.resolve())
            except ValueError:
                raise ValueError(f"Destination path escapes output directory: {dest}")
            downloads.append((url, dest))

    sem = asyncio.Semaphore(concurrency)
    issues: list[dict] = []

    def _print(progress: Progress, msg: str) -> None:
        progress.console.print(msg, highlight=False)

    def _conditional_headers(url: str) -> dict[str, str]:
        """Build If-None-Match / If-Modified-Since headers from cache."""
        headers: dict[str, str] = {}
        entry = cache.get(url)
        if entry:
            if entry.get("etag"):
                headers["If-None-Match"] = entry["etag"]
            if entry.get("last_modified"):
                headers["If-Modified-Since"] = entry["last_modified"]
        return headers

    def _update_cache(url: str, headers: dict) -> None:
        """Store ETag / Last-Modified from response headers."""
        etag = headers.get("ETag", "")
        last_modified = headers.get("Last-Modified", "")
        entry: dict[str, str] = {}
        if isinstance(etag, str) and etag:
            entry["etag"] = etag
        if isinstance(last_modified, str) and last_modified:
            entry["last_modified"] = last_modified
        if entry:
            cache[url] = entry

    async def _do_download(
        session: aiohttp.ClientSession,
        url: str,
        dest: Path,
        progress: Progress,
        ssl_ctx: ssl.SSLContext | bool = True,
    ) -> str:
        """Attempt a single download. Returns 'downloaded', 'not_modified', or 'error'."""
        filename = dest.name
        headers = _conditional_headers(url)
        async with session.get(url, ssl=ssl_ctx, headers=headers) as resp:
            if resp.status == 304:
                _print(progress, f"[dim]—[/dim] {filename} (未變更)")
                return "not_modified"

            if resp.status != 200:
                _print(progress, f"[red]✗[/red] {filename}: HTTP {resp.status}")
                issues.append({"file": filename, "url": url, "issue": "http_error", "detail": f"HTTP {resp.status}"})
                return "error"

            _update_cache(url, dict(resp.headers))

            total = resp.content_length
            task = progress.add_task(filename, total=total or None)

            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))

            size = dest.stat().st_size
            progress.remove_task(task)
            return "downloaded"

    async def _download(
        session: aiohttp.ClientSession, url: str, dest: Path, progress: Progress
    ) -> None:
        filename = dest.name
        async with sem:
            await asyncio.sleep(0.5)  # rate limit: 2 req/s
            try:
                result = await _do_download(session, url, dest, progress)
                if result == "downloaded":
                    size = dest.stat().st_size
                    _print(progress, f"[green]✓[/green] {filename} ({size:,} bytes)")
            except aiohttp.ClientSSLError as exc:
                _print(progress, f"[yellow]⚠[/yellow] {filename}: SSL error, retrying without verification")
                issues.append({"file": filename, "url": url, "issue": "ssl_error", "detail": str(exc)})
                try:
                    no_verify = ssl.create_default_context()
                    no_verify.check_hostname = False
                    no_verify.verify_mode = ssl.CERT_NONE
                    no_verify_connector = aiohttp.TCPConnector(ssl=no_verify)
                    async with aiohttp.ClientSession(connector=no_verify_connector) as retry_session:
                        result = await _do_download(retry_session, url, dest, progress, ssl_ctx=no_verify)
                        if result == "downloaded":
                            size = dest.stat().st_size
                            _print(progress, f"[green]✓[/green] {filename} ({size:,} bytes) [yellow](SSL 驗證跳過)[/yellow]")
                except (aiohttp.ClientError, asyncio.TimeoutError) as retry_exc:
                    _print(progress, f"[red]✗[/red] {filename}: retry failed: {retry_exc}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                _print(progress, f"[red]✗[/red] {filename}: network error: {exc}")
                issues.append({"file": filename, "url": url, "issue": "network_error", "detail": str(exc)})
            except Exception as exc:
                _print(progress, f"[red]✗[/red] {filename}: unexpected error: {exc}")
                issues.append({"file": filename, "url": url, "issue": "unexpected_error", "detail": str(exc)})

    connector = aiohttp.TCPConnector(limit=concurrency)
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession(connector=connector) as session:
            await asyncio.gather(
                *[_download(session, url, dest, progress) for url, dest in downloads]
            )

    # Save ETag / Last-Modified cache
    if cache:
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if issues:
        with open(issues_path, "w", encoding="utf-8") as f:
            for issue in issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")
        print(f"⚠ {len(issues)} 個問題已記錄到 {issues_path}")
