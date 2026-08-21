import html
import os
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


DEFAULT_ARCHIVES_CACHE_DIR = Path.home() / ".iara" / "archives_cache"

PAGE_STYLE = """
<style>
  body { background:#202124; color:#e8eaed; font-family: -apple-system, "Segoe UI", sans-serif;
         padding: 28px; max-width: 900px; margin: 0 auto; }
  h1 { font-size: 17px; font-weight: 600; word-break: break-all; }
  table { width:100%; border-collapse: collapse; margin-top: 18px; }
  th, td { text-align:left; padding: 7px 10px; border-bottom: 1px solid #3c4043; font-size: 13px; }
  th { color:#9aa0a6; font-weight:500; }
  .muted { color:#9aa0a6; font-size: 13px; }
  code { background:#303134; padding:2px 6px; border-radius:4px; }
</style>
"""


def _page(title, body):
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>{PAGE_STYLE}</head><body>{body}</body></html>"


def format_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def render_error(path, message):
    return _page(
        os.path.basename(path),
        f"<h1>No se pudo abrir {os.path.basename(path)}</h1><p class='muted'>{message}</p>",
    )


def render_missing_dependency(path, pip_package, extra_note=""):
    note = f"<p class='muted'>{extra_note}</p>" if extra_note else ""
    return _page(
        os.path.basename(path),
        f"<h1>Falta un componente para abrir {os.path.basename(path)}</h1>"
        f"<p class='muted'>Instalá el paquete e intentá de nuevo:</p>"
        f"<p><code>pip install {pip_package}</code></p>{note}",
    )


def _cache_root(cache_dir=None):
    root = Path(cache_dir) if cache_dir else DEFAULT_ARCHIVES_CACHE_DIR
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def _safe_cache_name(path):
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base) or "archivo"
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        mtime = 0
    return f"{base}_{mtime}"


def _dest_dir(path, cache_dir=None):
    return os.path.join(_cache_root(cache_dir), _safe_cache_name(path))


def _marker(dest_dir):
    return os.path.join(dest_dir, ".iara_extracted_ok")


def _source_marker(dest_dir):
    return os.path.join(dest_dir, ".iara_archive_source")


def _remember_source(dest_dir, archive_path):
    try:
        with open(_source_marker(dest_dir), "w", encoding="utf-8") as file:
            file.write(str(Path(archive_path).resolve()))
    except OSError:
        pass


def archive_source(dest_dir):
    try:
        with open(_source_marker(dest_dir), encoding="utf-8") as file:
            source = file.read().strip()
    except OSError:
        return None
    return Path(source) if source else None


def _already_extracted(dest_dir):
    return os.path.exists(_marker(dest_dir))


def _mark_extracted(dest_dir):
    with open(_marker(dest_dir), "w", encoding="utf-8") as f:
        f.write("ok")


def extract_zip(path, cache_dir=None):
    dest = _dest_dir(path, cache_dir)
    if not _already_extracted(dest):
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(dest)
        _mark_extracted(dest)
    _remember_source(dest, path)
    return dest


def extract_7z(path, cache_dir=None):
    try:
        import py7zr
    except ImportError:
        return None

    dest = _dest_dir(path, cache_dir)
    if not _already_extracted(dest):
        os.makedirs(dest, exist_ok=True)
        with py7zr.SevenZipFile(path, mode="r") as archive:
            archive.extractall(path=dest)
        _mark_extracted(dest)
    _remember_source(dest, path)
    return dest


def extract_rar(path, cache_dir=None):
    """Extract RAR archives when rarfile and an extractor are available."""
    dest = _dest_dir(path, cache_dir)
    if not _already_extracted(dest):
        os.makedirs(dest, exist_ok=True)
        candidates = [
            shutil.which("7z"),
            shutil.which("7z.exe"),
            shutil.which("unrar"),
            shutil.which("UnRAR.exe"),
            shutil.which("unar"),
            shutil.which("rar"),
            shutil.which("rar.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "WinRAR", "UnRAR.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "WinRAR", "UnRAR.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "WinRAR", "WinRAR.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "WinRAR", "rar.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "WinRAR", "WinRAR.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "WinRAR", "rar.exe"),
        ]
        extracted = False
        tried = set()
        for extractor in candidates:
            if not extractor or extractor in tried:
                continue
            tried.add(extractor)
            if not os.path.isfile(extractor):
                continue
            try:
                executable = os.path.basename(extractor).lower()
                if executable.startswith("7z"):
                    command = [extractor, "x", "-y", f"-o{dest}", str(path)]
                else:
                    command = [extractor, "x", "-y", str(path), dest + os.sep]
                result = subprocess.run(
                    command,
                    capture_output=True, text=True, timeout=120, check=False,
                )
                if result.returncode == 0:
                    extracted = True
                    break
            except (OSError, subprocess.SubprocessError):
                continue
        if not extracted:
            try:
                import rarfile
            except ImportError:
                return None
            try:
                with rarfile.RarFile(path) as archive:
                    archive.extractall(dest)
                extracted = True
            except (OSError, rarfile.Error):
                return None
        try:
            os.makedirs(dest, exist_ok=True)
            _mark_extracted(dest)
        except OSError:
            return None
    _remember_source(dest, path)
    return dest


def render_rar_listing(path):
    import rarfile

    entries = {}
    with rarfile.RarFile(path) as rf:
        for info in rf.infolist():
            name = info.filename.replace("\\", "/").strip("/")
            if not name:
                continue
            size = "" if info.isdir() else format_size(info.file_size)
            date = ""
            if info.date_time:
                try:
                    date = datetime(*info.date_time).strftime("%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    date = ""
            entries[name] = (info.isdir(), size or date)
            parts = name.split("/")
            for index in range(1, len(parts)):
                entries.setdefault("/".join(parts[:index]), (True, ""))

    rows = []
    for name, (is_dir, details) in sorted(entries.items(), key=lambda item: (item[0].lower().count("/"), item[0].lower())):
            icon = "📁" if is_dir else "📄"
            depth = name.count("/")
            parent = name.rsplit("/", 1)[0] if "/" in name else ""
            display = "display:none;" if parent else ""
            folder_attrs = (
                f" data-folder='{html.escape(name)}' onclick='toggleFolder(this)'"
                if is_dir else ""
            )
            rows.append(
                f"<div class='entry {'dir' if is_dir else 'file'}' data-parent='{html.escape(parent)}'{folder_attrs}"
                f" style='padding-left:{10 + depth * 22}px;{display}'>"
                f"<span>{icon} {html.escape(name.rsplit('/', 1)[-1])}</span>"
                f"<span class='size'>{html.escape(details)}</span></div>"
            )

    body = (
        f"<header>📦 {html.escape(str(Path(path).resolve()))}</header>"
        f"<main><section><h2>Contenido</h2>"
        f"<p class='muted'>{len(rows)} elementos - vista de solo lectura.</p>"
        f"{''.join(rows)}</section></main>"
    )
    return _archive_page(os.path.basename(path), body)


def _archive_page(title, body):
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        "<style>*{box-sizing:border-box}body{margin:0;background:#1e1e1e;color:#e6e6e6;"
        "font-family:-apple-system,'Segoe UI',Arial,sans-serif}header{padding:14px 20px;"
        "border-bottom:1px solid #3a3a3a;color:#aaa}main{padding:16px;height:calc(100vh - 60px);"
        "overflow:auto}h2{font-size:12px;text-transform:uppercase;color:#888}.entry{display:flex;"
        "justify-content:space-between;padding:7px 10px;border-radius:6px;font-size:13.5px}"
        ".entry:hover{background:#2c2c2c}.entry.dir{font-weight:600}.size{color:#888;"
        "font-size:12px;margin-left:12px}.entry.dir{cursor:pointer}</style>"
        "<script>function toggleFolder(row){const folder=row.dataset.folder;"
        "const open=row.dataset.open==='1';"
        "document.querySelectorAll('.entry[data-parent]').forEach(function(item){"
        "if(item.dataset.parent===folder)item.style.display=open?'none':'';});"
        "row.dataset.open=open?'0':'1';}</script></head><body>" + body + "</body></html>"
    )


def extract_epub_root(path, cache_dir=None):
    dest = extract_zip(path, cache_dir)
    opf_path = _find_opf(dest)
    if not opf_path:
        return dest
    first_doc = _first_spine_document(opf_path)
    return first_doc if (first_doc and os.path.exists(first_doc)) else dest


def _find_opf(root_dir):
    container = os.path.join(root_dir, "META-INF", "container.xml")
    if not os.path.exists(container):
        return None
    try:
        tree = ET.parse(container)
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = tree.find(".//c:rootfile", ns)
        full_path = rootfile.get("full-path") if rootfile is not None else None
        return os.path.join(root_dir, full_path) if full_path else None
    except ET.ParseError:
        return None


def _first_spine_document(opf_path):
    try:
        tree = ET.parse(opf_path)
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        manifest = {
            item.get("id"): item.get("href")
            for item in tree.findall(".//opf:manifest/opf:item", ns)
        }
        spine = tree.find(".//opf:spine", ns)
        if spine is None:
            return None
        for itemref in spine.findall("opf:itemref", ns):
            href = manifest.get(itemref.get("idref"))
            if href:
                return os.path.normpath(os.path.join(os.path.dirname(opf_path), href))
    except ET.ParseError:
        return None
    return None

