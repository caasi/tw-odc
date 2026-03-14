# Daily Workflow Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Streamline the daily update workflow so `make daily` downloads JSON metadata, auto-scaffolds missing providers, and applies daily changes in one step.

**Architecture:** Three changes at CLI layer only: (1) filter `metadata download` to JSON-only by default, (2) update Makefile, (3) add auto-scaffold logic to `apply-daily`. No changes to `fetcher.py` or `manifest.py`.

**Tech Stack:** Python 3.13, typer, pytest, uv

**Spec:** `docs/plans/013-daily-workflow-improvements-design.md`

---

## Chunk 1: `metadata download` JSON-only default

### Task 1: Add `--all` flag and JSON filter to `metadata download`

**Files:**
- Modify: `src/tw_odc/cli.py:155-177` (`metadata_download` function)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test — default download filters to JSON entries only**

In `tests/test_cli.py`, add a new test class after `TestMetadataDownloadDate`:

```python
class TestMetadataDownloadJsonDefault:
    def test_default_downloads_json_only(self, tmp_path, monkeypatch):
        """Default metadata download should only fetch JSON-format entries."""
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [
                {"id": "export-json", "name": "JSON", "format": "json",
                 "urls": ["https://example.com/export.json"]},
                {"id": "export-csv", "name": "CSV", "format": "csv",
                 "urls": ["https://example.com/export.csv"]},
                {"id": "export-xml", "name": "XML", "format": "xml",
                 "urls": ["https://example.com/export.xml"]},
                {"id": "daily-changed-json", "name": "Daily JSON", "format": "json",
                 "urls": ["https://example.com/daily.json"],
                 "params": {"date": "today"}},
                {"id": "daily-changed-csv", "name": "Daily CSV", "format": "csv",
                 "urls": ["https://example.com/daily.csv"],
                 "params": {"date": "today"}},
            ],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        captured = {}

        async def mock_fetch_all(m, output_dir, **kwargs):
            captured["datasets"] = m["datasets"]

        import tw_odc.fetcher
        monkeypatch.setattr(tw_odc.fetcher, "fetch_all", mock_fetch_all)
        import asyncio
        monkeypatch.setattr("tw_odc.cli.asyncio.run",
                            lambda coro: asyncio.get_event_loop().run_until_complete(coro))

        result = runner.invoke(app, ["metadata", "download"])
        assert result.exit_code == 0
        ids = [d["id"] for d in captured["datasets"]]
        assert "export-json" in ids
        assert "daily-changed-json" in ids
        assert "export-csv" not in ids
        assert "export-xml" not in ids
        assert "daily-changed-csv" not in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::TestMetadataDownloadJsonDefault::test_default_downloads_json_only -v`
Expected: FAIL — currently all 5 entries are passed to `fetch_all`

- [ ] **Step 3: Write failing test — `--all` downloads everything**

```python
    def test_all_flag_downloads_everything(self, tmp_path, monkeypatch):
        """--all should download all entries regardless of format."""
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [
                {"id": "export-json", "name": "JSON", "format": "json",
                 "urls": ["https://example.com/export.json"]},
                {"id": "export-csv", "name": "CSV", "format": "csv",
                 "urls": ["https://example.com/export.csv"]},
            ],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        captured = {}

        async def mock_fetch_all(m, output_dir, **kwargs):
            captured["datasets"] = m["datasets"]

        import tw_odc.fetcher
        monkeypatch.setattr(tw_odc.fetcher, "fetch_all", mock_fetch_all)
        import asyncio
        monkeypatch.setattr("tw_odc.cli.asyncio.run",
                            lambda coro: asyncio.get_event_loop().run_until_complete(coro))

        result = runner.invoke(app, ["metadata", "download", "--all"])
        assert result.exit_code == 0
        ids = [d["id"] for d in captured["datasets"]]
        assert "export-json" in ids
        assert "export-csv" in ids
```

- [ ] **Step 4: Write failing test — `--only` bypasses JSON filter**

```python
    def test_only_bypasses_json_filter(self, tmp_path, monkeypatch):
        """--only should work for any file, ignoring the JSON default filter."""
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [
                {"id": "export-json", "name": "JSON", "format": "json",
                 "urls": ["https://example.com/export.json"]},
                {"id": "export-csv", "name": "CSV", "format": "csv",
                 "urls": ["https://example.com/export.csv"]},
            ],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        captured = {}

        async def mock_fetch_all(m, output_dir, **kwargs):
            captured["only"] = kwargs.get("only")

        import tw_odc.fetcher
        monkeypatch.setattr(tw_odc.fetcher, "fetch_all", mock_fetch_all)
        import asyncio
        monkeypatch.setattr("tw_odc.cli.asyncio.run",
                            lambda coro: asyncio.get_event_loop().run_until_complete(coro))

        result = runner.invoke(app, ["metadata", "download", "--only", "export-csv.csv"])
        assert result.exit_code == 0
        # --only passes through to fetcher, no filtering applied
        assert captured["only"] == "export-csv.csv"
```

- [ ] **Step 5: Write failing test — `--only` and `--all` are mutually exclusive**

```python
    def test_only_and_all_mutually_exclusive(self, tmp_path, monkeypatch):
        """--only and --all cannot be used together."""
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [
                {"id": "export-json", "name": "JSON", "format": "json",
                 "urls": ["https://example.com/export.json"]},
            ],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "download", "--only", "export-json.json", "--all"])
        assert result.exit_code != 0
```

- [ ] **Step 6: Run all new tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestMetadataDownloadJsonDefault -v`
Expected: all FAIL

- [ ] **Step 7: Implement JSON filter and `--all` flag**

In `src/tw_odc/cli.py`, modify `metadata_download`:

```python
@metadata_app.command("download")
def metadata_download(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    only: str | None = typer.Option(None, "--only", help="Download only this file"),
    all_formats: bool = typer.Option(False, "--all", help="Download all formats (default: JSON only)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
    date: str | None = typer.Option(None, "--date", help="Override {date} param (YYYY-MM-DD)"),
) -> None:
    """Download metadata files."""
    from tw_odc.fetcher import fetch_all

    if only and all_formats:
        print("Error: --only and --all are mutually exclusive", file=sys.stderr)
        raise typer.Exit(code=1)

    metadata_dir = _get_metadata_dir(ctx)
    ensure_manifest(metadata_dir)
    manifest = _load_and_check(metadata_dir, ManifestType.METADATA)

    # Filter to JSON-only by default (unless --only or --all)
    if not only and not all_formats:
        manifest = {
            **manifest,
            "datasets": [ds for ds in manifest["datasets"] if ds.get("format") == "json"],
        }

    param_overrides = {"date": date} if date else None
    asyncio.run(fetch_all(manifest, metadata_dir, only=only, no_cache=no_cache, cache_path=metadata_dir / "etags.json", param_overrides=param_overrides))

    # Rebuild search index if export-json.json exists
    export_json_path = metadata_dir / "export-json.json"
    if export_json_path.exists():
        from tw_odc.manifest import build_search_index
        build_search_index(metadata_dir)
```

- [ ] **Step 8: Run all tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestMetadataDownloadJsonDefault -v`
Expected: all PASS

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest -v`
Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py
git commit -m "feat: default metadata download to JSON-only, add --all flag"
```

---

## Chunk 2: Makefile update

### Task 2: Update Makefile daily-download target

**Files:**
- Modify: `Makefile:7-8`

- [ ] **Step 1: Update Makefile**

Change `daily-download` to use the new JSON default:

```makefile
.PHONY: daily daily-download daily-apply

# Full daily update: download → apply
daily: daily-download daily-apply

# Download JSON metadata (export + daily changes)
daily-download:
	uv run tw-odc metadata download

# Apply daily changes to existing provider manifests
daily-apply:
	uv run tw-odc metadata apply-daily
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "chore: simplify daily-download now that download defaults to JSON"
```

---

## Chunk 3: `apply-daily` auto-scaffold

### Task 3: Auto-scaffold missing providers in `apply-daily`

**Files:**
- Modify: `src/tw_odc/cli.py:331-391` (`metadata_apply_daily` function)
- Test: `tests/test_cli.py`

- [ ] **Step 0: Update existing test that will break**

The existing `test_apply_daily_updates_and_warns` asserts `"no_local_manifest"` warning for `X機關`. After auto-scaffold, this warning is replaced. Update the test in `tests/test_cli.py`:

```python
    def test_apply_daily_updates_and_warns(self, tmp_path, monkeypatch):
        """Should update existing provider and warn about missing export for unknown ones."""
        base = self._setup_providers(tmp_path)
        monkeypatch.chdir(base)

        result = runner.invoke(app, ["metadata", "apply-daily", "--date", "2026-03-10"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "a_gov_tw_12345678" in output["updated"]
        assert "created" in output
        # X機關 cannot be scaffolded (no export-json.json), so it warns
        assert any(w["provider"] == "X機關" for w in output["warnings"])
        assert any(w["reason"] == "export_json_missing" for w in output["warnings"])

        # Verify manifest was actually updated
        m = json.loads((base / "a_gov_tw_12345678" / "manifest.json").read_text())
        ids = [d["id"] for d in m["datasets"]]
        assert "1001" in ids
        assert "1002" in ids
        ds_1001 = next(d for d in m["datasets"] if d["id"] == "1001")
        assert ds_1001["name"] == "更新資料"
```

- [ ] **Step 1: Write failing test — auto-scaffold missing provider**

Add to `TestMetadataApplyDaily` in `tests/test_cli.py`:

```python
    def test_apply_daily_auto_scaffolds_missing_provider(self, tmp_path, monkeypatch):
        """Should auto-create provider manifest when provider is missing locally."""
        base = self._setup_providers(tmp_path)
        # Add export-json.json with X機關 data (needed for scaffolding)
        export_data = [
            {"提供機關": "X機關", "資料集識別碼": 9998, "資料集名稱": "既有資料",
             "檔案格式": "CSV", "資料下載網址": "https://x.gov.tw/old"},
            {"提供機關": "X機關", "資料集識別碼": 9999, "資料集名稱": "無本地",
             "檔案格式": "CSV", "資料下載網址": "https://x.gov.tw/1"},
        ]
        (tmp_path / "export-json.json").write_text(
            json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(base)

        result = runner.invoke(app, ["metadata", "apply-daily", "--date", "2026-03-10"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        # X機關 should be in created, not in warnings
        assert "created" in output
        assert any("x_gov_tw" in s for s in output["created"])
        assert not any(w.get("reason") == "no_local_manifest" for w in output["warnings"]
                       if w.get("provider") == "X機關")
        # Provider dir should exist with manifest
        created_dirs = [d for d in tmp_path.iterdir()
                        if d.is_dir() and "x_gov_tw" in d.name]
        assert len(created_dirs) == 1
        m = json.loads((created_dirs[0] / "manifest.json").read_text())
        assert m["provider"] == "X機關"
        ids = [d["id"] for d in m["datasets"]]
        assert "9998" in ids
        assert "9999" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::TestMetadataApplyDaily::test_apply_daily_auto_scaffolds_missing_provider -v`
Expected: FAIL — currently `X機關` produces a warning, no `"created"` field

- [ ] **Step 3: Write failing test — auto-scaffold with missing export-json.json**

```python
    def test_apply_daily_scaffold_warns_when_no_export_json(self, tmp_path, monkeypatch):
        """Should warn when export-json.json is missing and cannot scaffold."""
        base = self._setup_providers(tmp_path)
        # No export-json.json exists
        monkeypatch.chdir(base)

        result = runner.invoke(app, ["metadata", "apply-daily", "--date", "2026-03-10"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "created" in output
        assert output["created"] == []
        # X機關 should have a warning about missing export
        assert any(w.get("reason") == "export_json_missing" for w in output["warnings"]
                   if w.get("provider") == "X機關")
```

- [ ] **Step 4: Write failing test — provider not found in export-json.json**

```python
    def test_apply_daily_scaffold_warns_provider_not_in_export(self, tmp_path, monkeypatch):
        """Should warn when provider exists in daily but not in export-json.json."""
        base = self._setup_providers(tmp_path)
        # export-json.json exists but has no X機關
        export_data = [
            {"提供機關": "Y機關", "資料集識別碼": 8888, "資料集名稱": "其他",
             "檔案格式": "CSV", "資料下載網址": "https://y.gov.tw/1"},
        ]
        (tmp_path / "export-json.json").write_text(
            json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(base)

        result = runner.invoke(app, ["metadata", "apply-daily", "--date", "2026-03-10"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["created"] == []
        assert any(w.get("reason") == "provider_not_in_export" for w in output["warnings"]
                   if w.get("provider") == "X機關")
```

- [ ] **Step 5: Write failing test — created field always present**

```python
    def test_apply_daily_created_field_always_present(self, tmp_path, monkeypatch):
        """Output should always have 'created' field, even when empty."""
        base = self._setup_providers(tmp_path)
        # Remove X機關 from daily so no scaffolding needed
        daily = [
            {"提供機關": "A機關", "資料集識別碼": 1001, "資料集名稱": "更新",
             "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/1",
             "資料集變動狀態": "修改"},
        ]
        (tmp_path / "daily-changed-json.json").write_text(
            json.dumps(daily, ensure_ascii=False))
        monkeypatch.chdir(base)

        result = runner.invoke(app, ["metadata", "apply-daily", "--date", "2026-03-10"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "created" in output
        assert output["created"] == []
```

- [ ] **Step 6: Run all new tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestMetadataApplyDaily -v -k "scaffold or created_field"  `
Expected: all new tests FAIL

- [ ] **Step 7: Implement auto-scaffold logic**

In `src/tw_odc/cli.py`, modify `metadata_apply_daily`:

```python
@metadata_app.command("apply-daily")
def metadata_apply_daily(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    date: str | None = typer.Option(None, "--date", help="Date label for the output summary (YYYY-MM-DD); does not select a different input file"),
) -> None:
    """Apply daily changed datasets to existing provider manifests."""
    import datetime as _dt

    metadata_dir = _get_metadata_dir(ctx)
    _load_and_check(metadata_dir, ManifestType.METADATA)

    if not date:
        date = _dt.date.today().isoformat()

    daily_path = metadata_dir / "daily-changed-json.json"
    if not daily_path.exists():
        print(f"E107: {t('E107', path=daily_path)}", file=sys.stderr)
        raise typer.Exit(code=1)

    data = json.loads(daily_path.read_text(encoding="utf-8"))
    groups = group_by_provider(data)
    providers = find_existing_providers(Path.cwd())

    updated: list[str] = []
    skipped: list[str] = []
    created: list[str] = []
    warnings: list[dict] = []

    # Lazy-loaded export data for auto-scaffolding
    _export_groups: dict | None = None
    _export_loaded = False

    def _get_export_groups() -> dict | None:
        nonlocal _export_groups, _export_loaded
        if _export_loaded:
            return _export_groups
        _export_loaded = True
        export_path = metadata_dir / "export-json.json"
        if not export_path.exists():
            return None
        export_data = json.loads(export_path.read_text(encoding="utf-8"))
        _export_groups = group_by_provider(export_data)
        return _export_groups

    for provider_name, datasets in sorted(groups.items()):
        # Check for deleted datasets
        has_deleted = any(d.get("資料集變動狀態") == "刪除" for d in datasets)
        if has_deleted:
            warnings.append({"provider": provider_name, "reason": "contains_deleted_datasets"})

        # Filter to non-deleted datasets
        active = [d for d in datasets if d.get("資料集變動狀態") != "刪除"]

        if provider_name not in providers:
            # Auto-scaffold missing provider
            export_groups = _get_export_groups()
            if export_groups is None:
                warnings.append({"provider": provider_name, "reason": "export_json_missing"})
                continue
            if provider_name not in export_groups:
                warnings.append({"provider": provider_name, "reason": "provider_not_in_export"})
                continue
            slug = create_dataset_manifest(Path.cwd(), provider_name, export_groups[provider_name])
            pkg_dir = Path.cwd() / slug
            created.append(slug)
            providers[provider_name] = pkg_dir

        if not active:
            pkg_dir = providers[provider_name]
            skipped.append(pkg_dir.name)
            continue

        pkg_dir = providers[provider_name]
        parsed = [parse_dataset(d) for d in active]
        count = update_dataset_manifest(pkg_dir, parsed)
        if count > 0:
            updated.append(pkg_dir.name)
        else:
            skipped.append(pkg_dir.name)

    result = {
        "date": date,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "warnings": warnings,
    }
    _output(result, fmt)
```

- [ ] **Step 8: Run all apply-daily tests**

Run: `uv run pytest tests/test_cli.py::TestMetadataApplyDaily -v`
Expected: all PASS

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest -v`
Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py
git commit -m "feat: auto-scaffold missing providers in apply-daily"
```

---

## Chunk 4: Documentation update

### Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update command examples**

In `CLAUDE.md`, update the `metadata download` section to document `--all`:

```bash
# Download data.gov.tw exports (JSON by default)
tw-odc metadata download
tw-odc metadata download --all                      # download all formats (JSON/CSV/XML)
tw-odc metadata download --only export-json.json     # download one file only
tw-odc metadata download --no-cache                  # bypass ETag cache
tw-odc metadata download --dir /path/to/dir          # specify metadata directory
```

- [ ] **Step 2: Update pipeline description**

Update the "Incremental update" pipeline line:

```
Incremental update: `metadata download → metadata apply-daily`
```

(Remove `--only daily-changed-json.json` since the default now handles it.)

- [ ] **Step 3: Update apply-daily description**

Update the `apply-daily` command examples section to mention auto-scaffold:

```bash
# Apply daily changes to existing provider manifests (auto-creates missing providers)
tw-odc metadata apply-daily                          # uses today's date
tw-odc metadata apply-daily --date 2026-03-10        # specific date
```

- [ ] **Step 4: Update design decisions**

Add to Key Design Decisions:

```
- **JSON-first metadata**: `metadata download` defaults to JSON-only; use `--all` for CSV/XML exports
- **Auto-scaffold on daily update**: `apply-daily` automatically creates missing provider manifests from `export-json.json`
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for JSON-default download and auto-scaffold"
```

- [ ] **Step 6: Run full test suite one final time**

Run: `uv run pytest -v`
Expected: all PASS
