import os
import re
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
    return dest


def render_rar_listing(path):
    import rarfile

    rows = []
    with rarfile.RarFile(path) as rf:
        for info in rf.infolist():
            icon = "[dir]" if info.isdir() else "[file]"
            size = "" if info.isdir() else format_size(info.file_size)
            date = ""
            if info.date_time:
                try:
                    date = datetime(*info.date_time).strftime("%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    date = ""
            rows.append(f"<tr><td>{icon} {info.filename}</td><td>{size}</td><td>{date}</td></tr>")

    body = (
        f"<h1>{os.path.basename(path)}</h1>"
        f"<p class='muted'>{len(rows)} elementos - vista de solo lectura. "
        f"Los archivos .rar no se pueden extraer sin una herramienta externa (unrar/unar).</p>"
        f"<table><tr><th>Nombre</th><th>Tamaño</th><th>Modificado</th></tr>{''.join(rows)}</table>"
    )
    return _page(os.path.basename(path), body)


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

