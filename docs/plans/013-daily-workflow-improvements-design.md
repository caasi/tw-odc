# 013 — Daily Workflow Improvements Design

## Summary

Three changes to streamline the daily update workflow:

1. `metadata download` defaults to JSON-only
2. Makefile `daily` target downloads all JSON metadata before applying
3. `apply-daily` auto-scaffolds missing providers

## Motivation

- The daily workflow currently only downloads `daily-changed-json.json`, missing the chance to refresh `export-json.json`. This matters because `metadata create` (used for scaffolding) depends on `export-json.json`.
- CSV and XML exports are never used in the current pipeline; downloading them wastes time and bandwidth.
- When `apply-daily` encounters a provider that doesn't exist locally, it silently skips with a warning. This means new providers appearing in daily changes are lost until someone manually runs `metadata create`.

## Change 1: `metadata download` Defaults to JSON-Only

### Current Behavior

`metadata download` reads all entries from the metadata `manifest.json` and downloads every one (export-json.json, export-csv.csv, export-xml.xml, daily-changed-json.json, daily-changed-csv.csv).

### New Behavior

- **Default**: only download entries whose format field is `json` (checked against the manifest entry's derived file extension). This covers `export-json.json`, `daily-changed-json.json`.
- **`--only <filename>`**: unchanged — downloads exactly the specified file, bypasses the JSON filter.
- **`--all` flag**: downloads all entries (restores old behavior).
- `--only` and `--all` are mutually exclusive.

**Breaking change**: the default behavior changes from downloading all formats to JSON-only. Use `--all` to restore the previous behavior.

### Implementation

Filter is applied at CLI layer (`cli.py` `metadata_download`), before passing entries to the fetcher. The fetcher remains unaware of format distinctions.

## Change 2: Makefile `daily` Target

### Current

```makefile
daily: daily-download daily-apply
daily-download:
	uv run tw-odc metadata download --only daily-changed-json.json
daily-apply:
	uv run tw-odc metadata apply-daily
```

### New

```makefile
daily: daily-download daily-apply
daily-download:
	uv run tw-odc metadata download
daily-apply:
	uv run tw-odc metadata apply-daily
```

Since `metadata download` now defaults to JSON-only, this downloads both `export-json.json` and `daily-changed-json.json` in one step.

## Change 3: `apply-daily` Auto-Scaffolds Missing Providers

### Current Behavior

When `provider_name not in providers`: emit warning `"no_local_manifest"`, skip.

### New Behavior

1. Lazy-load `export-json.json` (only on first missing provider, parsed once and cached for the rest of the run).
2. Use `group_by_provider` to get the provider's full dataset list from the export.
3. Call `create_dataset_manifest` to scaffold the provider directory.
4. After scaffolding, apply the daily change to the newly created manifest. Note: since `export-json.json` likely already contains the latest data, the apply step may be a no-op (0 changes). A provider may appear in `"created"` but not in `"updated"` — this is expected.
5. Output JSON gains a `"created"` field (always present, empty list if no providers were created) listing newly scaffolded provider slugs.

### Error Handling

- `export-json.json` does not exist → warning `"export_json_missing"`, skip that provider.
- Provider not found in `export-json.json` → warning `"provider_not_in_export"`, skip.
- The old `"no_local_manifest"` warning is removed (replaced by auto-create logic).

### Lazy Loading Rationale

Most daily runs have all providers already present. Reading and parsing `export-json.json` (~50+ MB) is expensive, so it's deferred until actually needed.

## Files Changed

| File | Change |
|------|--------|
| `src/tw_odc/cli.py` | `metadata_download`: add `--all` flag, default JSON filter; `metadata_apply_daily`: auto-scaffold logic |
| `Makefile` | `daily-download` target drops `--only` |
| `tests/test_cli.py` | Tests for JSON-only default, `--all`, auto-scaffold in apply-daily |
| `CLAUDE.md` | Update command examples and pipeline description |

## Out of Scope

- Scaffolding only the datasets mentioned in daily change (partial scaffold) — deferred due to unreliable source data.
- Format inference from URL for new datasets with `format: null` — left to `dataset check` with magic bytes.
- Changes to `fetcher.py` or `manifest.py` core logic.
