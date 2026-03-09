import json
from pathlib import Path

import pytest

from shared.scaffold import derive_slug, group_by_provider, scaffold_provider


def test_derive_slug_single_domain():
    urls = ["https://www.mofti.gov.tw/download/abc", "https://www.mofti.gov.tw/download/def"]
    assert derive_slug(urls) == "mofti_gov_tw"


def test_derive_slug_strips_www():
    urls = ["https://www.example.gov.tw/data"]
    assert derive_slug(urls) == "example_gov_tw"


def test_derive_slug_multiple_domains_picks_most_frequent():
    urls = [
        "https://a.gov.tw/1",
        "https://b.gov.tw/2",
        "https://a.gov.tw/3",
    ]
    assert derive_slug(urls) == "a_gov_tw"


def test_derive_slug_strips_port():
    urls = ["https://api.example.com:8080/data"]
    assert derive_slug(urls) == "api_example_com"


def test_derive_slug_fallback_empty():
    assert derive_slug([]) == ""


def test_group_by_provider():
    datasets = [
        {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "資料1", "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/1"},
        {"提供機關": "A機關", "資料集識別碼": 2, "資料集名稱": "資料2", "檔案格式": "JSON", "資料下載網址": "https://a.gov.tw/2"},
        {"提供機關": "B機關", "資料集識別碼": 3, "資料集名稱": "資料3", "檔案格式": "CSV", "資料下載網址": "https://b.gov.tw/3"},
    ]
    groups = group_by_provider(datasets)
    assert len(groups) == 2
    assert len(groups["A機關"]) == 2
    assert len(groups["B機關"]) == 1


def test_scaffold_provider(tmp_path):
    datasets = [
        {"資料集識別碼": 1001, "資料集名稱": "測試資料", "檔案格式": "CSV", "資料下載網址": "https://www.test.gov.tw/a"},
        {"資料集識別碼": 1002, "資料集名稱": "另一筆", "檔案格式": "JSON;CSV", "資料下載網址": "https://www.test.gov.tw/b;https://www.test.gov.tw/c"},
    ]
    slug = scaffold_provider(tmp_path, "測試機關", datasets)

    assert slug == "test_gov_tw"
    pkg_dir = tmp_path / slug
    assert (pkg_dir / "__init__.py").exists()
    assert (pkg_dir / "manifest.json").exists()

    manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "測試機關"
    assert manifest["slug"] == "test_gov_tw"
    assert len(manifest["datasets"]) == 2
    assert manifest["datasets"][1]["urls"] == ["https://www.test.gov.tw/b", "https://www.test.gov.tw/c"]


def test_scaffold_provider_skips_existing(tmp_path):
    datasets = [
        {"資料集識別碼": 1, "資料集名稱": "資料", "檔案格式": "CSV", "資料下載網址": "https://www.test.gov.tw/a"},
    ]
    slug = scaffold_provider(tmp_path, "測試機關", datasets)
    # Modify the manifest to detect if it gets overwritten
    pkg_dir = tmp_path / slug
    (pkg_dir / "manifest.json").write_text("custom")

    slug2 = scaffold_provider(tmp_path, "測試機關", datasets)
    assert (pkg_dir / "manifest.json").read_text() == "custom"
