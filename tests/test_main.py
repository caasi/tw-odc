import subprocess


def test_main_help():
    result = subprocess.run(
        ["uv", "run", "python", "main.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "concurrency" in result.stdout.lower()
