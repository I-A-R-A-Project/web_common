"""yt-dlp video cache management with resume support."""

import hashlib
import os
import shutil
from pathlib import Path


def get_cache_directory():
    """Return the yt-dlp video cache directory, creating it if necessary."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache_dir = base / "IARA" / "yt-dlp-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_cached_video_path(url):
    """Return the cached video file path for a URL, or None if not present."""
    cache_dir = get_cache_directory()
    filename = _url_to_filename(url)
    cache_file = cache_dir / filename
    return cache_file if cache_file.exists() else None


def get_cache_path_for_download(url):
    """Return the destination path for caching a downloaded video from URL."""
    cache_dir = get_cache_directory()
    filename = _url_to_filename(url)
    return cache_dir / filename


def _url_to_filename(url):
    """Hash a URL to a stable cache filename."""
    hash_digest = hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:16]
    return f"video-{hash_digest}.mkv"


def clear_cache():
    """Remove all cached videos."""
    cache_dir = get_cache_directory()
    try:
        shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def get_cache_stats():
    """Return (file_count, total_size_bytes) for cached videos."""
    cache_dir = get_cache_directory()
    try:
        files = list(cache_dir.glob("video-*.mkv"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        return len(files), total_size
    except OSError:
        return 0, 0
