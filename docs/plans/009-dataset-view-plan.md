# dataset view Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `tw-odc dataset view --id <id>` command that outputs raw downloaded file content to stdout for piping to external tools.

**Architecture:** New `dataset_view` command in `tw_odc/cli.py`. Resolves filenames using the same convention as `inspect_dataset` (single URL → `{id}.{fmt}`, multi-URL → `{id}-{n}.{fmt}`). Writes raw bytes to stdout; for multi-file datasets, prints filenames to stderr so stdout stays clean for piping.

**Tech Stack:** Python 3.13, typer, existing CLI infrastructure

---

### Task 1: Add dataset view command with tests

**Files:**
- Modify: `tw_odc/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestDatasetView:
    def test_view_single_file(self, tmp_path, monkeypatch):
        """View outputs raw file content to stdout."""
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001.csv").write_text("a,b\n1,2\n")
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "view", "--id", "1001"])
        assert result.exit_code == 0
        assert result.output == "a,b\n1,2\n"

    def test_view_multi_file(self, tmp_path, monkeypatch):
        """Multi-file dataset outputs all files sequentially."""
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv",
                          "urls": ["http://x/1", "http://x/2"]}],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001-1.csv").write_text("a,b\n1,2\n")
        (ds_dir / "1001-2.csv").write_text("a,b\n3,4\n")
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "view", "--id", "1001"])
        assert result.exit_code == 0
        assert "a,b\n1,2\n" in result.output
        assert "a,b\n3,4\n" in result.output

    def test_view_missing_file(self, tmp_path, monkeypatch):
        """View errors when dataset files are not downloaded."""
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        (pkg_dir / "datasets").mkdir()
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "view", "--id", "1001"])
        assert result.exit_code != 0

    def test_view_id_not_found(self, tmp_path, monkeypatch):
        """View errors when dataset ID not in manifest."""
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "view", "--id", "9999"])
        assert result.exit_code != 0
        assert "E006" in result.output

    def test_view_requires_id(self, tmp_path, monkeypatch):
        """View requires --id option."""
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1001", "name": "D", "format": "csv", "urls": ["http://x"]}],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "view"])
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_cli.py::TestDatasetView -v`
Expected: FAIL — `view` command doesn't exist yet

**Step 3: Implement dataset_view command**

Add to `tw_odc/cli.py`, before the `dataset_clean` command:

```python
@dataset_app.command("view")
def dataset_view(
    ctx: typer.Context,
    dataset_id: str = typer.Option(..., "--id", help="Dataset ID to view"),
) -> None:
    """Output raw dataset file content to stdout."""
    pkg_dir = _get_dataset_dir(ctx)
    manifest = _load_and_check(pkg_dir, ManifestType.DATASET)
    datasets_dir = pkg_dir / "datasets"

    matched = [ds for ds in manifest["datasets"] if str(ds["id"]) == dataset_id]
    if not matched:
        print(f"E006: {t('E006', id=dataset_id)}", file=sys.stderr)
        raise typer.Exit(code=1)

    ds = matched[0]
    url_count = len(ds["urls"])
    fmt = ds["format"].lower()
    found_any = False

    for i in range(url_count):
        if url_count == 1:
            filename = f"{dataset_id}.{fmt}"
        else:
            filename = f"{dataset_id}-{i + 1}.{fmt}"

        file_path = datasets_dir / filename
        if not file_path.exists():
            continue

        found_any = True
        if url_count > 1:
            print(f"--- {filename} ---", file=sys.stderr)
        sys.stdout.buffer.write(file_path.read_bytes())

    if not found_any:
        print(f"E008: {t('E008', id=dataset_id)}", file=sys.stderr)
        raise typer.Exit(code=1)
```

Add i18n key `E008` to both locale files:

In `tw_odc/locales/en.json`:
```json
"E008": "No downloaded files found for dataset %{id}; run 'tw-odc dataset download --id %{id}' first"
```

In `tw_odc/locales/zh-TW.json`:
```json
"E008": "找不到資料集 %{id} 的下載檔案；請先執行 'tw-odc dataset download --id %{id}'"
```

**Step 4: Run tests**

Run: `uv run python -m pytest tests/test_cli.py::TestDatasetView -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `uv run python -m pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add tw_odc/cli.py tests/test_cli.py tw_odc/locales/en.json tw_odc/locales/zh-TW.json
git commit -m "feat: add dataset view command for raw content output"
```
