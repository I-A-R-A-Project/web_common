import os

from PyQt6.QtCore import QUrl

from .video_tab import VideoTab


def open_video_tab(tabs, path, main_window, title_limit=30):
    tab = VideoTab(path, main_window)
    title = os.path.basename(path)
    index = tabs.addTab(tab, title[:title_limit] or "Video")
    tabs.setCurrentIndex(index)
    return tab


def configure_pdf_view(view, path, tabs=None, title_limit=30):
    settings = view.settings()
    settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
    settings.setAttribute(settings.WebAttribute.PdfViewerEnabled, True)
    view.setUrl(QUrl.fromLocalFile(path))
    if tabs is not None:
        index = tabs.indexOf(view)
        if index >= 0:
            tabs.setTabText(index, os.path.basename(path)[:title_limit] or "PDF")
    return view
