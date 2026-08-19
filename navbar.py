"""Barra de navegación reutilizable para navegadores web."""

import re
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QToolBar, QLineEdit
from PyQt6.QtGui import QAction


_WINDOWS_PATH_RE = re.compile(r"^[a-zA-Z]:[\\/]")


def looks_like_local_path(text: str) -> bool:
    """Return whether address text is a local filesystem path or file URL."""
    return (
        text.startswith("file://")
        or bool(_WINDOWS_PATH_RE.match(text))
        or text.startswith("/")
        or text.startswith("~")
    )


def address_to_url(text: str, *, search_url: str | None = None) -> QUrl | None:
    """Convert address-bar text to a navigable URL."""
    text = text.strip()
    if not text:
        return None

    if looks_like_local_path(text):
        local_path = (
            QUrl(text).toLocalFile()
            if text.startswith("file://")
            else os.path.expanduser(text)
        )
        return QUrl.fromLocalFile(local_path)

    if not text.startswith(("http://", "https://", "file://")):
        if search_url is not None and ("." not in text or " " in text):
            query = QUrl.toPercentEncoding(text).data().decode()
            return QUrl(search_url.format(query=query))
        text = "https://" + text
    return QUrl(text)


def save_web_page(view, *, target_dir: str | Path | None = None, status_callback=None) -> None:
    """Guarda la vista actual como HTML en un archivo."""
    if view is None:
        if status_callback:
            status_callback("No hay una pagina web activa para guardar", 4000)
        return

    page = getattr(view, "page", None)
    if page is None:
        if status_callback:
            status_callback("No hay una pagina web activa para guardar", 4000)
        return

    target_root = Path(target_dir) if target_dir is not None else Path.cwd() / "saved_pages"
    target_root.mkdir(parents=True, exist_ok=True)

    host = "page"
    try:
        host = view.url().host() or "page"
    except Exception:
        pass

    safe_host = re.sub(r"[^a-zA-Z0-9_-]+", "_", host).strip("_") or "page"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_file = target_root / f"{safe_host}_{timestamp}.html"

    def _write_html(html: str) -> None:
        target_file.write_text(html, encoding="utf-8")
        if status_callback:
            status_callback(f"Pagina guardada en {target_file.name}", 5000)

    try:
        page.toHtml(_write_html)
    except Exception:
        if status_callback:
            status_callback("No se pudo guardar la página.", 4000)


class BasicNavbar(QToolBar):
    """Barra de navegación básica con botones estándar: ← → ⟳ ■ 💾 y URL."""

    def __init__(self, parent=None):
        super().__init__("Navegación", parent)
        self.setMovable(False)

        # Callbacks que se asignan desde el navegador
        self.on_back = None
        self.on_forward = None
        self.on_reload = None
        self.on_stop = None
        self.on_save_page = None
        self.on_address_bar_enter = None

        # Botón Atrás
        self.back_action = QAction("←", self)
        self.back_action.setToolTip("Atrás")
        self.back_action.triggered.connect(self._on_back_clicked)
        self.addAction(self.back_action)

        # Botón Adelante
        self.forward_action = QAction("→", self)
        self.forward_action.setToolTip("Adelante")
        self.forward_action.triggered.connect(self._on_forward_clicked)
        self.addAction(self.forward_action)

        # Botón Recargar
        self.reload_action = QAction("⟳", self)
        self.reload_action.setToolTip("Recargar página")
        self.reload_action.triggered.connect(self._on_reload_clicked)
        self.addAction(self.reload_action)

        # Botón Detener
        self.stop_action = QAction("■", self)
        self.stop_action.setToolTip("Detener carga")
        self.stop_action.triggered.connect(self._on_stop_clicked)
        self.addAction(self.stop_action)

        # Barra de dirección
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("URL...")
        self.address_bar.returnPressed.connect(self._on_address_bar_enter)
        self.addWidget(self.address_bar)

        # Botón Guardar página
        self.save_page_action = QAction("💾", self)
        self.save_page_action.setToolTip("Guardar página")
        self.save_page_action.triggered.connect(self._on_save_page_clicked)
        self.addAction(self.save_page_action)

    def _on_back_clicked(self):
        if self.on_back:
            self.on_back()

    def _on_forward_clicked(self):
        if self.on_forward:
            self.on_forward()

    def _on_reload_clicked(self):
        if self.on_reload:
            self.on_reload()

    def _on_stop_clicked(self):
        if self.on_stop:
            self.on_stop()

    def _on_save_page_clicked(self):
        if self.on_save_page:
            self.on_save_page()

    def _on_address_bar_enter(self):
        if self.on_address_bar_enter:
            self.on_address_bar_enter(self.address_bar.text())

    def set_url(self, url: str):
        """Actualiza la URL en la barra."""
        self.address_bar.setText(url)

    def get_url(self) -> str:
        """Obtiene la URL actual de la barra."""
        return self.address_bar.text()
