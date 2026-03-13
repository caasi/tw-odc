# tests/test_manifest.py
import json
import pytest
from pathlib import Path
from tw_odc.manifest import (
    load_manifest,
    ManifestType,
    group_by_provider,
    compute_slug,
    derive_slug,
    parse_dataset,
    create_dataset_manifest,
    find_existing_providers,
    update_dataset_manifest,
)


class TestLoadManifest:
    def test_load_metadata_manifest(self, tmp_path):
        m = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        result = load_manifest(tmp_path)
        assert result["type"] == "metadata"

    def test_load_dataset_manifest(self, tmp_path):
        m = {"type": "dataset", "provider": "財政部", "slug": "mof_gov_tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        result = load_manifest(tmp_path)
        assert result["type"] == "dataset"

    def test_load_missing_manifest_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path)

    def test_load_applies_patch(self, tmp_path):
        m = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [{"id": "1", "name": "A", "format": "csv", "urls": []}]
        }
        patch = [{"op": "replace", "path": "/datasets/0/format", "value": "json"}]
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        (tmp_path / "patch.json").write_text(json.dumps(patch))
        result = load_manifest(tmp_path)
        assert result["datasets"][0]["format"] == "json"

    def test_load_no_patch_file_is_ok(self, tmp_path):
        m = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(m))
        result = load_manifest(tmp_path)
        assert result["datasets"] == []


class TestDeriveSlug:
    def test_single_domain(self):
        assert derive_slug(["https://www.mof.gov.tw/a"]) == "mof_gov_tw"

    def test_strips_www(self):
        assert derive_slug(["https://www.example.gov.tw/a"]) == "example_gov_tw"

    def test_most_frequent_domain(self):
        urls = ["https://a.gov.tw/1", "https://b.gov.tw/2", "https://a.gov.tw/3"]
        assert derive_slug(urls) == "a_gov_tw"

    def test_empty(self):
        assert derive_slug([]) == ""


class TestComputeSlug:
    def test_with_urls(self):
        slug = compute_slug("財政部", ["https://mof.gov.tw/a"])
        assert slug.startswith("mof_gov_tw_")
        assert len(slug.split("_")[-1]) == 8

    def test_fallback_hash(self):
        slug = compute_slug("無網址機關", [])
        assert slug.startswith("org_")
        assert len(slug) == 20


class TestGroupByProvider:
    def test_groups(self):
        datasets = [
            {"提供機關": "A", "other": 1},
            {"提供機關": "A", "other": 2},
            {"提供機關": "B", "other": 3},
        ]
        groups = group_by_provider(datasets)
        assert len(groups["A"]) == 2
        assert len(groups["B"]) == 1


class TestParseDataset:
    def test_basic(self):
        raw = {
            "資料集識別碼": 1001,
            "資料集名稱": "測試",
            "檔案格式": "CSV",
            "資料下載網址": "https://a.gov.tw/1",
        }
        result = parse_dataset(raw)
        assert result == {
            "id": "1001",
            "name": "測試",
            "format": "csv",
            "urls": ["https://a.gov.tw/1"],
        }

    def test_multiple_urls(self):
        raw = {
            "資料集識別碼": 1002,
            "資料集名稱": "多URL",
            "檔案格式": "CSV;JSON",
            "資料下載網址": "https://a.gov.tw/1;https://a.gov.tw/2",
        }
        result = parse_dataset(raw)
        assert result["urls"] == ["https://a.gov.tw/1", "https://a.gov.tw/2"]

    def test_format_alias(self):
        raw = {
            "資料集識別碼": 1003,
            "資料集名稱": "壓縮",
            "檔案格式": "壓縮檔",
            "資料下載網址": "https://a.gov.tw/1",
        }
        result = parse_dataset(raw)
        assert result["format"] == "zip"

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


class TestCreateDatasetManifest:
    def test_creates_manifest(self, tmp_path):
        raw_datasets = [
            {
                "資料集識別碼": 1001, "資料集名稱": "測試",
                "檔案格式": "CSV", "資料下載網址": "https://test.gov.tw/a",
            },
        ]
        slug = create_dataset_manifest(tmp_path, "測試機關", raw_datasets)
        assert slug.startswith("test_gov_tw_")
        manifest_path = tmp_path / slug / "manifest.json"
        assert manifest_path.exists()
        m = json.loads(manifest_path.read_text())
        assert m["type"] == "dataset"
        assert m["provider"] == "測試機關"
        assert len(m["datasets"]) == 1

    def test_update_existing_manifest(self, tmp_path):
        raw1 = [{"資料集識別碼": 1, "資料集名稱": "A", "檔案格式": "CSV", "資料下載網址": "https://t.gov.tw/a"}]
        slug = create_dataset_manifest(tmp_path, "T", raw1)
        raw2 = [
            {"資料集識別碼": 1, "資料集名稱": "A", "檔案格式": "CSV", "資料下載網址": "https://t.gov.tw/a"},
            {"資料集識別碼": 2, "資料集名稱": "B", "檔案格式": "JSON", "資料下載網址": "https://t.gov.tw/b"},
        ]
        slug2 = create_dataset_manifest(tmp_path, "T", raw2)
        assert slug == slug2
        m = json.loads((tmp_path / slug / "manifest.json").read_text())
        assert len(m["datasets"]) == 2


class TestFindExistingProviders:
    def test_finds_providers(self, tmp_path):
        """Should find all subdirectories with dataset manifest.json."""
        pkg1 = tmp_path / "provider_a"
        pkg1.mkdir()
        (pkg1 / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a", "datasets": [],
        }))
        pkg2 = tmp_path / "provider_b"
        pkg2.mkdir()
        (pkg2 / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "B機關", "slug": "provider_b", "datasets": [],
        }))
        # Root manifest should not be included
        (tmp_path / "manifest.json").write_text(json.dumps({
            "type": "metadata", "provider": "data.gov.tw", "datasets": [],
        }))

        result = find_existing_providers(tmp_path)
        assert "A機關" in result
        assert "B機關" in result
        assert result["A機關"] == pkg1
        assert result["B機關"] == pkg2

    def test_empty_dir(self, tmp_path):
        """No subdirectories → empty dict."""
        assert find_existing_providers(tmp_path) == {}

    def test_ignores_non_dataset_manifests(self, tmp_path):
        """Subdirectories with metadata-type manifest should be ignored."""
        pkg = tmp_path / "sub"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "metadata", "provider": "data.gov.tw", "datasets": [],
        }))
        assert find_existing_providers(tmp_path) == {}


class TestUpdateDatasetManifest:
    def test_merges_new_datasets(self, tmp_path):
        """New datasets should be added to existing manifest."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "既有", "format": "csv", "urls": ["https://a.tw/1"]},
            ],
        }))
        changed = [
            {"id": "1002", "name": "新增", "format": "json", "urls": ["https://a.tw/2"]},
        ]
        count = update_dataset_manifest(pkg, changed)
        assert count == 1
        m = json.loads((pkg / "manifest.json").read_text())
        assert len(m["datasets"]) == 2
        ids = [d["id"] for d in m["datasets"]]
        assert "1001" in ids
        assert "1002" in ids

    def test_updates_existing_dataset(self, tmp_path):
        """Existing dataset with same id should be overwritten."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "舊名", "format": "csv", "urls": ["https://a.tw/old"]},
            ],
        }))
        changed = [
            {"id": "1001", "name": "新名", "format": "json", "urls": ["https://a.tw/new"]},
        ]
        count = update_dataset_manifest(pkg, changed)
        assert count == 1
        m = json.loads((pkg / "manifest.json").read_text())
        assert len(m["datasets"]) == 1
        assert m["datasets"][0]["name"] == "新名"
        assert m["datasets"][0]["format"] == "json"

    def test_no_changes_returns_zero(self, tmp_path):
        """If changed datasets are empty, nothing should change."""
        pkg = tmp_path / "provider_a"
        pkg.mkdir()
        (pkg / "manifest.json").write_text(json.dumps({
            "type": "dataset", "provider": "A機關", "slug": "provider_a",
            "datasets": [
                {"id": "1001", "name": "既有", "format": "csv", "urls": ["https://a.tw/1"]},
            ],
        }))
        count = update_dataset_manifest(pkg, [])
        assert count == 0
        m = json.loads((pkg / "manifest.json").read_text())
        assert len(m["datasets"]) == 1

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
