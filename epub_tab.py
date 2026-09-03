import os
from html import escape
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView

from . import local_viewer


class EpubTab(QWebEngineView):
    """Visor de EPUB basado en WebEngine para HTML, CSS e imágenes locales."""

    def __init__(self, profile: QWebEngineProfile, path: str, cache_dir=None, parent=None):
        super().__init__(parent)
        self._path = os.path.abspath(path)
        self._qurl = QUrl.fromLocalFile(self._path)
        self._cache_dir = cache_dir
        self.setPage(self._create_page(profile))
        self.loadFinished.connect(self._enable_continuous_scrolling)
        self._load_epub()

    def _create_page(self, profile):
        from .tabs import UnifiedWebEnginePage

        return UnifiedWebEnginePage(profile, self)

    def _load_epub(self):
        try:
            documents = local_viewer.extract_epub_documents(
                self._path, self._cache_dir
            )
            if not documents:
                raise ValueError("El EPUB no contiene documentos en el spine")
            reader = self._create_reader(documents)
            self.setUrl(QUrl.fromLocalFile(reader))
        except (OSError, ValueError, RuntimeError) as exc:
            self.setHtml(
                local_viewer.render_error(
                    self._path, f"Error al abrir el EPUB: {exc}"
                ),
                self._qurl,
            )

    def _create_reader(self, documents):
        reader_path = Path(documents[0]).parent / ".iara_epub_reader.html"
        total = len(documents)
        pages = "\n".join(
            f'<div class="page" data-index="{index - 1}">'
            f'<div class="page-label">Capítulo {index} de {total}</div>'
            f'<iframe src="{QUrl.fromLocalFile(document).toString()}" '
            f'title="Capítulo {index}"></iframe></div>'
            for index, document in enumerate(documents, 1)
        )
        assets = Path(__file__).with_name("assets")
        template = (assets / "epub_reader.html").read_text(encoding="utf-8")
        content = (
            template.replace("__TITLE__", escape(self.title()))
            .replace("__CSS_URL__", QUrl.fromLocalFile(str(assets / "epub_reader.css")).toString())
            .replace("__JS_URL__", QUrl.fromLocalFile(str(assets / "epub_reader.js")).toString())
            .replace("__TOTAL__", str(total))
            .replace("__BOOK_NAME__", escape(Path(self._path).name))
            .replace("__PAGES__", pages)
        )
        reader_path.write_text(content, encoding="utf-8")
        return str(reader_path)

    def _enable_continuous_scrolling(self, loaded):
        if not loaded:
            return
        self.page().runJavaScript(
            """
            (() => {
                const root = document.documentElement;
                const body = document.body;
                for (const element of [root, body]) {
                    if (!element) continue;
                    element.style.overflow = 'auto';
                    element.style.overflowY = 'auto';
                    element.style.height = 'auto';
                    element.style.maxHeight = 'none';
                }
                return true;
            })();
            """
        )

    def url(self):
        return self._qurl

    def title(self):
        return Path(self._path).name

    def reload(self):
        self._load_epub()

    def zoomFactor(self):
        return super().zoomFactor()

    def setZoomFactor(self, factor):
        super().setZoomFactor(factor)
