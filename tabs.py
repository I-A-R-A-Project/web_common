import os
import uuid
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow, QMenu, QTabBar, QTabWidget, QVBoxLayout, QWidget

from .navbar import BasicNavbar, address_to_url, save_web_page
from .session import is_navigation_title
from .folder_viewer import is_text_file


VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".avi", ".mov")
SPECIAL_LOCAL_EXTS = (".zip", ".rar", ".7z", ".epub") + VIDEO_EXTS


def create_profiled_web_view(profile, parent=None, url=None):
    """Crea una vista QWebEngine con una página ligada al perfil indicado."""
    view = QWebEngineView(parent)
    view.setPage(QWebEnginePage(profile, view))
    if url is not None:
        view.setUrl(url if isinstance(url, QUrl) else QUrl(url))
    return view


class ContextTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._context_menu_handler = None

    def set_context_menu_handler(self, handler):
        self._context_menu_handler = handler

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._context_menu_handler is not None
        ):
            self._context_menu_handler(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)


def add_plus_tab(tabs: QTabWidget):
    """Agrega una pestaña ``+`` sin botones laterales y devuelve el widget."""
    plus_widget = QWidget()
    index = tabs.addTab(plus_widget, "+")
    bar = tabs.tabBar()
    bar.setTabButton(index, bar.ButtonPosition.RightSide, None)
    bar.setTabButton(index, bar.ButtonPosition.LeftSide, None)
    return plus_widget


def keep_plus_tab_last(tabs: QTabWidget, plus_widget) -> None:
    """Mueve la pestaña ``+`` al final después de reordenar pestañas."""
    plus_index = tabs.indexOf(plus_widget)
    last_index = tabs.count() - 1
    if plus_index >= 0 and plus_index != last_index:
        tabs.tabBar().moveTab(plus_index, last_index)


def update_tab_title(
    tabs: QTabWidget,
    tab,
    title: str,
    *,
    title_limit: int = 30,
    muted_prefix: str = "",
) -> None:
    """Actualiza el título visible y conserva los títulos de sesión."""
    index = tabs.indexOf(tab)
    if index < 0:
        return
    session_title = tab.property("_session_title")
    if is_navigation_title(title) and session_title:
        tabs.setTabText(index, session_title)
        return
    if not is_navigation_title(title):
        tab.setProperty("_session_title", "")
    visible_title = (title or "Nueva pestaña")[:title_limit]
    if muted_prefix and hasattr(tab, "page") and tab.page().isAudioMuted():
        visible_title = muted_prefix + visible_title
    tabs.setTabText(index, visible_title)


def update_tab_icon(tabs: QTabWidget, tab, icon) -> None:
    """Actualiza el ícono de una pestaña si todavía pertenece al widget."""
    index = tabs.indexOf(tab)
    if index >= 0:
        tabs.setTabIcon(index, icon)


def install_tab_context_menu(
    tabs: QTabWidget,
    *,
    close_tab,
    plus_widget=None,
    toggle_mute=None,
    direct_right_click=False,
) -> None:
    """Install the common actions shown when right-clicking a tab."""
    def show_menu(pos):
        bar = tabs.tabBar()
        index = bar.tabAt(pos)
        if index < 0 or (plus_widget is not None and tabs.widget(index) is plus_widget):
            return
        last_real_index = (
            tabs.indexOf(plus_widget) - 1
            if plus_widget is not None
            else tabs.count() - 1
        )
        menu = QMenu(tabs.window())
        tab = tabs.widget(index)
        if hasattr(tab, "page"):
            page = tab.page()
            action = menu.addAction(
                "Activar sonido" if page.isAudioMuted() else "Enmudecer pestaña"
            )
            action.triggered.connect(
                lambda: toggle_mute(index)
                if toggle_mute is not None
                else page.setAudioMuted(not page.isAudioMuted())
            )
            menu.addSeparator()

        close_right = menu.addAction("Cerrar pestañas a la derecha")
        close_right.setEnabled(index < last_real_index)
        close_right.triggered.connect(
            lambda: [close_tab(i) for i in range(last_real_index, index, -1)]
        )
        close_left = menu.addAction("Cerrar pestañas a la izquierda")
        close_left.setEnabled(index > 0)
        close_left.triggered.connect(
            lambda: [close_tab(i) for i in range(index - 1, -1, -1)]
        )
        menu.exec(bar.mapToGlobal(pos))

    if direct_right_click:
        bar = tabs.tabBar()
        if not isinstance(bar, ContextTabBar):
            if plus_widget is not None and tabs.indexOf(plus_widget) >= 0:
                return
            new_bar = ContextTabBar(tabs)
            tabs.setTabBar(new_bar)
            bar = new_bar
        bar.set_context_menu_handler(show_menu)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    else:
        bar = tabs.tabBar()
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(show_menu)


def configure_tab_widget(
    tabs: QTabWidget,
    *,
    close_tab,
    plus_widget,
    current_changed=None,
    tab_bar_clicked=None,
    tab_moved=None,
    toggle_mute=None,
    direct_right_click=True,
) -> None:
    """Configura la pestaña compartida entre Browser e IA: barra de tabs,
    clics, reordenado y menú contextual."""
    bar = tabs.tabBar()
    if not isinstance(bar, ContextTabBar):
        tabs.setTabBar(ContextTabBar(tabs))
        bar = tabs.tabBar()

    tabs.setTabsClosable(True)
    tabs.setMovable(True)
    tabs.tabCloseRequested.connect(close_tab)
    if current_changed is not None:
        tabs.currentChanged.connect(current_changed)
    if tab_bar_clicked is not None:
        tabs.tabBarClicked.connect(tab_bar_clicked)
    if tab_moved is not None:
        tabs.tabBar().tabMoved.connect(tab_moved)
    if plus_widget is not None:
        index = tabs.indexOf(plus_widget)
        if index >= 0:
            bar.setTabButton(index, bar.ButtonPosition.RightSide, None)
            bar.setTabButton(index, bar.ButtonPosition.LeftSide, None)
        keep_plus_tab_last(tabs, plus_widget)
    install_tab_context_menu(
        tabs,
        close_tab=close_tab,
        plus_widget=plus_widget,
        toggle_mute=toggle_mute,
        direct_right_click=direct_right_click,
    )


class TabbedPopupWindow(QMainWindow):
    """Fallback window for browser requests that explicitly require a window."""

    def __init__(
        self,
        profile,
        *,
        folder_view_handler=None,
        special_local_handler=None,
        file_view_handler=None,
        view_factory=None,
    ):
        super().__init__()
        self.setWindowTitle("Nueva ventana")
        self.resize(1000, 700)
        self.profile = profile
        self.folder_view_handler = folder_view_handler
        self.special_local_handler = special_local_handler
        self.file_view_handler = file_view_handler
        self.view_factory = view_factory
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        navbar = BasicNavbar(self)
        navbar.on_back = lambda: self._call_current("back")
        navbar.on_forward = lambda: self._call_current("forward")
        navbar.on_reload = lambda: self._call_current("reload")
        navbar.on_stop = lambda: self._call_current("stop")
        navbar.on_address_bar_enter = self._navigate
        navbar.on_save_page = lambda: save_web_page(self.current_view())
        self.address_bar = navbar.address_bar

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(navbar)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)
        self._add_tab()

    def _create_view(self):
        if self.view_factory:
            return self.view_factory(self._new_tab_view)
        return UnifiedWebTab(
            self.profile,
            folder_view_handler=self.folder_view_handler,
            special_local_handler=self.special_local_handler,
            file_view_handler=self.file_view_handler,
            new_tab_handler=self._new_tab_page,
        )

    def _add_tab(self):
        view = self._create_view()
        index = self.tabs.addTab(view, "Nueva pestaña")
        self.tabs.setCurrentIndex(index)
        view.titleChanged.connect(
            lambda title, tab=view: self._update_title(tab, title)
        )
        view.urlChanged.connect(
            lambda url, tab=view: self._update_address(tab, url)
        )
        return view

    def _new_tab_page(self):
        return self._new_tab_view().page()

    def _new_tab_view(self):
        return self._add_tab()

    def current_page(self):
        return self.tabs.currentWidget().page()

    def current_view(self):
        return self.tabs.currentWidget()

    def _call_current(self, method):
        view = self.current_view()
        if view is not None:
            getattr(view, method)()

    def _navigate(self, text):
        url = address_to_url(text, search_url="https://www.google.com/search?q={query}")
        if url is not None and self.current_view() is not None:
            self.current_view().setUrl(url)

    def _update_address(self, view, url):
        if view is self.current_view():
            self.address_bar.setText(url.toString())

    def _on_tab_changed(self, _index):
        view = self.current_view()
        self.address_bar.setText(view.url().toString() if view else "")

    def _update_title(self, view, title):
        index = self.tabs.indexOf(view)
        if index >= 0:
            session_title = view.property("_session_title")
            if is_navigation_title(title) and session_title:
                self.tabs.setTabText(index, session_title)
                return
            if not is_navigation_title(title):
                view.setProperty("_session_title", "")
            self.tabs.setTabText(index, (title or "Nueva pestaña")[:30])

    def _close_tab(self, index):
        view = self.tabs.widget(index)
        self.tabs.removeTab(index)
        view.deleteLater()
        if self.tabs.count() == 0:
            self.close()


class UnifiedWebEnginePage(QWebEnginePage):
    def __init__(
        self,
        profile,
        parent=None,
        folder_view_handler=None,
        special_local_handler=None,
        file_view_handler=None,
        new_tab_page_handler=None,
        new_window_page_handler=None,
    ):
        super().__init__(profile, parent)
        self.view_widget = parent
        self.folder_view_handler = folder_view_handler
        self.special_local_handler = special_local_handler
        self.file_view_handler = file_view_handler
        self.new_tab_page_handler = new_tab_page_handler
        self.new_window_page_handler = new_window_page_handler
        self.popup_windows = []

    def createWindow(self, window_type):
        if (
            window_type == QWebEnginePage.WebWindowType.WebBrowserTab
            and self.new_tab_page_handler
        ):
            return self.new_tab_page_handler()
        if (
            window_type == QWebEnginePage.WebWindowType.WebBrowserWindow
            and self.new_window_page_handler
        ):
            return self.new_window_page_handler()

        popup_window = TabbedPopupWindow(
            self.profile(),
            folder_view_handler=self.folder_view_handler,
            special_local_handler=self.special_local_handler,
            file_view_handler=self.file_view_handler,
        )
        popup_window.show()
        self.popup_windows.append(popup_window)
        return popup_window.current_page()

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        from . import folder_viewer
        if is_main_frame and url.scheme() == "browser-action":
            return not folder_viewer.handle_action(self, url)
        if is_main_frame and url.scheme() == "file":
            local_path = url.toLocalFile()
            if self.folder_view_handler and local_path and Path(local_path).is_dir():
                handler = self.folder_view_handler
                QTimer.singleShot(0, lambda: handler(self, local_path))
                return False
            if self.special_local_handler and local_path:
                ext = os.path.splitext(local_path)[1].lower()
                if ext in SPECIAL_LOCAL_EXTS:
                    handler = self.special_local_handler
                    QTimer.singleShot(0, lambda: handler(self.view_widget, local_path))
                    return False
            if self.file_view_handler and local_path and is_text_file(local_path):
                handler = self.file_view_handler
                QTimer.singleShot(0, lambda: handler(self, local_path))
                return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class UnifiedWebTab(QWebEngineView):
    def __init__(
        self,
        profile,
        parent_window=None,
        script_manager=None,
        folder_view_handler=None,
        special_local_handler=None,
        file_view_handler=None,
        new_tab_handler=None,
        new_window_handler=None,
        url_changed_handler=None,
        title_changed_handler=None,
        icon_changed_handler=None,
        load_finished_handler=None,
    ):
        super().__init__()
        self.parent_window = parent_window
        self.script_manager = script_manager
        self.session_id = uuid.uuid4().hex

        page = UnifiedWebEnginePage(
            profile,
            self,
            folder_view_handler=folder_view_handler,
            special_local_handler=special_local_handler,
            file_view_handler=file_view_handler,
            new_tab_page_handler=new_tab_handler,
            new_window_page_handler=new_window_handler,
        )
        self.setPage(page)

        self._new_window_handler = new_window_handler
        self._url_changed_handler = url_changed_handler
        self._title_changed_handler = title_changed_handler
        self._icon_changed_handler = icon_changed_handler
        self._load_finished_handler = load_finished_handler

        page.newWindowRequested.connect(self._on_new_window_requested)
        self.urlChanged.connect(self._on_url_changed)
        self.loadFinished.connect(self._on_load_finished)
        self.titleChanged.connect(self._on_title_changed)
        self.iconChanged.connect(self._on_icon_changed)

    def _on_url_changed(self, qurl: QUrl):
        self._inject_matching_userscripts(qurl.toString())
        if self._url_changed_handler:
            self._url_changed_handler(self, qurl)

    def _on_load_finished(self, ok):
        if self._load_finished_handler:
            self._load_finished_handler(self, ok)

    def _on_title_changed(self, title):
        if self._title_changed_handler:
            self._title_changed_handler(self, title)

    def _on_icon_changed(self, icon):
        if self._icon_changed_handler:
            self._icon_changed_handler(self, icon)

    def _on_new_window_requested(self, request):
        if self._new_window_handler:
            self._new_window_handler(request)

    def _inject_matching_userscripts(self, url):
        if not self.script_manager:
            return
        collection = self.page().scripts()
        collection.clear()
        for user_script in self.script_manager.scripts_for_url(url):
            collection.insert(user_script.to_qwebengine_script())
