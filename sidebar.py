import os

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QToolButton, QVBoxLayout, QWidget
from PyQt6.QtCore import QUrl

from .session import icon_from_data, icon_to_data


class SidebarRail(QWidget):
    WIDTH = 52

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons = {}
        self._apps = []
        self._favicon_icons = {}
        self.on_favicon_changed = None
        self.on_toggle = None
        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet("""
            SidebarRail { background-color: #202124; }
            QToolButton { border: none; border-radius: 8px; color: #e8eaed; }
            QToolButton:checked { background-color: #3c4043; }
            QToolButton:hover { background-color: #303134; }
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 6, 4, 6)
        self._layout.setSpacing(4)
        self._layout.addStretch()

    def _icon_for_app(self, app):
        path = app.get("icon_path")
        if path and os.path.exists(path):
            return QIcon(path)
        favicon = self._favicon_icons.get(app.get("id"))
        if favicon is not None and not favicon.isNull():
            return favicon
        favicon = icon_from_data(app.get("favicon"))
        if not favicon.isNull():
            self._favicon_icons[app.get("id")] = favicon
            return favicon
        return None

    def rebuild(self, apps, active_app_id=None):
        self._apps = list(apps)
        app_ids = {app["id"] for app in apps}
        self._favicon_icons = {
            app_id: icon
            for app_id, icon in self._favicon_icons.items()
            if app_id in app_ids
        }
        for btn in self.buttons.values():
            btn.deleteLater()
        self.buttons.clear()
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for app in apps:
            btn = QToolButton()
            icon = self._icon_for_app(app)
            if icon is not None:
                btn.setIcon(icon)
                btn.setIconSize(QSize(28, 28))
            else:
                btn.setText(str(app.get("name", ""))[:2].upper())
            btn.setToolTip(app.get("name", ""))
            btn.setCheckable(True)
            btn.setFixedSize(44, 44)
            btn.clicked.connect(lambda _checked, a=app: self._emit_toggle(a))
            self._layout.insertWidget(self._layout.count() - 1, btn)
            self.buttons[app["id"]] = btn
            if app["id"] == active_app_id:
                btn.setChecked(True)

    def set_favicon(self, app_id, icon):
        if icon is None or icon.isNull():
            return
        app = next(
            (item for item in self._apps if item.get("id") == app_id),
            None,
        )
        if app is None or app.get("icon_path"):
            return
        self._favicon_icons[app_id] = icon
        favicon = icon_to_data(icon)
        if favicon:
            app["favicon"] = favicon
            if self.on_favicon_changed:
                self.on_favicon_changed(app_id, favicon)
        button = self.buttons.get(app_id)
        if button is not None:
            button.setIcon(icon)
            button.setIconSize(QSize(28, 28))
            button.setText("")

    def _emit_toggle(self, app):
        if self.on_toggle:
            self.on_toggle(app)

    def set_checked(self, app_id, checked):
        if app_id in self.buttons:
            self.buttons[app_id].setChecked(checked)

    def uncheck_all(self):
        for btn in self.buttons.values():
            btn.setChecked(False)


class AppPanelOverlay(QWidget):
    EXPANDED_WIDTH = 563

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.views = {}
        self.active_app_id = None
        self.on_new_window_request = None
        self.on_app_icon_changed = None
        self.setAutoFillBackground(True)
        self.setStyleSheet("AppPanelOverlay { background-color: #202124; }")

        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def open_app(self, app):
        app_id = app["id"]
        if app_id not in self.views:
            view = QWebEngineView()
            page = QWebEnginePage(self.profile, view)
            view.setPage(page)
            page.newWindowRequested.connect(self._on_new_window_requested)
            view.iconChanged.connect(
                lambda icon, app_id=app_id: self._on_app_icon_changed(app_id, icon)
            )
            view.setUrl(QUrl(app["url"]))
            self.views[app_id] = view
            self.stack.addWidget(view)

        self.stack.setCurrentWidget(self.views[app_id])
        self.active_app_id = app_id
        self.show()
        self._animate_to(self.EXPANDED_WIDTH)

    def close_panel(self):
        self.active_app_id = None
        self._animate_to(0)

    def is_open_for(self, app_id):
        return self.active_app_id == app_id

    def _on_new_window_requested(self, request):
        requested_host = request.requestedUrl().host().lower()
        if self.on_new_window_request:
            self.on_new_window_request(request)

    def _on_app_icon_changed(self, app_id, icon):
        if self.on_app_icon_changed:
            self.on_app_icon_changed(app_id, icon)

    def _animate_to(self, target_w):
        geometry = self.geometry()
        if geometry.width() == target_w:
            return
        self._anim.stop()
        self._anim.setStartValue(geometry)
        self._anim.setEndValue(QRect(geometry.x(), geometry.y(), target_w, geometry.height()))
        try:
            self._anim.finished.disconnect(self._hide_if_collapsed)
        except TypeError:
            pass
        self._anim.finished.connect(self._hide_if_collapsed)
        self._anim.start()
        self.raise_()

    def _hide_if_collapsed(self):
        if self.geometry().width() <= 0:
            self.hide()

    def set_height(self, height):
        geometry = self.geometry()
        self.setGeometry(geometry.x(), geometry.y(), geometry.width(), height)


class SidebarContainer(QWidget):
    def __init__(self, rail, tabs, app_panel, parent=None):
        super().__init__(parent)
        self.rail = rail
        self.tabs = tabs
        self.app_panel = app_panel

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(rail)
        layout.addWidget(tabs, 1)

        self.app_panel.setParent(self)
        self.app_panel.setGeometry(rail.width(), 0, 0, self.height() or 780)
        self.app_panel.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.app_panel.move(self.rail.width(), 0)
        self.app_panel.set_height(self.height())
