import os

from .video_tab import VideoTab


def open_video_tab(tabs, path, main_window, title_limit=30, on_open=None):
    tab = VideoTab(path, main_window)
    title = os.path.basename(path)
    index = tabs.addTab(tab, title[:title_limit] or "Video")
    tabs.setCurrentIndex(index)
    if on_open is not None:
        on_open(tab, title)
    return tab
