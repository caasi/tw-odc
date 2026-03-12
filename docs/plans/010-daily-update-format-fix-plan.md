# 010 — 修正 daily update 格式覆寫問題 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 `apply-daily` 將 dataset format 覆寫成 `"bin"` 的 bug，改用 field-level merge 保留既有格式。

**Architecture:** `parse_dataset()` 回傳 `None` 取代 `"bin"` fallback → `update_dataset_manifest()` 做 field-level merge 跳過 `None` 欄位 → `fetcher.py` 和 `inspector.py` 在消費端處理 `None` format。

**Tech Stack:** Python 3.13, pytest, uv

---

## Chunk 1: parse_dataset 和 update_dataset_manifest

### Task 1: parse_dataset 空格式回傳 None

**Files:**
- Modify: `tw_odc/manifest.py:79-92`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write failing test — empty format returns None**

在 `tests/test_manifest.py` 的 `TestParseDataset` class 末尾加：

```python
    def test_empty_format_returns_none(self):
        raw = {
            "資料集識別碼": 1004,
            "資料集名稱": "無格式",
            "檔案格式": None,
            "資料下載網址": "https://a.gov.tw/1",
        }
        result = parse_dataset(raw)
        assert result["format"] is None

    def test_empty_string_format_returns_none(self):
        raw = {
            "資料集識別碼": 1005,
            "資料集名稱": "空字串格式",
            "檔案格式": "",
            "資料下載網址": "https://a.gov.tw/1",
        }
        result = parse_dataset(raw)
        assert result["format"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manifest.py::TestParseDataset::test_empty_format_returns_none tests/test_manifest.py::TestParseDataset::test_empty_string_format_returns_none -v`

Expected: FAIL — `assert 'bin' is None`

- [ ] **Step 3: Implement — change fallback from "bin" to None**

In `tw_odc/manifest.py`, line 85:

```python
# before
fmt = formats[0].lower() if formats else "bin"
# after
fmt = formats[0].lower() if formats else None
```

And line 86, guard the alias lookup:

```python
# before
fmt = FORMAT_ALIASES.get(fmt, fmt)
# after
if fmt is not None:
    fmt = FORMAT_ALIASES.get(fmt, fmt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manifest.py::TestParseDataset -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tw_odc/manifest.py tests/test_manifest.py
git commit -m "fix: parse_dataset returns None for empty format instead of bin"
```

### Task 2: update_dataset_manifest field-level merge

**Files:**
- Modify: `tw_odc/manifest.py:139-159`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write failing test — None format preserves existing**

在 `tests/test_manifest.py` 的 `TestUpdateDatasetManifest` class 末尾加：

```python
    def test_none_format_preserves_existing(self, tmp_path):
        """When changed dataset has format=None, existing format should be preserved."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "舊名", "format": "csv", "urls": ["https://a.tw/1"]},
            ],
        }))
        changed = [
            {"id": "1001", "name": "新名", "format": None, "urls": []},
        ]
        count = update_dataset_manifest(pkg, changed)
        assert count == 1
        m = json.loads((pkg / "manifest.json").read_text())
        ds = m["datasets"][0]
        assert ds["name"] == "新名"
        assert ds["format"] == "csv"  # preserved
        assert ds["urls"] == ["https://a.tw/1"]  # preserved (empty urls)
```

- [ ] **Step 2: Write failing test — non-None format updates existing**

```python
    def test_non_none_format_updates_existing(self, tmp_path):
        """When changed dataset has a real format, it should update."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "舊名", "format": "csv", "urls": ["https://a.tw/1"]},
            ],
        }))
        changed = [
            {"id": "1001", "name": "新名", "format": "json", "urls": ["https://a.tw/new"]},
        ]
        count = update_dataset_manifest(pkg, changed)
        assert count == 1
        m = json.loads((pkg / "manifest.json").read_text())
        ds = m["datasets"][0]
        assert ds["format"] == "json"
        assert ds["urls"] == ["https://a.tw/new"]
```

- [ ] **Step 3: Write failing test — new dataset with None format is added as-is**

```python
    def test_new_dataset_with_none_format(self, tmp_path):
        """New datasets (not in existing manifest) should be added as-is, even with None format."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "既有", "format": "csv", "urls": ["https://a.tw/1"]},
            ],
        }))
        changed = [
            {"id": "1002", "name": "新增", "format": None, "urls": []},
        ]
        count = update_dataset_manifest(pkg, changed)
        assert count == 1
        m = json.loads((pkg / "manifest.json").read_text())
        assert len(m["datasets"]) == 2
        new_ds = [d for d in m["datasets"] if d["id"] == "1002"][0]
        assert new_ds["format"] is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_manifest.py::TestUpdateDatasetManifest -v`

Expected: `test_none_format_preserves_existing` FAIL — format becomes `None` instead of `"csv"`

- [ ] **Step 5: Implement field-level merge**

In `tw_odc/manifest.py`, replace lines 146-152 (from `existing = ...` through the end of the `for` loop). Keep lines 154-159 (the `if count > 0` write-back block and `return count`) unchanged.

```python
    existing = {str(d["id"]): d for d in manifest["datasets"]}
    count = 0
    for ds in changed_datasets:
        ds_id = str(ds["id"])
        if ds_id in existing:
            old = existing[ds_id]
            merged = {**old}
            merged["name"] = ds["name"]
            if ds.get("format") is not None:
                merged["format"] = ds["format"]
            if ds.get("urls"):
                merged["urls"] = ds["urls"]
            if merged != existing[ds_id]:
                existing[ds_id] = merged
                count += 1
        else:
            existing[ds_id] = ds
            count += 1
```

- [ ] **Step 6: Run all manifest tests**

Run: `uv run pytest tests/test_manifest.py -v`

Expected: all PASS (including existing tests)

- [ ] **Step 7: Commit**

```bash
git add tw_odc/manifest.py tests/test_manifest.py
git commit -m "fix: update_dataset_manifest uses field-level merge, preserves existing format on None"
```

## Chunk 2: fetcher 和 inspector 的 None format 處理

### Task 3: fetcher _dest_filename handles None format

**Files:**
- Modify: `tw_odc/fetcher.py:45-55`
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: Write failing test**

在 `tests/test_fetcher.py` 加：

```python
def test_dest_filename_none_format_falls_back_to_bin():
    """When format is None, filename should use 'bin' as extension."""
    result = _dest_filename({"id": "1001", "format": None}, 0, 1)
    assert result == "1001.bin"


def test_dest_filename_none_format_multi_url():
    """When format is None with multiple URLs, filename should use 'bin' as extension."""
    result = _dest_filename({"id": "1001", "format": None}, 0, 2)
    assert result == "1001-1.bin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fetcher.py::test_dest_filename_none_format_falls_back_to_bin tests/test_fetcher.py::test_dest_filename_none_format_multi_url -v`

Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'lower'`

- [ ] **Step 3: Implement None fallback**

In `tw_odc/fetcher.py`, line 47:

```python
# before
fmt = dataset["format"].lower()
# after
fmt = (dataset["format"] or "bin").lower()
```

- [ ] **Step 4: Run all fetcher tests**

Run: `uv run pytest tests/test_fetcher.py -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tw_odc/fetcher.py tests/test_fetcher.py
git commit -m "fix: fetcher falls back to bin extension when dataset format is None"
```

### Task 4: inspector handles None format

**Files:**
- Modify: `tw_odc/inspector.py:131-217`
- Test: `tests/test_inspector.py`

- [ ] **Step 1: Write failing test — None format uses bin filename, adds FORMAT_UNDECLARED, skips FORMAT_MISMATCH**

在 `tests/test_inspector.py` 的 `TestInspectDataset` class 末尾加：

```python
    def test_none_format_uses_bin_filename(self, tmp_path):
        """When format is None, should look for {id}.bin file."""
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.bin").write_text("a,b\n1,2\n")

        dataset = {"id": "1001", "name": "Undeclared", "format": None, "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.declared_format == "bin"
        assert result.file_exists is True
        assert result.detected_formats == ["csv"]
        assert "FORMAT_UNDECLARED" in result.issues
        assert "FORMAT_MISMATCH" not in result.issues

    def test_none_format_missing_file(self, tmp_path):
        """When format is None and file doesn't exist, should still report correctly."""
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()

        dataset = {"id": "9999", "name": "Missing", "format": None, "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.declared_format == "bin"
        assert result.file_exists is False
        assert "DOWNLOAD_FAILED" in result.issues
        assert "FORMAT_UNDECLARED" in result.issues
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_inspector.py::TestInspectDataset::test_none_format_uses_bin_filename tests/test_inspector.py::TestInspectDataset::test_none_format_missing_file -v`

Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'lower'`

- [ ] **Step 3: Implement None format handling in inspect_dataset**

In `tw_odc/inspector.py`, replace lines 141-149:

```python
    dataset_id = str(dataset["id"])
    declared_fmt = (dataset["format"] or "bin").lower()
    format_undeclared = dataset["format"] is None
    urls = dataset["urls"]
    url_count = len(urls)

    if not _SAFE_ID_RE.match(dataset_id):
        raise ValueError(f"Unsafe dataset id: {dataset_id!r}")
    if not _SAFE_FMT_RE.match(declared_fmt):
        raise ValueError(f"Unsafe dataset format: {declared_fmt!r}")
```

Then, after the FORMAT_MISMATCH block (after line 196), before the PDF check, add `FORMAT_UNDECLARED` and guard FORMAT_MISMATCH:

Replace the FORMAT_MISMATCH block (lines 191-196):

```python
    # Format mismatch: declared vs detected (skip for ZIP and undeclared formats)
    if not format_undeclared and declared_fmt != "zip" and any_exists:
        for fmt in detected_formats:
            if fmt not in ("missing", "empty") and fmt != declared_fmt:
                issues.append("FORMAT_MISMATCH")
                break

    if format_undeclared:
        issues.append("FORMAT_UNDECLARED")
```

- [ ] **Step 4: Run all inspector tests**

Run: `uv run pytest tests/test_inspector.py -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tw_odc/inspector.py tests/test_inspector.py
git commit -m "fix: inspector handles None format with bin fallback and FORMAT_UNDECLARED issue"
```

## Chunk 3: 整合驗證

### Task 5: Full integration test

**Files:**
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write integration test — end-to-end daily update flow**

在 `tests/test_manifest.py` 的 `TestUpdateDatasetManifest` class 末尾加：

```python
    def test_daily_update_flow_preserves_format(self, tmp_path):
        """Simulate full daily update: parse_dataset with null format → merge preserves existing."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "舊名", "format": "csv", "urls": ["https://a.tw/1"]},
                {"id": "1002", "name": "JSON資料", "format": "json", "urls": ["https://a.tw/2"]},
            ],
        }))
        # Simulate daily-changed-json.json entries (format is always null)
        daily_changed = [
            {
                "資料集識別碼": 1001,
                "資料集名稱": "新名",
                "檔案格式": None,
                "資料下載網址": "",
            },
        ]
        parsed = [parse_dataset(d) for d in daily_changed]
        count = update_dataset_manifest(pkg, parsed)
        assert count == 1
        m = json.loads((pkg / "manifest.json").read_text())
        ds_map = {d["id"]: d for d in m["datasets"]}
        assert ds_map["1001"]["name"] == "新名"
        assert ds_map["1001"]["format"] == "csv"  # preserved!
        assert ds_map["1001"]["urls"] == ["https://a.tw/1"]  # preserved!
        assert ds_map["1002"]["format"] == "json"  # untouched
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/test_manifest.py::TestUpdateDatasetManifest::test_daily_update_flow_preserves_format -v`

Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_manifest.py
git commit -m "test: add integration test for daily update format preservation"
```
