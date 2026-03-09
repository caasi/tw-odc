import subprocess
from pathlib import Path

from main import discover_providers


def test_main_help():
    result = subprocess.run(
        ["uv", "run", "python", "main.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "concurrency" in result.stdout.lower()


def test_discover_finds_data_gov_tw():
    providers = discover_providers()
    assert "data_gov_tw" in providers
