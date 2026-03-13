import json
import sys
from pathlib import Path

from tw_odc.paths import _config_dir, data_dir


class TestConfigDir:
    def test_unix_returns_xdg_path(self, monkeypatch):
        """Linux/macOS should return ~/.config/tw-odc/."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = _config_dir()
        assert result == Path.home() / ".config" / "tw-odc"

    def test_macos_returns_xdg_path(self, monkeypatch):
        """macOS should also return ~/.config/tw-odc/ (not ~/Library/...)."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = _config_dir()
        assert result == Path.home() / ".config" / "tw-odc"

    def test_respects_xdg_config_home(self, monkeypatch):
        """Should respect XDG_CONFIG_HOME env var."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        result = _config_dir()
        assert result == Path("/custom/config/tw-odc")


class TestDataDir:
    def test_cwd_with_metadata_manifest(self, tmp_path, monkeypatch):
        """$PWD with type=metadata manifest → return $PWD."""
        manifest = {"type": "metadata", "provider": "data.gov.tw", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)
        assert data_dir() == tmp_path

    def test_cwd_with_dataset_manifest_falls_back(self, tmp_path, monkeypatch):
        """$PWD with type=dataset manifest → fallback to config dir."""
        manifest = {"type": "dataset", "provider": "T", "slug": "t", "datasets": []}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        result = data_dir()
        assert result != tmp_path
        assert "tw-odc" in str(result)

    def test_cwd_without_manifest_falls_back(self, tmp_path, monkeypatch):
        """$PWD without manifest.json → fallback to config dir."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        result = data_dir()
        assert "tw-odc" in str(result)

    def test_cwd_with_corrupt_manifest_falls_back(self, tmp_path, monkeypatch):
        """$PWD with corrupt manifest.json → fallback to config dir."""
        (tmp_path / "manifest.json").write_text("not json")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        result = data_dir()
        assert result != tmp_path

    def test_creates_config_dir_if_not_exists(self, tmp_path, monkeypatch):
        """Should create config dir when falling back."""
        monkeypatch.chdir(tmp_path)
        config = tmp_path / "custom_config" / "tw-odc"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom_config"))
        monkeypatch.setattr(sys, "platform", "linux")
        result = data_dir()
        assert result == config
        assert config.exists()


class TestDefaultManifest:
    def test_default_manifest_is_valid_json(self):
        """Bundled default_manifest.json should be valid and type=metadata."""
        from importlib.resources import files
        content = files("tw_odc").joinpath("default_manifest.json").read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["type"] == "metadata"
        assert len(data["datasets"]) == 5

    def test_default_manifest_has_all_exports(self):
        """Should contain export-json, export-csv, export-xml, daily-changed-json, daily-changed-csv."""
        from importlib.resources import files
        content = files("tw_odc").joinpath("default_manifest.json").read_text(encoding="utf-8")
        data = json.loads(content)
        ids = {d["id"] for d in data["datasets"]}
        assert ids == {"export-json", "export-csv", "export-xml", "daily-changed-json", "daily-changed-csv"}
