import os

from PyQt6.QtCore import QUrl
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class EpubTab(QWidget):
    def __init__(self, path, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._path = os.path.abspath(path)
        self._qurl = QUrl.fromLocalFile(self._path)

        self.document = QPdfDocument(self)
        self.document.load(self._path)

        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    def url(self):
        return self._qurl

    def title(self):
        return os.path.basename(self._path)

    def setUrl(self, qurl):
        pass

    def back(self):
        pass

    def forward(self):
        pass

    def reload(self):
        self.document.load(self._path)

    def zoomFactor(self):
        return self.view.zoomFactor()

    def setZoomFactor(self, factor):
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(factor)
