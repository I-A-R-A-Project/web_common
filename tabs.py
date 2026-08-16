import os
import uuid
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow


VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".avi", ".mov")
SPECIAL_LOCAL_EXTS = (".zip", ".rar", ".7z", ".epub", ".pdf") + VIDEO_EXTS


class UnifiedWebEnginePage(QWebEnginePage):
    def __init__(
        self,
        profile,
        parent=None,
        folder_view_handler=None,
        special_local_handler=None,
    ):
        super().__init__(profile, parent)
        self.view_widget = parent
        self.folder_view_handler = folder_view_handler
        self.special_local_handler = special_local_handler
        self.popup_windows = []

    def createWindow(self, window_type):
        popup_view = QWebEngineView()
        popup_page = UnifiedWebEnginePage(
            self.profile(),
            popup_view,
            folder_view_handler=self.folder_view_handler,
            special_local_handler=self.special_local_handler,
        )
        popup_view.setPage(popup_page)

        popup_window = QMainWindow()
        popup_window.setWindowTitle("Popup")
        popup_window.setCentralWidget(popup_view)
        popup_window.setGeometry(100, 100, 800, 600)
        popup_window.show()
        self.popup_windows.append(popup_window)
        return popup_page

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
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class UnifiedWebTab(QWebEngineView):
    def __init__(
        self,
        profile,
        parent_window=None,
        script_manager=None,
        folder_view_handler=None,
        special_local_handler=None,
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
