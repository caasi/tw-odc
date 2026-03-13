import asyncio
import datetime
import json
import re
import shutil
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn

from tw_odc.i18n import t

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


async def check_url_health(
    url: str,
    session: aiohttp.ClientSession | None = None,
    timeout: int = 10,
) -> tuple[bool, str | None]:
    """HEAD check on a URL. Returns (is_healthy, reason_if_not).

    Healthy: 2xx or 3xx.
    Unhealthy: 4xx, 5xx, timeout, connection error.
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False) as resp:
            if resp.status in (405, 501):
                # Server doesn't support HEAD; assume GET will work.
                return True, None
            if resp.status < 400:
                return True, None
            return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, "Timeout"
    except aiohttp.ClientSSLError:
        # SSL failed — retry with verification disabled (mirrors _do_download fallback)
        no_verify = ssl.create_default_context()
        no_verify.check_hostname = False
        no_verify.verify_mode = ssl.CERT_NONE
        retry_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=no_verify)
        )
        try:
            async with retry_session.head(url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False) as resp:
                if resp.status in (405, 501):
                    return True, None
                if resp.status < 400:
                    return True, None
                return False, f"HTTP {resp.status}"
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            return False, str(e)
        finally:
            await retry_session.close()
    except aiohttp.ClientError as e:
        return False, str(e)
    finally:
        if close_session:
            await session.close()
_SAFE_FMT_RE = re.compile(r"^\w+$")


def resolve_params(params: dict | None, overrides: dict | None = None) -> dict:
    """Resolve special param values. 'today' → YYYY-MM-DD. Overrides take precedence.

    Only keys already present in params are resolved; extra override keys are ignored.
    Returns an empty dict when params is None or empty.

    Example:
        resolve_params({"date": "today"})                           # {"date": "YYYY-MM-DD"}
        resolve_params({"date": "today"}, {"date": "2026-01-01"})  # {"date": "2026-01-01"}
        resolve_params({"date": "today"}, {"other": "ignored"})    # {"date": "YYYY-MM-DD"}
    """
    if not params:
        return {}
    resolved = {}
    for key, value in params.items():
        override_val = (overrides or {}).get(key)
        if override_val is not None:
            resolved[key] = str(override_val)
        elif value == "today":
            resolved[key] = datetime.date.today().isoformat()
        else:
            resolved[key] = str(value)
    return resolved


def _dest_filename(dataset: dict, url_index: int, url_count: int) -> str:
    """Derive destination filename from dataset id and format."""
    fmt = (dataset["format"] or "bin").lower()
    dataset_id = str(dataset["id"])
    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(fmt):
        raise ValueError(f"Unsafe dataset format: {fmt!r}")
    if url_count == 1:
        return f"{dataset_id}.{fmt}"
    return f"{dataset_id}-{url_index + 1}.{fmt}"


def clean(pkg_dir: Path) -> list[str]:
    """Remove all generated files for a provider package.

    Deletes: datasets/, etags.json, issues.jsonl, scores.json.
    Returns list of names that were actually removed.
    """
    manifest_path = pkg_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"manifest.json not found in {pkg_dir}; not a provider package"
        )
    removed: list[str] = []
    datasets_dir = pkg_dir / "datasets"
    if datasets_dir.is_dir():
        shutil.rmtree(datasets_dir)
        removed.append("datasets/")
    for name in ("etags.json", "issues.jsonl", "scores.json"):
        path = pkg_dir / name
        if path.exists():
            path.unlink()
            removed.append(name)
    return removed


def clean_dataset(pkg_dir: Path, dataset_id: str, dataset_urls: list[str]) -> list[str]:
    """Remove generated files for a single dataset.

    Deletes matching files in datasets/, and removes related entries from
    etags.json, issues.jsonl, and scores.json.
    Returns list of descriptions of what was removed.
    """
    removed: list[str] = []

    # Remove dataset files
    datasets_dir = pkg_dir / "datasets"
    if datasets_dir.exists():
        for f in datasets_dir.glob(f"{dataset_id}.*"):
            f.unlink()
            removed.append(str(f.name))
        for f in datasets_dir.glob(f"{dataset_id}-*"):
            f.unlink()
            removed.append(str(f.name))

    # Remove matching entries from etags.json
    etags_path = pkg_dir / "etags.json"
    if etags_path.exists():
        etags = json.loads(etags_path.read_text(encoding="utf-8"))
        url_set = set(dataset_urls)
        filtered = {k: v for k, v in etags.items() if k not in url_set}
        if len(filtered) < len(etags):
            removed.append(f"etags.json {t('output.partial')}")
            if filtered:
                etags_path.write_text(
                    json.dumps(filtered, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                etags_path.unlink()

    # Remove matching lines from issues.jsonl
    issues_path = pkg_dir / "issues.jsonl"
    if issues_path.exists():
        lines = issues_path.read_text(encoding="utf-8").splitlines()
        kept = []
        removed_count = 0
        prefix = f"{dataset_id}."
        prefix_dash = f"{dataset_id}-"
        for line in lines:
            if not line.strip():
                continue
            entry = json.loads(line)
            fname = entry.get("file", "")
            if fname.startswith(prefix) or fname.startswith(prefix_dash):
                removed_count += 1
            else:
                kept.append(line)
        if removed_count > 0:
            removed.append(f"issues.jsonl {t('output.partial')}")
            if kept:
                issues_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            else:
                issues_path.unlink()

    # Remove matching entries from scores.json
    scores_path = pkg_dir / "scores.json"
    if scores_path.exists():
        scores = json.loads(scores_path.read_text(encoding="utf-8"))
        datasets = scores.get("datasets", [])
        filtered_ds = [d for d in datasets if str(d.get("id")) != dataset_id]
        if len(filtered_ds) < len(datasets):
            removed.append(f"scores.json {t('output.partial')}")
            if filtered_ds:
                scores["datasets"] = filtered_ds
                scores_path.write_text(
                    json.dumps(scores, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                scores_path.unlink()

    return removed


async def fetch_all(
    manifest: dict,
    output_dir: Path,
    concurrency: int = 5,
    only: str | None = None,
    no_cache: bool = False,
    cache_path: Path | None = None,
    param_overrides: dict | None = None,
) -> None:
    """Download all datasets listed in manifest.

    Args:
        manifest: Parsed manifest dict with "datasets" key.
        output_dir: Directory to write downloaded files to.
        concurrency: Maximum number of simultaneous downloads.
        only: If set, only download the file whose dest name matches.
        no_cache: If True, skip conditional headers (ignore ETag cache).
        cache_path: Path to etags.json. If None, uses output_dir.parent / "etags.json".
    """
    if cache_path is None:
        cache_path = output_dir.parent / "etags.json"
    issues_path = output_dir.parent / "issues.jsonl"

    # Load cached ETags
    cache: dict[str, dict[str, str]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    # Collect all (url, dest) pairs
    # Parameterized datasets (with `params`) always get a fresh download — their
    # URL changes across runs but maps to the same dest filename, so ETag caching
    # by URL would leave stale content if a different parameterized URL was cached.
    downloads: list[tuple[str, Path]] = []
    parameterized_urls: set[str] = set()
    for dataset in manifest["datasets"]:
        resolved = resolve_params(dataset.get("params"), param_overrides)
        urls = dataset["urls"]
        has_params = bool(dataset.get("params"))
        if resolved:
            urls = [u.format_map(resolved) for u in urls]
        for i, url in enumerate(urls):
            filename = _dest_filename(dataset, i, len(urls))
            dest = (output_dir / filename).resolve()
            try:
                dest.relative_to(output_dir.resolve())
            except ValueError:
                raise ValueError(f"Destination path escapes output directory: {dest}")
            downloads.append((url, dest))
            if has_params:
                parameterized_urls.add(url)

    # Evict any stale cache entries for parameterized URLs so that
    # conditional headers are never sent and old entries are cleaned up.
    cache_evicted = any(url in cache for url in parameterized_urls)
    for url in parameterized_urls:
        cache.pop(url, None)

    if only:
        matched = [(url, dest) for url, dest in downloads if dest.name == only]
        if not matched:
            available = ", ".join(dest.name for _, dest in downloads)
            print(f"E106: {t('E106', name=only, available=available)}", file=sys.stderr)
            return
        downloads = matched

    # HEAD pre-check: verify URLs are reachable before downloading
    if downloads:
        unhealthy_urls: set[str] = set()
        async with aiohttp.ClientSession() as check_session:
            for url, dest in downloads:
                ok, reason = await check_url_health(url, session=check_session)
                if not ok:
                    print(f"W003: {t('W003', url=url, reason=reason)}", file=sys.stderr)
                    unhealthy_urls.add(url)
        if unhealthy_urls:
            downloads = [(url, dest) for url, dest in downloads if url not in unhealthy_urls]

    if not downloads:
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    issues: list[dict] = []
    blocked_domains: set[str] = set()

    def _print(progress: Progress, msg: str) -> None:
        progress.console.print(msg, highlight=False)

    def _conditional_headers(url: str) -> dict[str, str]:
        if no_cache or url in parameterized_urls:
            return {}
        headers: dict[str, str] = {}
        entry = cache.get(url)
        if entry:
            if entry.get("etag"):
                headers["If-None-Match"] = entry["etag"]
            if entry.get("last_modified"):
                headers["If-Modified-Since"] = entry["last_modified"]
        return headers

    def _update_cache(url: str, headers: dict) -> None:
        if url in parameterized_urls:
            return
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
        filename = dest.name
        headers = _conditional_headers(url)
        async with session.get(url, ssl=ssl_ctx, headers=headers) as resp:
            if resp.status == 304:
                _print(progress, f"[dim]—[/dim] {t('status.not_modified', filename=filename)}")
                return "not_modified"
            if resp.status == 429:
                domain = urlparse(url).hostname or url
                blocked_domains.add(domain)
                _print(progress, f"[red]✗[/red] {t('status.rate_limited', filename=filename, domain=domain)}")
                issues.append({"file": filename, "url": url, "issue": "rate_limited", "detail": f"HTTP 429, domain {domain} blocked"})
                return "error"
            if resp.status != 200:
                _print(progress, f"[red]✗[/red] {t('status.http_error', filename=filename, status=resp.status)}")
                issues.append({"file": filename, "url": url, "issue": "http_error", "detail": f"HTTP {resp.status}"})
                return "error"
            _update_cache(url, dict(resp.headers))
            total = resp.content_length
            task = progress.add_task(filename, total=total or None)
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))
            progress.remove_task(task)
            return "downloaded"

    async def _download(
        session: aiohttp.ClientSession, url: str, dest: Path, progress: Progress
    ) -> None:
        filename = dest.name
        domain = urlparse(url).hostname or url
        async with sem:
            if domain in blocked_domains:
                _print(progress, f"[dim]—[/dim] {t('status.skipped_blocked', filename=filename, domain=domain)}")
                issues.append({"file": filename, "url": url, "issue": "rate_limited", "detail": f"skipped, domain {domain} blocked"})
                return
            await asyncio.sleep(0.5)
            try:
                result = await _do_download(session, url, dest, progress)
                if result == "downloaded":
                    size = dest.stat().st_size
                    _print(progress, f"[green]✓[/green] {t('status.downloaded', filename=filename, size=f'{size:,}')}")
            except aiohttp.ClientSSLError as exc:
                _print(progress, f"[yellow]⚠[/yellow] {t('status.ssl_retry', filename=filename)}")
                issues.append({"file": filename, "url": url, "issue": "ssl_error", "detail": str(exc)})
                try:
                    no_verify = ssl.create_default_context()
                    no_verify.check_hostname = False
                    no_verify.verify_mode = ssl.CERT_NONE
                    no_verify_connector = aiohttp.TCPConnector(ssl=no_verify)
                    async with aiohttp.ClientSession(connector=no_verify_connector, trust_env=True) as retry_session:
                        result = await _do_download(retry_session, url, dest, progress, ssl_ctx=no_verify)
                        if result == "downloaded":
                            size = dest.stat().st_size
                            _print(progress, f"[green]✓[/green] {t('status.downloaded_ssl_skip', filename=filename, size=f'{size:,}')}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as retry_exc:
                    _print(progress, f"[red]✗[/red] {t('status.retry_failed', filename=filename, error=retry_exc)}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                _print(progress, f"[red]✗[/red] {t('status.network_error', filename=filename, error=exc)}")
                issues.append({"file": filename, "url": url, "issue": "network_error", "detail": str(exc)})
            except Exception as exc:
                _print(progress, f"[red]✗[/red] {t('status.unexpected_error', filename=filename, error=exc)}")
                issues.append({"file": filename, "url": url, "issue": "unexpected_error", "detail": str(exc)})

    connector = aiohttp.TCPConnector(limit=concurrency)
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(), DownloadColumn(), TransferSpeedColumn(),
    ) as progress:
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            await asyncio.gather(
                *[_download(session, url, dest, progress) for url, dest in downloads]
            )

    if cache:
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    elif cache_evicted and not cache and cache_path.exists():
        # Eviction removed all remaining entries; clean up the now-empty cache file.
        cache_path.unlink()
    if issues:
        with open(issues_path, "w", encoding="utf-8") as f:
            for issue in issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")
        print(f"⚠ {t('summary.issues', count=len(issues), path=issues_path)}", file=sys.stderr)
