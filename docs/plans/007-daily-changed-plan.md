# Daily Changed Dataset Integration — Implementation Plan

> **Status:** IMPLEMENTED. This plan reflects the actual implementation as of 2026-03-11.

**Goal:** Add `params` support to metadata manifest so tw-odc can download date-parameterized daily changed datasets from data.gov.tw.

**Architecture:** Extend `fetch_all` in `fetcher.py` to resolve URL templates via an optional `params` dict on dataset entries. Add `--date` CLI option to override `params.date`. Update root `manifest.json` with daily-changed entries. Add `metadata apply-daily` command for incremental provider updates.

**Tech Stack:** Python 3.13, typer, aiohttp (existing stack — no new deps)

---

### Task 1: Add `resolve_params` helper to fetcher

**Files:**
- Modified: `tw_odc/fetcher.py`
- Test: `tests/test_fetcher.py`

**Implementation** (`tw_odc/fetcher.py`):

```python
def resolve_params(params: dict | None, overrides: dict | None = None) -> dict:
    """Resolve special param values. 'today' → YYYY-MM-DD. Overrides take precedence.

    Only keys already present in params are resolved; extra override keys are ignored.
    Returns an empty dict when params is None or empty.
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
```

> **Note vs. original design:** `resolve_params` only iterates over keys present in `params`. Extra keys in `overrides` that are not in `params` are ignored. The original plan used `{**params, **(overrides or {})}` which would allow overrides to inject new keys — the implementation is more restrictive.

**Tests:** `test_resolve_params_today`, `test_resolve_params_literal`, `test_resolve_params_empty`

---

### Task 2: `_dest_filename` — stable filenames (no params suffix)

**Files:**
- Modified: `tw_odc/fetcher.py`
- Test: `tests/test_fetcher.py`

**Implementation:** `_dest_filename` does **not** accept a `resolved_params` argument. Filenames are always `{id}.{format}` (or `{id}-{n}.{format}` for multi-URL datasets), regardless of params. Params affect URL substitution only.

```python
def _dest_filename(dataset: dict, url_index: int, url_count: int) -> str:
    """Derive destination filename from dataset id and format."""
    fmt = dataset["format"].lower()
    dataset_id = str(dataset["id"])
    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(fmt):
        raise ValueError(f"Unsafe dataset format: {fmt!r}")
    if url_count == 1:
        return f"{dataset_id}.{fmt}"
    return f"{dataset_id}-{url_index + 1}.{fmt}"
```

> **Divergence from original plan:** The original plan proposed adding a `resolved_params` kwarg and including param values as a date suffix in the filename (e.g., `daily-changed-json-2026-03-10.json`). The implementation uses stable filenames instead (e.g., `daily-changed-json.json`). This matches the design doc (`007-daily-changed-design.md`) which explicitly states "params 只影響 URL 模板替換，不反映在檔名中".

**Tests:** `test_dest_filename_ignores_params`, `test_dest_filename_without_params_unchanged`

---

### Task 3: Update `fetch_all` to resolve params, substitute URLs, and bypass ETag cache

**Files:**
- Modified: `tw_odc/fetcher.py`
- Test: `tests/test_fetcher.py`

**Implementation** — `fetch_all` gains `param_overrides: dict | None = None` parameter. In the download collection loop:

```python
for dataset in manifest["datasets"]:
    resolved = resolve_params(dataset.get("params"), param_overrides)
    urls = dataset["urls"]
    has_params = bool(dataset.get("params"))
    if resolved:
        urls = [u.format_map(resolved) for u in urls]
    for i, url in enumerate(urls):
        filename = _dest_filename(dataset, i, len(urls))   # no resolved_params
        ...
        if has_params:
            parameterized_urls.add(url)
```

**ETag cache safety for parameterized datasets** (not in original plan):

Parameterized datasets interact with the ETag cache as follows:
- At the start of `fetch_all`, existing ETag cache entries whose URL matches a parameterized URL being fetched in this run are **evicted** (different dates produce different URLs that map to the same filename)
- Conditional headers (`If-None-Match`, `If-Modified-Since`) are **never sent** for parameterized URLs
- Successful downloads for parameterized URLs are **never written** to the ETag cache
- ETag cache entries for parameterized URLs from previous runs may remain in `etags.json`, but they are no longer consulted

> **Divergence from original plan:** The original plan called `_dest_filename(dataset, i, len(urls), resolved_params=resolved or None)`. The implementation calls `_dest_filename(dataset, i, len(urls))` — no resolved_params argument needed since filenames are stable.

**Tests:** `test_fetch_all_resolves_params`, `test_fetch_all_param_overrides`, `test_fetch_all_parameterized_skips_etag_cache`

---

### Task 4: Add `--date` CLI option to `metadata download`

**Files:**
- Modified: `tw_odc/cli.py`
- Test: `tests/test_cli.py`

**Implementation:**

```python
@metadata_app.command("download")
def metadata_download(
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    only: str | None = typer.Option(None, "--only", help="Download only this file"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
    date: str | None = typer.Option(None, "--date", help="Override {date} param (YYYY-MM-DD)"),
) -> None:
    """Download metadata files."""
    from tw_odc.fetcher import fetch_all

    cwd = Path.cwd()
    manifest = _load_and_check(cwd, ManifestType.METADATA)
    param_overrides = {"date": date} if date else None
    asyncio.run(fetch_all(manifest, cwd, only=only, no_cache=no_cache, cache_path=cwd / "etags.json", param_overrides=param_overrides))
```

**Tests:** `TestMetadataDownloadDate::test_date_option_passes_param_overrides`

---

### Task 5: Update manifest.json and .gitignore

**Files:**
- Modified: `manifest.json`
- Modified: `.gitignore`

**manifest.json** — two daily-changed entries added after the 3 static export entries:

```json
{
  "id": "daily-changed-json",
  "name": "每日異動資料集 JSON",
  "format": "json",
  "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
  "params": { "date": "today" }
},
{
  "id": "daily-changed-csv",
  "name": "每日異動資料集 CSV",
  "format": "csv",
  "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=csv&report_date={date}"],
  "params": { "date": "today" }
}
```

**.gitignore** — `/daily-changed-*.*` added after existing export entries.

---

### Task 6: Update CLAUDE.md documentation

**Files:**
- Modified: `CLAUDE.md`

Daily-changed commands documented in the Commands section; `params` field described in the Architecture section.

---

### Task 7: Add `metadata apply-daily` command

> **Note:** This task was described in the design doc (`007-daily-changed-design.md`) but was not included in the original implementation plan. It was implemented alongside Tasks 1–6.

**Files:**
- Modified: `tw_odc/cli.py` — new `metadata apply-daily` command
- Modified: `tw_odc/manifest.py` — new `update_dataset_manifest` and `find_existing_providers` functions
- Test: `tests/test_cli.py` and `tests/test_manifest.py`

**CLI interface:**

```bash
# Read daily-changed-json.json (uses today's date label)
tw-odc metadata apply-daily

# Specify date label for output summary (does NOT select a different input file)
tw-odc metadata apply-daily --date 2026-03-10
```

**Flow:**
1. Load `daily-changed-json.json` from cwd (must be downloaded first via `metadata download`)
2. `group_by_provider()` groups changed datasets by provider name
3. `find_existing_providers(cwd)` maps provider names to their local `pkg_dir` paths
4. For each provider in the daily data:
   - If contains deleted datasets: add warning `{provider, reason: "contains_deleted_datasets"}`
   - Filter to non-deleted (active) datasets
   - If no local manifest exists: add warning `{provider, reason: "no_local_manifest"}`, skip
   - If no active datasets: add to `skipped`
   - Otherwise: `update_dataset_manifest(pkg_dir, parsed_datasets)` → merge into existing manifest
     - Updated count > 0: add to `updated`
     - Updated count == 0: add to `skipped`

**Output (JSON):**

```json
{
  "date": "2026-03-10",
  "updated": ["provider_slug_1", "provider_slug_2"],
  "skipped": ["provider_slug_3"],
  "warnings": [
    {"provider": "某機關", "reason": "no_local_manifest"},
    {"provider": "另機關", "reason": "contains_deleted_datasets"}
  ]
}
```

**`update_dataset_manifest(pkg_dir, changed_datasets) -> int`** in `tw_odc/manifest.py`:
- Reads existing `manifest.json` datasets
- Merges changed datasets by id (existing entries overwritten, new entries appended)
- Writes back to `manifest.json`
- Returns count of updated datasets

**`find_existing_providers(cwd) -> dict[str, Path]`** in `tw_odc/manifest.py`:
- Scans `cwd` for subdirectories containing `manifest.json` with `type: dataset`
- Returns `{provider_name: pkg_dir}` mapping

**Behaviour for deleted datasets:** Warned but not processed — the deleted entry is excluded from `active` list and a warning is emitted. Manual intervention required to remove deleted datasets from local manifests.
