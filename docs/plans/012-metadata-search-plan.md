# 012 — metadata search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `tw-odc metadata search <keywords...>` command that searches export-json metadata by keyword, using a slim JSONL index for fast (~0.06s) lookups.

**Architecture:** Two pieces: (1) search index generation in `tw_odc/manifest.py` — reads `export-json.json`, writes `export-search.jsonl` with only search-relevant fields; (2) `metadata_search` command in `tw_odc/cli.py` — reads the JSONL index line by line, matches raw text before parsing JSON, outputs results. `metadata download` calls index generation after downloading `export-json.json`.

**Tech Stack:** Python 3.13, typer, stdlib json only (no new dependencies)

---

### Task 1: Add search index generation with tests

**Files:**
- Modify: `src/tw_odc/manifest.py`
- Modify: `tests/test_manifest.py`

**Step 1: Write failing tests**

Add to `tests/test_manifest.py`:

```python
class TestBuildSearchIndex:
    def test_generates_jsonl(self, tmp_path):
        """build_search_index creates export-search.jsonl from export-json.json."""
        export_data = [
            {
                "資料集識別碼": 12345,
                "資料集名稱": "臺中市工廠登記清冊",
                "提供機關": "臺中市政府經濟發展局",
                "資料集描述": "工廠登記資料",
                "檔案格式": "CSV",
                "資料下載網址": "https://example.com/a.csv",
            },
            {
                "資料集識別碼": 67890,
                "資料集名稱": "國防部新聞稿",
                "提供機關": "國防部",
                "資料集描述": "新聞稿資料",
                "檔案格式": "XML",
                "資料下載網址": "https://example.com/b.xml",
            },
        ]
        export_path = tmp_path / "export-json.json"
        export_path.write_text(json.dumps(export_data, ensure_ascii=False))

        from tw_odc.manifest import build_search_index
        index_path = build_search_index(tmp_path)

        assert index_path == tmp_path / "export-search.jsonl"
        assert index_path.exists()

        lines = index_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert first["id"] == 12345
        assert first["name"] == "臺中市工廠登記清冊"
        assert first["provider"] == "臺中市政府經濟發展局"
        assert first["desc"] == "工廠登記資料"
        assert first["format"] == "CSV"

    def test_only_includes_search_fields(self, tmp_path):
        """Index entries should not include URL, encoding, or other fields."""
        export_data = [{
            "資料集識別碼": 1,
            "資料集名稱": "Test",
            "提供機關": "Agency",
            "資料集描述": "Desc",
            "檔案格式": "JSON",
            "資料下載網址": "https://example.com/data.json",
            "編碼格式": "UTF-8",
            "品質檢測": "白金",
        }]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data))

        from tw_odc.manifest import build_search_index
        build_search_index(tmp_path)

        entry = json.loads((tmp_path / "export-search.jsonl").read_text().strip())
        assert set(entry.keys()) == {"id", "name", "provider", "desc", "format"}

    def test_missing_export_json_raises(self, tmp_path):
        """build_search_index raises FileNotFoundError when export-json.json is missing."""
        from tw_odc.manifest import build_search_index

        with pytest.raises(FileNotFoundError):
            build_search_index(tmp_path)

    def test_overwrites_existing_index(self, tmp_path):
        """Calling build_search_index again overwrites the previous index."""
        export_data = [{"資料集識別碼": 1, "資料集名稱": "A", "提供機關": "B", "資料集描述": "C", "檔案格式": "CSV", "資料下載網址": "https://x"}]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data))
        (tmp_path / "export-search.jsonl").write_text("old data\n")

        from tw_odc.manifest import build_search_index
        build_search_index(tmp_path)

        lines = (tmp_path / "export-search.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        assert "old data" not in lines[0]
```

**Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_manifest.py::TestBuildSearchIndex -v`
Expected: FAIL — `build_search_index` doesn't exist yet

**Step 3: Implement build_search_index**

Add to `src/tw_odc/manifest.py`:

```python
def build_search_index(metadata_dir: Path) -> Path:
    """Build export-search.jsonl from export-json.json.

    Extracts only search-relevant fields (id, name, provider, desc, format)
    into a JSONL file for fast line-by-line text matching.
    """
    export_path = metadata_dir / "export-json.json"
    if not export_path.exists():
        raise FileNotFoundError(f"export-json.json not found in {metadata_dir}")

    index_path = metadata_dir / "export-search.jsonl"
    data = json.loads(export_path.read_text(encoding="utf-8"))

    with open(index_path, "w", encoding="utf-8") as f:
        for ds in data:
            entry = {
                "id": ds.get("資料集識別碼", ""),
                "name": ds.get("資料集名稱", ""),
                "provider": ds.get("提供機關", ""),
                "desc": ds.get("資料集描述", ""),
                "format": ds.get("檔案格式", ""),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return index_path
```

**Step 4: Run tests**

Run: `uv run python -m pytest tests/test_manifest.py::TestBuildSearchIndex -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/tw_odc/manifest.py tests/test_manifest.py
git commit -m "feat: add build_search_index for slim JSONL generation"
```

---

### Task 2: Integrate index generation into metadata download

**Files:**
- Modify: `src/tw_odc/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write failing test**

Add to `tests/test_cli.py`:

```python
def test_metadata_download_generates_search_index(tmp_path, monkeypatch):
    """metadata download should generate export-search.jsonl after downloading export-json.json."""
    # Set up metadata dir with manifest
    manifest = {
        "type": "metadata",
        "provider": "data.gov.tw",
        "datasets": [{"id": "export-json", "name": "JSON export", "format": "json",
                       "urls": ["https://example.com/export.json"]}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    # Simulate already-downloaded export-json.json
    export_data = [{"資料集識別碼": 1, "資料集名稱": "Test", "提供機關": "A", "資料集描述": "D", "檔案格式": "CSV", "資料下載網址": "https://x"}]
    (tmp_path / "export-json.json").write_text(json.dumps(export_data))
    monkeypatch.chdir(tmp_path)

    # Mock fetch_all to be a no-op (file already exists)
    with patch("tw_odc.cli.fetch_all", new_callable=AsyncMock):
        result = runner.invoke(app, ["metadata", "download"])

    assert result.exit_code == 0
    assert (tmp_path / "export-search.jsonl").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_cli.py::test_metadata_download_generates_search_index -v`
Expected: FAIL

**Step 3: Implement**

In `src/tw_odc/cli.py`, modify `metadata_download` to call `build_search_index` after `fetch_all`:

```python
@metadata_app.command("download")
def metadata_download(
    ctx: typer.Context,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
    only: str | None = typer.Option(None, "--only", help="Download only this file"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass ETag cache"),
    date: str | None = typer.Option(None, "--date", help="Override {date} param (YYYY-MM-DD)"),
) -> None:
    """Download metadata files."""
    from tw_odc.fetcher import fetch_all

    metadata_dir = _get_metadata_dir(ctx)
    ensure_manifest(metadata_dir)
    manifest = _load_and_check(metadata_dir, ManifestType.METADATA)
    param_overrides = {"date": date} if date else None
    asyncio.run(fetch_all(manifest, metadata_dir, only=only, no_cache=no_cache, cache_path=metadata_dir / "etags.json", param_overrides=param_overrides))

    # Rebuild search index if export-json.json exists
    export_json_path = metadata_dir / "export-json.json"
    if export_json_path.exists():
        from tw_odc.manifest import build_search_index
        build_search_index(metadata_dir)
```

Add `build_search_index` to the import block at top of cli.py if not using lazy import (the above uses lazy import inside the function, consistent with `fetch_all`).

**Step 4: Run tests**

Run: `uv run python -m pytest tests/test_cli.py::test_metadata_download_generates_search_index -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py
git commit -m "feat: generate search index after metadata download"
```

---

### Task 3: Add metadata search command with tests

**Files:**
- Modify: `src/tw_odc/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `src/tw_odc/locales/en.json`
- Modify: `src/tw_odc/locales/zh-TW.json`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestMetadataSearch:
    @pytest.fixture()
    def search_dir(self, tmp_path):
        """Set up metadata dir with search index."""
        manifest = {
            "type": "metadata", "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON", "format": "json",
                           "urls": ["https://example.com/export.json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        # Write slim JSONL index directly
        entries = [
            {"id": 1, "name": "臺中市工廠登記清冊", "provider": "臺中市政府經濟發展局", "desc": "工廠登記資料", "format": "CSV"},
            {"id": 2, "name": "臺南市工廠登記清冊", "provider": "臺南市政府經濟發展局", "desc": "工廠登記資料", "format": "JSON"},
            {"id": 3, "name": "國防部新聞稿", "provider": "國防部", "desc": "即時新聞", "format": "XML"},
            {"id": 4, "name": "政府採購統計", "provider": "行政院公共工程委員會", "desc": "廠商採購資料", "format": "CSV"},
        ]
        index_path = tmp_path / "export-search.jsonl"
        with open(index_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return tmp_path

    def test_single_keyword(self, search_dir, monkeypatch):
        """Single keyword matches across all fields."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search", "國防"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "國防部新聞稿"

    def test_multiple_keywords_and(self, search_dir, monkeypatch):
        """Multiple keywords use AND logic."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search", "臺中", "工廠登記"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["provider"] == "臺中市政府經濟發展局"

    def test_cross_field_and(self, search_dir, monkeypatch):
        """Keywords can match across different fields."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search", "工程委員會", "廠商"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == 4

    def test_no_results(self, search_dir, monkeypatch):
        """No matches returns empty list."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search", "不存在的關鍵字"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_field_filter_provider(self, search_dir, monkeypatch):
        """--field provider restricts search to provider name only."""
        monkeypatch.chdir(search_dir)
        # "工廠登記" appears in name and desc, but not provider
        result = runner.invoke(app, ["metadata", "search", "工廠登記", "--field", "provider"])
        data = json.loads(result.output)
        assert len(data) == 0

    def test_field_filter_name(self, search_dir, monkeypatch):
        """--field name restricts search to dataset name."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search", "工廠登記", "--field", "name"])
        data = json.loads(result.output)
        assert len(data) == 2  # 臺中 + 臺南

    def test_text_format(self, search_dir, monkeypatch):
        """--format text outputs tab-separated lines."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search", "國防", "--format", "text"])
        assert result.exit_code == 0
        assert "國防部新聞稿" in result.output
        assert "國防部" in result.output

    def test_fallback_to_export_json(self, search_dir, monkeypatch):
        """Falls back to export-json.json when index is missing."""
        monkeypatch.chdir(search_dir)
        # Remove index, create export-json.json instead
        (search_dir / "export-search.jsonl").unlink()
        export_data = [
            {"資料集識別碼": 99, "資料集名稱": "測試資料集", "提供機關": "測試機關", "資料集描述": "測試", "檔案格式": "CSV", "資料下載網址": "https://x"},
        ]
        (search_dir / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))

        result = runner.invoke(app, ["metadata", "search", "測試"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "測試資料集"

    def test_no_keywords_shows_error(self, search_dir, monkeypatch):
        """search with no keywords should error."""
        monkeypatch.chdir(search_dir)
        result = runner.invoke(app, ["metadata", "search"])
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_cli.py::TestMetadataSearch -v`
Expected: FAIL — `search` command doesn't exist yet

**Step 3: Add i18n keys**

In `src/tw_odc/locales/en.json`, add:
```json
"search.count": "Found %{count} datasets",
"E009": "export-search.jsonl and export-json.json not found in %{path}; run 'tw-odc metadata download' first"
```

In `src/tw_odc/locales/zh-TW.json`, add:
```json
"search.count": "找到 %{count} 筆資料集",
"E009": "%{path} 中找不到 export-search.jsonl 和 export-json.json；請先執行 'tw-odc metadata download'"
```

**Step 4: Implement metadata_search command**

Add to `src/tw_odc/cli.py`, after `metadata_list`:

```python
@metadata_app.command("search")
def metadata_search(
    ctx: typer.Context,
    keywords: Annotated[list[str], typer.Argument(help="Search keywords (AND logic)")],
    field: Annotated[Optional[list[str]], typer.Option("--field", help="Restrict to field: provider, name, desc")] = None,
    fmt: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format"),
) -> None:
    """Search datasets in metadata by keyword."""
    metadata_dir = _get_metadata_dir(ctx)
    index_path = metadata_dir / "export-search.jsonl"
    export_path = metadata_dir / "export-json.json"

    keywords_lower = [k.lower() for k in keywords]
    valid_fields = {"provider", "name", "desc"}
    if field:
        for f in field:
            if f not in valid_fields:
                print(f"Error: --field must be one of: {', '.join(sorted(valid_fields))}", file=sys.stderr)
                raise typer.Exit(code=1)

    results: list[dict] = []

    if index_path.exists():
        # Fast path: slim JSONL
        with open(index_path, encoding="utf-8") as f:
            for line in f:
                line_lower = line.lower()
                if not all(k in line_lower for k in keywords_lower):
                    continue
                entry = json.loads(line)
                if field:
                    haystack = " ".join(str(entry.get(f, "")) for f in field).lower()
                    if not all(k in haystack for k in keywords_lower):
                        continue
                results.append(entry)
    elif export_path.exists():
        # Fallback: full JSON parse
        data = json.loads(export_path.read_text(encoding="utf-8"))
        for ds in data:
            entry = {
                "id": ds.get("資料集識別碼", ""),
                "name": ds.get("資料集名稱", ""),
                "provider": ds.get("提供機關", ""),
                "desc": ds.get("資料集描述", ""),
                "format": ds.get("檔案格式", ""),
            }
            if field:
                haystack = " ".join(str(entry.get(f, "")) for f in field).lower()
            else:
                haystack = " ".join(str(v) for v in entry.values()).lower()
            if all(k in haystack for k in keywords_lower):
                results.append(entry)
    else:
        print(f"E009: {t('E009', path=metadata_dir)}", file=sys.stderr)
        raise typer.Exit(code=1)

    # Sort by provider, then id
    results.sort(key=lambda r: (str(r.get("provider", "")), str(r.get("id", ""))))

    print(t("search.count", count=len(results)), file=sys.stderr)
    _output(results, fmt)
```

**Step 5: Run tests**

Run: `uv run python -m pytest tests/test_cli.py::TestMetadataSearch -v`
Expected: ALL PASS

**Step 6: Run full test suite**

Run: `uv run python -m pytest -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/tw_odc/cli.py tests/test_cli.py src/tw_odc/locales/en.json src/tw_odc/locales/zh-TW.json
git commit -m "feat: add metadata search command with slim JSONL index"
```

---

### Task 4: Update gitignore and documentation

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Step 1: Add export-search.jsonl to .gitignore**

Add after the existing export-json/csv/xml lines:
```
/export-search.jsonl
```

**Step 2: Update README.md**

Add `metadata search` examples to the 使用方式 section (after metadata list):

```markdown
# 搜尋資料集
tw-odc metadata search 國防
tw-odc metadata search 臺中 工廠登記
tw-odc metadata search 廠商 --field name
tw-odc metadata search 國防 --format text
```

**Step 3: Update CLAUDE.md**

Add to the Commands section:

```markdown
# Search datasets in metadata
tw-odc metadata search <keywords...>
tw-odc metadata search 國防 採購                    # multiple keywords (AND)
tw-odc metadata search 臺中 --field provider        # restrict to provider name
tw-odc metadata search 工廠登記 --format text        # human-readable output
```

Add to Key Design Decisions:
```
- **Search index**: `metadata download` generates `export-search.jsonl` (slim JSONL with search fields only) for fast (~0.06s) keyword search; `metadata search` falls back to full `export-json.json` parsing if index is missing
```

**Step 4: Commit**

```bash
git add .gitignore README.md CLAUDE.md
git commit -m "docs: add metadata search to README, CLAUDE.md, and gitignore"
```

---

### Task 5: Manual smoke test

Not a code task. Verify end-to-end:

```bash
# Regenerate index from existing export-json.json
tw-odc metadata download --only export-json.json

# Verify index exists
ls -lh export-search.jsonl

# Search tests
tw-odc metadata search 國防
tw-odc metadata search 臺中 工廠登記
tw-odc metadata search 廠商 --field name
tw-odc metadata search 採購 --format text
tw-odc metadata search 不存在的東西

# Verify fallback: remove index, search should still work (slower)
rm export-search.jsonl
tw-odc metadata search 國防
```
