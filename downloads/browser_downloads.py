"""Shared browser download tracking and UI."""

import json
import os
import tempfile
import time
import uuid
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import Qt, QStandardPaths, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest

from web_common.storage.paths import app_data_dir
from .downloader_handoff import entry_from_url, launch_downloader


STATUS_NAMES = {
    "waiting": "En espera",
    "resolving": "Resolviendo",
    "downloading": "Descargando",
    "finished": "Completado",
    "cancelled": "Cancelado",
    "error": "Error",
}


def downloader_state_path() -> Path:
    return app_data_dir("Downloader") / "download_state.json"


def _cookie_applies_to_url(cookie, url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    raw_domain = cookie.get("domain") or ""
    domain = raw_domain.lstrip(".").lower()
    cookie_path = cookie.get("path") or "/"
    request_path = parsed.path or "/"
    if not host or not domain:
        return False
    if raw_domain.startswith("."):
        domain_matches = host == domain or host.endswith(f".{domain}")
    else:
        domain_matches = host == domain
    if not domain_matches:
        return False
    if not (
        request_path == cookie_path.rstrip("/")
        or request_path.startswith(cookie_path.rstrip("/") + "/")
        or cookie_path == "/"
    ):
        return False
    if cookie.get("secure") and parsed.scheme.lower() != "https":
        return False
    expires_at = cookie.get("expires_at")
    if expires_at:
        try:
            if int(expires_at) <= int(time.time() * 1000):
                return False
        except (TypeError, ValueError):
            return False
    return True


def cookies_for_url(cookies, url):
    return [dict(cookie) for cookie in cookies if _cookie_applies_to_url(cookie, url)]


def request_cookie_jar(cookies, url, base_cookies=None):
    from requests.cookies import RequestsCookieJar

    jar = RequestsCookieJar()
    for name, value in (base_cookies or {}).items():
        jar.set(str(name), str(value))
    for cookie in cookies_for_url(cookies, url):
        raw_domain = cookie["domain"]
        domain = raw_domain.lstrip(".").lower()
        expires_at = cookie.get("expires_at")
        expires = int(int(expires_at) / 1000) if expires_at else None
        for existing in list(jar):
            if existing.name == cookie["name"]:
                jar.clear(existing.domain, existing.path, existing.name)
        jar.set_cookie(
            Cookie(
                version=0,
                name=cookie["name"],
                value=cookie["value"],
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=raw_domain.startswith("."),
                domain_initial_dot=raw_domain.startswith("."),
                path=cookie.get("path") or "/",
                path_specified=True,
                secure=bool(cookie.get("secure")),
                expires=expires,
                discard=expires is None,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": cookie.get("http_only", False)},
                rfc2109=False,
            )
        )
    return jar


class BrowserCookieStore:
    """Cache profile cookies for short-lived, origin-scoped download handoffs."""

    def __init__(self, profile):
        self.cookies = {}
        self.profile = profile
        self.store = profile.cookieStore()
        self.store.cookieAdded.connect(self._cookie_added)
        self.store.cookieRemoved.connect(self._cookie_removed)
        self.store.loadAllCookies()

    @staticmethod
    def _cookie_key(cookie):
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        path = cookie.path() or "/"
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")
        return (cookie.domain() or "", path, name)

    def _cookie_added(self, cookie):
        name, value = bytes(cookie.name()), bytes(cookie.value())
        if not name or not cookie.domain():
            return
        expires_at = None
        expiration = cookie.expirationDate()
        if not cookie.isSessionCookie() and expiration.isValid():
            expires_at = expiration.toMSecsSinceEpoch()
        record = {
            "name": name.decode("utf-8", errors="replace"),
            "value": value.decode("utf-8", errors="replace"),
            "domain": cookie.domain(),
            "path": cookie.path() or "/",
            "secure": cookie.isSecure(),
            "http_only": cookie.isHttpOnly(),
            "expires_at": expires_at,
        }
        self.cookies[self._cookie_key(cookie)] = record

    def _cookie_removed(self, cookie):
        self.cookies.pop(self._cookie_key(cookie), None)

    def cookies_for_url(self, url):
        return cookies_for_url(self.cookies.values(), url)

    def headers_for_download(self, referer=""):
        headers = {}
        user_agent = self.profile.httpUserAgent()
        if user_agent:
            headers["User-Agent"] = user_agent
        if referer:
            headers["Referer"] = referer
        return headers


class DownloadItem:
    STATE_NAMES = {
        QWebEngineDownloadRequest.DownloadState.DownloadRequested: "Solicitando",
        QWebEngineDownloadRequest.DownloadState.DownloadInProgress: "Descargando",
        QWebEngineDownloadRequest.DownloadState.DownloadCompleted: "Completado",
        QWebEngineDownloadRequest.DownloadState.DownloadCancelled: "Cancelado",
        QWebEngineDownloadRequest.DownloadState.DownloadInterrupted: "Interrumpido",
    }

    def __init__(self, request: QWebEngineDownloadRequest):
        self.request = request
        self.filename = request.downloadFileName()
        self.directory = request.downloadDirectory()

    @property
    def path(self):
        return os.path.join(self.directory, self.filename)

    def progress_text(self):
        received = self.request.receivedBytes()
        total = self.request.totalBytes()
        state = self.STATE_NAMES.get(self.request.state(), "?")
        if total > 0:
            pct = int(received / total * 100)
            size_mb = total / (1024 * 1024)
            return f"{self.filename} — {state} ({pct}% de {size_mb:.1f} MB)"
        received_mb = received / (1024 * 1024)
        return f"{self.filename} — {state} ({received_mb:.1f} MB)"


class DownloadManager:
    """Accept native WebEngine downloads used as a fallback."""

    def __init__(self, download_dir=None, fallback_dir=None):
        self.download_dir = download_dir
        self.fallback_dir = fallback_dir
        self.items = []
        self._pending_names = set()

    def handle_download(self, request: QWebEngineDownloadRequest):
        download_dir = self.download_dir or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
        if not download_dir:
            download_dir = self.fallback_dir or str(Path.home() / "Downloads")
        os.makedirs(download_dir, exist_ok=True)

        requested_name = Path(request.downloadFileName()).name or "download"
        final_name = self._unique_name(download_dir, requested_name)
        request.setDownloadDirectory(str(download_dir))
        request.setDownloadFileName(final_name)
        self._pending_names.add(final_name)
        request.stateChanged.connect(
            lambda state, name=final_name: self._release_name(name, state)
        )
        request.accept()

        item = DownloadItem(request)
        self.items.insert(0, item)
        return item

    def _release_name(self, filename, state):
        if state in {
            QWebEngineDownloadRequest.DownloadState.DownloadCompleted,
            QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
            QWebEngineDownloadRequest.DownloadState.DownloadInterrupted,
        }:
            self._pending_names.discard(filename)

    def _unique_name(self, directory, filename):
        base, ext = os.path.splitext(filename)
        candidate = filename
        index = 1
        while (
            os.path.exists(os.path.join(directory, candidate))
            or candidate in self._pending_names
        ):
            candidate = f"{base} ({index}){ext}"
            index += 1
        return candidate


class BrowserDownloadTracker:
    """Track Downloader entry IDs separately for each browser application."""

    def __init__(self, tracking_path, state_path=None):
        self.tracking_path = Path(tracking_path)
        self.state_path = Path(state_path) if state_path else downloader_state_path()

    def submit_url(
        self,
        url,
        start_path,
        *,
        path="",
        title="",
        metadata=None,
        auth_cookies=None,
        auth_headers=None,
    ):
        url = (url or "").strip()
        try:
            scheme = urlsplit(url).scheme.lower()
        except ValueError:
            scheme = ""
        if not url or scheme not in {"http", "https", "ftp", "magnet"}:
            return "unsupported", "La descarga no tiene una URL transferible."

        entry_id = uuid.uuid4().hex
        entry = entry_from_url(url, path=path, title=title)
        entry["id"] = entry_id
        scoped_cookies = cookies_for_url(auth_cookies or [], url)
        if scoped_cookies:
            entry["auth_cookies"] = scoped_cookies
        if auth_headers:
            entry["auth_headers"] = dict(auth_headers)
        try:
            ids, metadata_by_id = self._load_tracking()
            ids.append(entry_id)
            if metadata:
                metadata_by_id[entry_id] = metadata
            self._write_tracking(ids, metadata_by_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return "error", f"No se pudo guardar el seguimiento de descargas: {exc}"

        try:
            ok, error = launch_downloader([entry], start_path)
        except OSError as exc:
            ok, error = False, str(exc)
        if not ok:
            try:
                ids, metadata_by_id = self._load_tracking()
                metadata_by_id.pop(entry_id, None)
                self._write_tracking(
                    [item for item in ids if item != entry_id],
                    metadata_by_id,
                )
            except (OSError, ValueError, json.JSONDecodeError) as cleanup_error:
                error = (
                    f"{error or 'No se pudo iniciar Downloader.'} "
                    f"No se pudo limpiar el ID local: {cleanup_error}"
                )
            return "error", error or "No se pudo iniciar Downloader."

        return "sent", "Descarga enviada al Downloader."

    def get_entries(self):
        ids, metadata_by_id = self._load_tracking()
        ids = set(ids)
        if not ids or not self.state_path.exists():
            return []

        with self.state_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_entries = payload.get("entries", []) if isinstance(payload, dict) else None
        if not isinstance(raw_entries, list):
            raise ValueError("El archivo de estado no contiene una lista de descargas.")

        entries = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id")
            if not isinstance(entry_id, str) or entry_id not in ids:
                continue
            copy = dict(entry)
            copy["_browser_metadata"] = metadata_by_id.get(entry_id, {})
            entries.append(copy)
        return entries

    def clear_metadata(self, entry_id):
        ids, metadata_by_id = self._load_tracking()
        metadata_by_id.pop(entry_id, None)
        self._write_tracking(ids, metadata_by_id)

    def _load_tracking(self):
        if not self.tracking_path.exists():
            return [], {}
        with self.tracking_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        ids = payload.get("ids", []) if isinstance(payload, dict) else None
        if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
            raise ValueError("El archivo local de IDs de descargas no es válido.")
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else None
        if not isinstance(metadata, dict) or any(
            not isinstance(value, dict) for value in metadata.values()
        ):
            raise ValueError("Los metadatos locales de descargas no son válidos.")
        return list(dict.fromkeys(ids)), metadata

    def _write_tracking(self, ids, metadata):
        self.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                delete=False,
                suffix=".json",
                dir=self.tracking_path.parent,
                encoding="utf-8",
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(
                    {
                        "version": 1,
                        "ids": list(dict.fromkeys(ids)),
                        "metadata": metadata,
                    },
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
            os.replace(temp_path, self.tracking_path)
        except OSError:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise


def format_downloader_entry(entry):
    title = str(entry.get("title") or entry.get("url_original") or "Descarga").strip()
    status = entry.get("status", "waiting")
    if not isinstance(status, str):
        status = str(status)
    status_label = STATUS_NAMES.get(status, str(status))
    extract_status = entry.get("extract_status")
    if status == "finished" and extract_status == "running":
        status_label = "Extrayendo"
    elif status == "finished" and extract_status == "done":
        status_label = "Completado (extraído)"
    elif status == "finished" and extract_status == "error":
        status_label = "Error de extracción"
    label = f"{title} — {status_label}"
    try:
        progress = int(entry.get("progress", 0) or 0)
    except (TypeError, ValueError):
        progress = 0
    if status in {"downloading", "resolving"} and progress > 0:
        label += f" ({progress}%)"
    speed = entry.get("speed_text")
    if speed:
        label += f" — {str(speed)}"
    error = entry.get("error_text") or entry.get("extract_error")
    if error and (status == "error" or extract_status == "error"):
        label += f" — {str(error)}"
    return label


class BrowserDownloadsDialog(QDialog):
    """Show this browser's Downloader entries and any native fallback items."""

    def __init__(
        self,
        tracker: BrowserDownloadTracker,
        download_manager: DownloadManager | None = None,
        on_open=None,
        parent=None,
    ):
        super().__init__(parent)
        self.tracker = tracker
        self.download_manager = download_manager
        self.on_open = on_open
        self.setWindowTitle("Descargas")
        self.resize(620, 440)

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._open_selected())
        self.list_widget.currentRowChanged.connect(
            lambda _row: self._update_actions()
        )
        layout.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("Abrir")
        self.open_button.clicked.connect(self._open_selected)
        self.open_button.setVisible(bool(on_open))
        buttons.addWidget(self.open_button)

        self.folder_button = QPushButton("Abrir carpeta")
        self.folder_button.clicked.connect(self._open_folder)
        buttons.addWidget(self.folder_button)

        self.cancel_button = QPushButton("Cancelar descarga nativa")
        self.cancel_button.clicked.connect(self._cancel_selected)
        self.cancel_button.setVisible(download_manager is not None)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)
        self._refresh()

    def _refresh(self):
        selected_key = None
        current = self.list_widget.currentItem()
        if current:
            selected_key = current.data(Qt.ItemDataRole.UserRole)

        self.list_widget.clear()
        try:
            entries = self.tracker.get_entries()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.list_widget.addItem(f"No se pudo leer el estado de Downloader: {exc}")
            return

        rows = []
        for entry in entries:
            rows.append((format_downloader_entry(entry), ("downloader", entry)))
        if self.download_manager:
            rows.extend(
                (item.progress_text(), ("native", item))
                for item in self.download_manager.items
            )

        if not rows:
            self.list_widget.addItem("(sin descargas todavía)")
            self._update_actions()
            return

        selected_row = -1
        for index, (label, data) in enumerate(rows):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.list_widget.addItem(item)
            if data == selected_key:
                selected_row = index
        if selected_row >= 0:
            self.list_widget.setCurrentRow(selected_row)
        self._update_actions()

    def _update_actions(self):
        data = self._selected_data()
        is_native = bool(data and data[0] == "native")
        self.open_button.setEnabled(is_native)
        self.cancel_button.setEnabled(is_native)
        self.folder_button.setEnabled(
            bool(
                data
                and (
                    data[1].directory
                    if data[0] == "native"
                    else data[1].get("path")
                )
            )
        )

    def _selected_data(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_selected(self):
        data = self._selected_data()
        if data and data[0] == "native" and self.on_open:
            self.on_open(data[1].path)
            self.accept()

    def _open_folder(self):
        data = self._selected_data()
        if not data:
            return
        if data[0] == "native":
            folder = data[1].directory
        else:
            folder = data[1].get("path", "")
        if folder and Path(folder).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _cancel_selected(self):
        data = self._selected_data()
        if data and data[0] == "native":
            data[1].request.cancel()

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
