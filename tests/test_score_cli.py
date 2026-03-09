import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from shared.__main__ import app

runner = CliRunner()


def _make_provider(tmp_path, slug="test_provider", datasets=None):
    """Create a minimal provider directory with manifest and datasets."""
    pkg_dir = tmp_path / slug
    pkg_dir.mkdir()
    if datasets is None:
        datasets = [{"id": "1001", "name": "Test", "format": "csv", "urls": ["http://x"]}]
    manifest = {"provider": "測試機關", "slug": slug, "datasets": datasets}
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    ds_dir = pkg_dir / "datasets"
    ds_dir.mkdir()
    (ds_dir / "1001.csv").write_text("a,b\n1,2\n")
    return pkg_dir


def test_score_single_provider(tmp_path):
    pkg_dir = _make_provider(tmp_path)

    with patch("shared.__main__.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["score", str(pkg_dir)])

    assert result.exit_code == 0
    assert (pkg_dir / "scores.json").exists()
    scores = json.loads((pkg_dir / "scores.json").read_text())
    assert scores["datasets"][0]["star_score"] == 3
    # Output shows per-file path and stars
    assert "1001.csv" in result.output
    assert "★★★" in result.output
    # Output shows average at the end
    assert "平均" in result.output


def test_score_all_providers(tmp_path):
    _make_provider(tmp_path, slug="provider_a")
    _make_provider(tmp_path, slug="provider_b")

    with patch("shared.__main__.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["score", "--all"], catch_exceptions=False)

    assert result.exit_code == 0
    assert (tmp_path / "provider_a" / "scores.json").exists()
    assert (tmp_path / "provider_b" / "scores.json").exists()
