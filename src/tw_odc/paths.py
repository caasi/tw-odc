"""Path resolution for tw-odc metadata storage."""

import json
import sys
from pathlib import Path

APP_NAME = "tw-odc"


def _config_dir() -> Path:
    """回傳跨平台的使用者設定目錄。

    - Linux: ~/.config/tw-odc/（XDG）
    - macOS: ~/.config/tw-odc/（強制 XDG，不用 ~/Library/Application Support/）
    - Windows: C:/Users/<user>/AppData/Local/tw-odc/
    """
    if sys.platform == "win32":
        from platformdirs.windows import Windows
        return Path(Windows(APP_NAME).user_config_dir)
    else:
        from platformdirs.unix import Unix
        return Path(Unix(APP_NAME).user_config_dir)


def data_dir() -> Path:
    """回傳 metadata 存放目錄。

    優先順序：
    1. $PWD 有 manifest.json 且 type == "metadata" → 回傳 $PWD
    2. 否則 → _config_dir()
    """
    cwd = Path.cwd()
    local_manifest = cwd / "manifest.json"
    if local_manifest.is_file():
        try:
            data = json.loads(local_manifest.read_text(encoding="utf-8"))
            if data.get("type") == "metadata":
                return cwd
        except (json.JSONDecodeError, OSError):
            pass

    config = _config_dir()
    config.mkdir(parents=True, exist_ok=True)
    return config


def ensure_manifest(metadata_dir: Path) -> None:
    """若 metadata_dir 內無 manifest.json，從 package 內建的 default 複製一份。"""
    manifest_path = metadata_dir / "manifest.json"
    if manifest_path.exists():
        return
    from importlib.resources import files
    default = files("tw_odc").joinpath("default_manifest.json").read_text(encoding="utf-8")
    metadata_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(default, encoding="utf-8")
