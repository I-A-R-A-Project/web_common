import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def downloader_executable_from(start_path):
    candidates = []
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "IARA" / "Downloader.exe")
    candidates.append(Path(sys.executable).resolve().parent / "Downloader.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def downloader_script_from(start_path):
    root = Path(start_path).resolve()
    for candidate in (root, *root.parents):
        script = candidate / "Downloader" / "download_manager.py"
        if script.exists():
            return script
    return None


def launch_downloader(entries, start_path):
    executable = downloader_executable_from(start_path)
    if executable is not None:
        command = [str(executable)]
        working_dir = executable.parent
    else:
        script = downloader_script_from(start_path)
        if script is None:
            return False, "No se encontró Downloader instalado ni Downloader/download_manager.py"
        command = [sys.executable, str(script)]
        working_dir = script.parent

    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".json",
        encoding="utf-8",
    ) as handle:
        json.dump(entries, handle, indent=2, ensure_ascii=False)
        json_path = handle.name

    subprocess.Popen([*command, json_path], cwd=str(working_dir))
    return True, ""


def entry_from_url(url, path="", title="", download_type=None):
    entry = {"url": url, "path": path or "", "title": title or ""}
    if download_type:
        entry["download_type"] = download_type
    return entry


def handoff_url_to_downloader(
    url,
    start_path,
    *,
    path="",
    title="",
    status_callback=None,
):
    """Send user-selected external URL to Downloader."""
    url = (url or "").strip()
    scheme = urlsplit(url).scheme.lower()
    if not url or scheme not in {"http", "https", "ftp", "magnet"}:
        message = "Seleccioná una URL web o magnet válida."
        if status_callback:
            status_callback(message, 5000)
        return False
    ok, error = launch_downloader(
        [entry_from_url(url, path=path, title=title)],
        start_path,
    )
    if status_callback:
        status_callback(
            "URL enviada al Downloader" if ok else error,
            5000 if ok else 7000,
        )
    return ok
