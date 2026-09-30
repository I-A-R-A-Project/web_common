"""Shared per-user data paths for IARA applications."""

import os
from pathlib import Path


def iara_data_root() -> Path:
    override = os.environ.get("IARA_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "IARA"


def app_data_dir(name: str) -> Path:
    path = iara_data_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path
