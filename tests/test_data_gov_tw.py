import json
import subprocess
from pathlib import Path

import pytest


def test_manifest_has_three_datasets():
    manifest_path = Path("data_gov_tw/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["datasets"]) == 3
    assert all(
        any(url.startswith("https://data.gov.tw/") for url in ds["urls"])
        for ds in manifest["datasets"]
    )


def test_cli_module_runs():
    result = subprocess.run(
        ["uv", "run", "python", "-m", "data_gov_tw", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "data.gov.tw" in result.stdout
