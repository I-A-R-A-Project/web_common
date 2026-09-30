import base64
import json
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QTimer
from PyQt6.QtGui import QIcon, QPixmap


class SessionAutoSaver:
    """Programa un guardado de sesión después de cambios en las pestañas."""

    def __init__(self, save_callback):
        self._save_callback = save_callback
        self._pending = False

    def schedule(self):
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self._save)

    def _save(self):
        self._pending = False
        self._save_callback()


def widget_url(widget):
    if not hasattr(widget, "url"):
        return ""
    try:
        url = widget.url().toString()
    except Exception:
        return ""
    return "" if url == "about:blank" else url


def icon_to_data(icon):
    if icon.isNull():
        return ""
    pixmap = icon.pixmap(32, 32)
    if pixmap.isNull():
        return ""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        return ""
    return base64.b64encode(bytes(buffer.data())).decode("ascii")


def icon_from_data(value):
    if not isinstance(value, str) or not value:
        return QIcon()
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return QIcon()
    pixmap = QPixmap()
    if not pixmap.loadFromData(data, "PNG"):
        return QIcon()
    return QIcon(pixmap)


# Keep the original private names available to existing consumers.
_icon_data = icon_to_data
_icon_from_data = icon_from_data


def collect_tabs(tab_widget, skip_widgets=(), metadata_for_widget=None):
    skip_ids = {id(widget) for widget in skip_widgets if widget is not None}
    tabs = []
    for index in range(tab_widget.count()):
        widget = tab_widget.widget(index)
        if widget is None or id(widget) in skip_ids:
            continue
        url = widget_url(widget)
        if not url:
            continue
        entry = {
            "url": url,
            "title": tab_widget.tabText(index),
        }
        favicon = icon_to_data(tab_widget.tabIcon(index))
        if favicon:
            entry["favicon"] = favicon
        if metadata_for_widget:
            metadata = metadata_for_widget(widget) or {}
            entry.update(metadata)
        tabs.append(entry)
    return tabs


def restore_tab_metadata(tab_widget, index, entry):
    title = entry.get("title")
    if isinstance(title, str) and title:
        tab_widget.widget(index).setProperty("_session_title", title)
        tab_widget.setTabText(index, title)
    tab_widget.setTabIcon(index, icon_from_data(entry.get("favicon")))


def is_navigation_title(title):
    if not isinstance(title, str):
        return False
    value = title.strip().lower()
    return bool(
        re.match(r"^(https?://|file://|www\.)", value)
        or ("." in value and " " not in value)
    )


def save_tab_session(path, tab_widget, skip_widgets=(), metadata_for_widget=None, extra=None):
    session_path = Path(path)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "tabs": collect_tabs(tab_widget, skip_widgets, metadata_for_widget),
        "active_index": tab_widget.currentIndex(),
        "saved": datetime.now().isoformat(),
    }
    if extra:
        payload.update(extra)
    with session_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_tab_session(path):
    session_path = Path(path)
    if not session_path.exists():
        return {}
    try:
        with session_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    tabs = payload.get("tabs")
    if not isinstance(tabs, list):
        return {}
    payload["tabs"] = [
        tab for tab in tabs
        if isinstance(tab, dict) and isinstance(tab.get("url"), str) and tab.get("url")
    ]
    return payload
