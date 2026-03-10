# tests/test_cli.py
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tw_odc.cli import app

runner = CliRunner()


class TestMetadataList:
    def test_json_output(self, tmp_path, monkeypatch):
        """metadata list outputs JSON array of providers."""
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON匯出", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "資料A",
             "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/d"},
            {"提供機關": "A機關", "資料集識別碼": 2, "資料集名稱": "資料A2",
             "檔案格式": "JSON", "資料下載網址": "https://a.gov.tw/d2"},
            {"提供機關": "B機關", "資料集識別碼": 3, "資料集名稱": "資料B",
             "檔案格式": "CSV", "資料下載網址": "https://b.gov.tw/d"},
        ]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [p["provider"] for p in data]
        assert "A機關" in names
        assert "B機關" in names

    def test_text_output(self, tmp_path, monkeypatch):
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON匯出", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "A機關", "資料集識別碼": 1, "資料集名稱": "資料A",
             "檔案格式": "CSV", "資料下載網址": "https://a.gov.tw/d"},
        ]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "list", "--format", "text"])
        assert result.exit_code == 0
        assert "A機關" in result.output
        # Should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)


class TestMetadataCreate:
    def test_creates_dataset_manifest(self, tmp_path, monkeypatch):
        manifest = {
            "type": "metadata",
            "provider": "data.gov.tw",
            "datasets": [{"id": "export-json", "name": "JSON匯出", "format": "json",
                          "urls": ["https://data.gov.tw/datasets/export/json"]}],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        export_data = [
            {"提供機關": "測試機關", "資料集識別碼": 1001, "資料集名稱": "測試",
             "檔案格式": "CSV", "資料下載網址": "https://test.gov.tw/a"},
        ]
        (tmp_path / "export-json.json").write_text(json.dumps(export_data, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "create", "--provider", "測試機關"])
        assert result.exit_code == 0
        slug = result.output.strip()
        assert slug == "test_gov_tw"
        assert (tmp_path / slug / "manifest.json").exists()


class TestDatasetList:
    def test_json_output(self, tmp_path, monkeypatch):
        manifest = {
            "type": "dataset",
            "provider": "測試機關",
            "slug": "test_gov_tw",
            "datasets": [
                {"id": "1001", "name": "資料A", "format": "csv", "urls": ["https://test.gov.tw/a"]},
                {"id": "1002", "name": "資料B", "format": "json", "urls": ["https://test.gov.tw/b"]},
            ],
        }
        pkg_dir = tmp_path / "test_gov_tw"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["id"] == "1001"

    def test_with_dir_flag(self, tmp_path, monkeypatch):
        manifest = {
            "type": "dataset",
            "provider": "測試機關",
            "slug": "test_gov_tw",
            "datasets": [{"id": "1001", "name": "資料A", "format": "csv", "urls": ["https://test.gov.tw/a"]}],
        }
        pkg_dir = tmp_path / "test_gov_tw"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["dataset", "--dir", "test_gov_tw", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


class TestDatasetClean:
    def test_clean_removes_files(self, tmp_path, monkeypatch):
        manifest = {
            "type": "dataset", "provider": "T", "slug": "t",
            "datasets": [],
        }
        pkg_dir = tmp_path / "t"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))
        ds_dir = pkg_dir / "datasets"
        ds_dir.mkdir()
        (ds_dir / "1001.csv").write_text("data")
        monkeypatch.chdir(pkg_dir)

        result = runner.invoke(app, ["dataset", "clean"])
        assert result.exit_code == 0
        assert not ds_dir.exists()


class TestWrongManifestType:
    def test_metadata_cmd_in_dataset_dir(self, tmp_path, monkeypatch):
        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["metadata", "list"])
        assert result.exit_code != 0

    def test_dataset_cmd_in_metadata_dir(self, tmp_path, monkeypatch):
        manifest = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code != 0
