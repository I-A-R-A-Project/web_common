"""Operaciones de zoom compartidas por los navegadores."""


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
