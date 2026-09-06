import html
import os
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QUrl


DEFAULT_ARCHIVES_CACHE_DIR = Path.home() / ".iara" / "archives_cache"

ASSETS_DIR = Path(__file__).with_name("assets")


def handle_special_local_file(
    tab,
    local_path,
    *,
    video_extensions,
    video_handler,
    target_handler,
):
    """Dispatch a special local file while leaving app-specific UI callbacks injectable."""
    path = str(local_path)
    if Path(path).suffix.lower() in video_extensions:
        video_handler(path)
        return
    target_handler(tab, path)


def _page(title, body):
    template = (ASSETS_DIR / "local_viewer.html").read_text(encoding="utf-8")
    return (
        template.replace("__TITLE__", html.escape(title))
        .replace("__CSS_URL__", QUrl.fromLocalFile(str(ASSETS_DIR / "local_viewer.css")).toString())
        .replace("__BODY__", body)
    )


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


def _safe_member_path(destination, member_name):
    root = Path(destination).resolve()
    target = (root / member_name).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Ruta insegura en el comprimido: {member_name}")
    return target


def _extract_zip_safe(archive, destination):
    for info in archive.infolist():
        target = _safe_member_path(destination, info.filename)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def _extract_tar_safe(archive, destination):
    for info in archive.getmembers():
        target = _safe_member_path(destination, info.name)
        if info.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif info.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def extract_zip(path, cache_dir=None):
    dest = _dest_dir(path, cache_dir)
    if not _already_extracted(dest):
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            _extract_zip_safe(zf, dest)
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


def archive_entries(path):
    """Devuelve archivos de un comprimido usando librerías Python cuando existen."""
    lower = Path(path).name.lower()
    try:
        if lower.endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                return [name for name in archive.namelist() if not name.endswith("/")]
        if lower.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar")):
            import tarfile
            with tarfile.open(path) as archive:
                return [item.name for item in archive.getmembers() if item.isfile()]
        if lower.endswith(".rar"):
            import rarfile
            with rarfile.RarFile(path) as archive:
                return [name for name in archive.namelist() if not name.endswith("/")]
        if lower.endswith(".7z"):
            import py7zr
            with py7zr.SevenZipFile(path, mode="r") as archive:
                return list(archive.getnames())
        if lower.endswith((".gz", ".bz2")):
            return [Path(path).stem]
    except (ImportError, OSError, ValueError, RuntimeError):
        return None
    return None


def extract_archive(path, destination):
    """Extrae un comprimido en ``destination`` sin depender de ejecutables externos."""
    import bz2
    import gzip
    import tarfile

    source = Path(path)
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    lower = source.name.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(source) as archive:
            _extract_zip_safe(archive, target)
    elif lower.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar")):
        with tarfile.open(source) as archive:
            _extract_tar_safe(archive, target)
    elif lower.endswith(".gz"):
        with gzip.open(source, "rb") as source_file, (target / source.stem).open("wb") as target_file:
            shutil.copyfileobj(source_file, target_file)
    elif lower.endswith(".bz2"):
        with bz2.open(source, "rb") as source_file, (target / source.stem).open("wb") as target_file:
            shutil.copyfileobj(source_file, target_file)
    elif lower.endswith(".rar"):
        import rarfile
        with rarfile.RarFile(source) as archive:
            archive.extractall(target)
    elif lower.endswith(".7z"):
        import py7zr
        with py7zr.SevenZipFile(source, mode="r") as archive:
            archive.extractall(path=target)
    else:
        raise ValueError(f"Formato comprimido no soportado: {source.name}")
    return target


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
    template = (ASSETS_DIR / "archive_viewer.html").read_text(encoding="utf-8")
    return (
        template.replace("__TITLE__", html.escape(title))
        .replace("__CSS_URL__", QUrl.fromLocalFile(str(ASSETS_DIR / "archive_viewer.css")).toString())
        .replace("__JS_URL__", QUrl.fromLocalFile(str(ASSETS_DIR / "archive_viewer.js")).toString())
        .replace("__BODY__", body)
    )


def extract_epub_root(path, cache_dir=None):
    dest = extract_zip(path, cache_dir)
    documents = extract_epub_documents(path, cache_dir)
    if documents:
        return documents[0]
    return dest


def extract_epub_documents(path, cache_dir=None):
    dest = extract_zip(path, cache_dir)
    opf_path = _find_opf(dest)
    if not opf_path:
        return []
    return [
        document
        for document in _spine_documents(opf_path)
        if document and os.path.exists(document)
    ]


def open_local_target(tab, local_path, cache_dir=None, epub_handler=None):
    """Abre un archivo local usando los visores y extractores compartidos.

    ``epub_handler`` permite que cada navegador reemplace su pestaña por su
    propio widget EPUB sin duplicar el procesamiento de archivos.
    """
    ext = os.path.splitext(local_path)[1].lower()
    try:
        if ext == ".zip":
            tab.setUrl(QUrl.fromLocalFile(extract_zip(local_path, cache_dir)))
            return True

        if ext == ".7z":
            dest = extract_7z(local_path, cache_dir)
            if dest is None:
                tab.page().setHtml(
                    render_missing_dependency(local_path, "py7zr"),
                    QUrl.fromLocalFile(local_path),
                )
            else:
                tab.setUrl(QUrl.fromLocalFile(dest))
            return True

        if ext == ".rar":
            dest = extract_rar(local_path, cache_dir)
            if dest:
                tab.setUrl(QUrl.fromLocalFile(dest))
            else:
                tab.page().setHtml(
                    render_error(
                        local_path,
                        "No se pudo extraer. Instalá 7-Zip o WinRAR, "
                        "o configurá 7z/unrar/unar en el PATH.",
                    ),
                    QUrl.fromLocalFile(local_path),
                )
            return True

        if ext == ".epub":
            if epub_handler is not None:
                epub_handler(tab, local_path, cache_dir)
            else:
                document = extract_epub_root(local_path, cache_dir)
                tab.setUrl(QUrl.fromLocalFile(document))
            return True
    except (OSError, ValueError, RuntimeError) as exc:
        tab.page().setHtml(
            render_error(local_path, f"Error al procesar el archivo: {exc}"),
            QUrl.fromLocalFile(local_path),
        )
        return True

    tab.setUrl(QUrl.fromLocalFile(local_path))
    return False


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
    documents = _spine_documents(opf_path)
    return documents[0] if documents else None


def _spine_documents(opf_path):
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
        documents = []
        for itemref in spine.findall("opf:itemref", ns):
            href = manifest.get(itemref.get("idref"))
            if href:
                documents.append(os.path.normpath(os.path.join(os.path.dirname(opf_path), href)))
        return documents
    except ET.ParseError:
        return []
