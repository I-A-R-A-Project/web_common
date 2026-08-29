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
        frames = "\n".join(
            f'<iframe src="{QUrl.fromLocalFile(document).toString()}" '
            f'title="Capítulo {index}"></iframe>'
            for index, document in enumerate(documents, 1)
        )
        reader_path.write_text(
            f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(self.title())}</title>
<style>
html, body {{ margin: 0; padding: 0; background: #202124; color: #e8eaed;
  overflow-y: auto; }}
body {{ min-height: 100vh; }}
iframe {{ display: block; width: 100%; height: 100vh; border: 0;
  background: white; }}
</style></head><body>{frames}
<script>
document.addEventListener("keydown", function(event) {{
  if (["ArrowDown", "ArrowRight", "PageDown", " "].includes(event.key)) {{
    event.preventDefault();
    window.scrollBy({{top: window.innerHeight * 0.85, behavior: "smooth"}});
  }} else if (["ArrowUp", "ArrowLeft", "PageUp"].includes(event.key)) {{
    event.preventDefault();
    window.scrollBy({{top: -window.innerHeight * 0.85, behavior: "smooth"}});
  }} else if (event.key === "Home") {{
    event.preventDefault();
    window.scrollTo({{top: 0, behavior: "smooth"}});
  }} else if (event.key === "End") {{
    event.preventDefault();
    window.scrollTo({{top: document.body.scrollHeight, behavior: "smooth"}});
  }}
}});
</script></body></html>""",
            encoding="utf-8",
        )
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
