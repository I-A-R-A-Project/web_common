"""Acciones compartidas para abrir archivos y rutas locales en los navegadores."""

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from . import local_viewer


def open_local_file(parent, open_path):
    """Muestra el selector de archivos y entrega la ruta seleccionada."""
    path, _ = QFileDialog.getOpenFileName(parent, "Abrir archivo")
    if path:
        return open_path(path)
    return None


def open_local_folder(parent, open_path):
    """Muestra el selector de carpetas y entrega la ruta seleccionada."""
    path = QFileDialog.getExistingDirectory(parent, "Abrir carpeta")
    if path:
        return open_path(path)
    return None


def handle_special_local_file(
    tab,
    local_path,
    *,
    video_extensions,
    video_handler,
    target_handler,
):
    """Deriva videos y archivos especiales a los callbacks de la aplicación."""
    return local_viewer.handle_special_local_file(
        tab,
        local_path,
        video_extensions=video_extensions,
        video_handler=video_handler,
        target_handler=target_handler,
    )


def open_local_target(tab, local_path, cache_dir, *, epub_handler=None):
    """Abre archivos locales usando los extractores y visores compartidos."""
    return local_viewer.open_local_target(
        tab,
        str(Path(local_path)),
        cache_dir,
        epub_handler=epub_handler,
    )


def replace_tab_with_epub(
    tab,
    tabs,
    local_path,
    cache_dir,
    *,
    epub_factory,
    on_replaced=None,
):
    """Reemplaza una pestaña por un visor EPUB creado por la aplicación."""
    epub = epub_factory(tab, local_path, cache_dir)
    index = tabs.indexOf(tab)
    if index < 0:
        return None
    tabs.removeTab(index)
    tabs.insertTab(index, epub, epub.title())
    tabs.setCurrentIndex(index)
    if on_replaced is not None:
        on_replaced(tab, epub)
    tab.deleteLater()
    return epub
