import os
import uuid
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from .navbar import BasicNavbar, address_to_url, save_web_page
from .session import is_navigation_title
from .folder_viewer import is_text_file


VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".avi", ".mov")
SPECIAL_LOCAL_EXTS = (".zip", ".rar", ".7z", ".epub", ".pdf") + VIDEO_EXTS


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
            new_window_page_handler=None,
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
