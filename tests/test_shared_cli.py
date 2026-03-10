import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shared.__main__ import app

runner = CliRunner()


def _write_export(path: Path, datasets: list[dict]) -> None:
    path.write_text(json.dumps(datasets, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATASETS = [
    # 正常機關：有 URL，slug 為 a_gov_tw
    {
        "提供機關": "A機關",
        "資料集識別碼": 1,
        "資料集名稱": "資料A",
        "檔案格式": "CSV",
        "資料下載網址": "https://a.gov.tw/data",
    },
    # 已移植機關：有 URL，slug 為 b_gov_tw
    {
        "提供機關": "B機關",
        "資料集識別碼": 2,
        "資料集名稱": "資料B",
        "檔案格式": "JSON",
        "資料下載網址": "https://b.gov.tw/data",
    },
    # 無 URL 機關：fallback slug 為 org_<sha256>
    {
        "提供機關": "無網址機關",
        "資料集識別碼": 3,
        "資料集名稱": "資料C",
        "檔案格式": "CSV",
        "資料下載網址": "",
    },
]

_ORG_SLUG = "org_" + hashlib.sha256("無網址機關".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# list --missing tests
# ---------------------------------------------------------------------------


def test_list_missing_shows_unscaffolded(tmp_path):
    """Without any scaffolded dirs, all providers appear under --missing."""
    export = tmp_path / "export.json"
    _write_export(export, DATASETS)

    result = runner.invoke(app, ["list", str(export), "--missing", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "A機關" in result.output
    assert "B機關" in result.output
    assert "無網址機關" in result.output


def test_list_missing_filters_existing_domain_slug(tmp_path):
    """Provider whose domain-based slug directory exists is filtered out."""
    export = tmp_path / "export.json"
    _write_export(export, DATASETS)
    (tmp_path / "b_gov_tw").mkdir()

    result = runner.invoke(app, ["list", str(export), "--missing", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "A機關" in result.output
    assert "B機關" not in result.output
    assert "無網址機關" in result.output


def test_list_missing_filters_fallback_org_slug(tmp_path):
    """Provider with no URLs whose org_<sha256> directory exists is filtered out (no false positive)."""
    export = tmp_path / "export.json"
    _write_export(export, DATASETS)
    (tmp_path / _ORG_SLUG).mkdir()

    result = runner.invoke(app, ["list", str(export), "--missing", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "A機關" in result.output
    assert "B機關" in result.output
    assert "無網址機關" not in result.output


def test_list_missing_all_scaffolded(tmp_path):
    """When every provider is scaffolded, --missing produces no output."""
    export = tmp_path / "export.json"
    _write_export(export, DATASETS)
    (tmp_path / "a_gov_tw").mkdir()
    (tmp_path / "b_gov_tw").mkdir()
    (tmp_path / _ORG_SLUG).mkdir()

    result = runner.invoke(app, ["list", str(export), "--missing", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_list_without_missing_shows_all(tmp_path):
    """Without --missing, all providers appear regardless of existing directories."""
    export = tmp_path / "export.json"
    _write_export(export, DATASETS)
    (tmp_path / "a_gov_tw").mkdir()

    result = runner.invoke(app, ["list", str(export)])

    assert result.exit_code == 0
    assert "A機關" in result.output
    assert "B機關" in result.output
    assert "無網址機關" in result.output
