"""Helpers de navegación independientes de cada aplicación."""

from PyQt6.QtCore import QUrl

from .navbar import address_to_url
from .tabs import is_blocked_url


def set_zoom(view_getter, factor, persist=None):
    """Aplica un factor de zoom a la vista activa y notifica su persistencia."""
    view = view_getter()
    if view is None:
        return None
    view.setZoomFactor(factor)
    if persist is not None:
        persist(factor)
    return factor


def adjust_zoom(view_getter, delta, persist=None):
    """Incrementa o reduce el zoom de la vista activa."""
    view = view_getter()
    if view is None:
        return None
    return set_zoom(view_getter, view.zoomFactor() + delta, persist)


def active_tab(tabs, plus_widget=None):
    """Devuelve la pestaña activa, evitando el placeholder ``+``."""
    current = tabs.currentWidget()
    if current is not None and current is not plus_widget:
        return current
    for index in range(tabs.count() - 1, -1, -1):
        widget = tabs.widget(index)
        if widget is not None and widget is not plus_widget:
            return widget
    return None


def open_plus_tab(tabs, index, plus_widget, open_callback):
    """Ejecuta el callback de nueva pestaña cuando se pulsa ``+``."""
    if tabs.widget(index) is plus_widget:
        return open_callback()
    return None


def sync_address_bar(
    tabs,
    tab,
    qurl,
    address_bar,
    *,
    plus_widget=None,
    extra_callback=None,
):
    """Sincroniza la barra de dirección solo para la pestaña visible."""
    if tab is not active_tab(tabs, plus_widget):
        return False
    text = qurl.toString()
    address_bar.setText("" if text == "about:blank" else text)
    address_bar.setCursorPosition(0)
    if extra_callback is not None:
        extra_callback(text)
    return True


def navigate_view(view_getter, text, *, search_url=None):
    """Convierte una dirección y la carga en la vista activa."""
    target = address_to_url(text, search_url=search_url)
    if target is None or is_blocked_url(target):
        return None
    view = view_getter()
    if view is None:
        return None
    view.setUrl(target)
    return target


def new_tab_page(create_tab):
    """Crea una pestaña mediante el callback de la aplicación y devuelve su página."""
    return create_tab().page()


def open_default_tab(create_tab):
    """Abre una pestaña usando la política predeterminada de la aplicación."""
    return create_tab()


def handle_tab_changed(tabs, index, plus_widget, on_tab_changed):
    """Obtiene la pestaña activa y delega su sincronización a la aplicación."""
    if index < 0:
        return None
    tab = tabs.widget(index)
    if tab is None or tab is plus_widget:
        return None
    on_tab_changed(tab)
    return tab
