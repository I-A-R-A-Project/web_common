import json
from datetime import datetime
from pathlib import Path


def widget_url(widget):
    if not hasattr(widget, "url"):
        return ""
    try:
        url = widget.url().toString()
    except Exception:
        return ""
    return "" if url == "about:blank" else url


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
        entry = {"url": url}
        if metadata_for_widget:
            metadata = metadata_for_widget(widget) or {}
            entry.update(metadata)
        tabs.append(entry)
    return tabs


def save_tab_session(path, tab_widget, skip_widgets=(), metadata_for_widget=None, extra=None):
    session_path = Path(path)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
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

