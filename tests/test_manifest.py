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
        assert compute_slug("財政部", ["https://mof.gov.tw/a"]) == "mof_gov_tw"

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


class TestCreateDatasetManifest:
    def test_creates_manifest(self, tmp_path):
        raw_datasets = [
            {
                "資料集識別碼": 1001, "資料集名稱": "測試",
                "檔案格式": "CSV", "資料下載網址": "https://test.gov.tw/a",
            },
        ]
        slug = create_dataset_manifest(tmp_path, "測試機關", raw_datasets)
        assert slug == "test_gov_tw"
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
