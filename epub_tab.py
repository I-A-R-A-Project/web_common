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
        reader_path.write_text(
            f"""<!doctype html>
                <html><head><meta charset="utf-8"><title>{escape(self.title())}</title>
                <style>
                * {{ box-sizing:border-box; }}
                html, body {{ margin:0; padding:0; background:#16171a; color:#e8eaed;
                overflow-y:auto; font-family:-apple-system,"Segoe UI",Arial,sans-serif; }}
                body {{ min-height:100vh; }}
                #epub-toolbar {{ position:sticky; top:0; z-index:10; display:flex; align-items:center;
                flex-wrap:wrap; gap:10px; padding:9px 18px; background:#1c1d21;
                border-bottom:1px solid #2c2d31; font-size:13px; color:#9aa0a6; }}
                #epub-toolbar button {{ background:#2a2b30; color:#f1f3f4; border:none; border-radius:6px;
                padding:5px 10px; cursor:pointer; font-size:13px; line-height:1; }}
                #epub-toolbar button:hover {{ background:#3a3b42; }}
                #epub-toolbar button:disabled {{ opacity:.35; cursor:default; }}
                #epub-toolbar button:disabled:hover {{ background:#2a2b30; }}
                #chapterIndicator, #zoomIndicator {{ min-width:58px; text-align:center;
                font-variant-numeric:tabular-nums; }}
                .divider {{ width:1px; height:18px; background:#2c2d31; margin:0 2px; }}
                .spacer {{ flex:1; }}
                .muted {{ color:#6c7077; font-size:12px; max-width:260px; overflow:hidden;
                text-overflow:ellipsis; white-space:nowrap; }}
                #progress-track {{ position:sticky; top:39px; z-index:9; height:3px; background:#1c1d21; }}
                #progress-fill {{ height:100%; width:0%; background:#4a90e2; transition:width .08s linear; }}
                .page-stack {{ display:flex; flex-direction:column; align-items:center; gap:26px;
                padding:26px 16px 70px; transform-origin:top center; }}
                .page {{ width:100%; max-width:820px; }}
                .page-label {{ color:#8a8f97; font-size:11px; text-transform:uppercase;
                letter-spacing:.06em; margin-bottom:6px; padding-left:2px; }}
                .page iframe {{ display:block; width:100%; height:100vh; border:0; background:#fff;
                border-radius:4px; box-shadow:0 6px 24px rgba(0,0,0,.35); }}
                </style></head><body>
                <div id="epub-toolbar">
                  <button id="prevChapter" title="Capítulo anterior ([)">◀</button>
                  <span id="chapterIndicator">1 / {total}</span>
                  <button id="nextChapter" title="Siguiente capítulo (])">▶</button>
                  <span class="divider"></span>
                  <button id="zoomOut" title="Reducir zoom (Ctrl -)">−</button>
                  <span id="zoomIndicator">100%</span>
                  <button id="zoomIn" title="Aumentar zoom (Ctrl +)">+</button>
                  <span class="spacer"></span>
                  <span class="muted">{escape(Path(self._path).name)}</span>
                </div>
                <div id="progress-track"><div id="progress-fill"></div></div>
                <div class="page-stack">{pages}</div>
                <script>
                (function () {{
                  const pages = [...document.querySelectorAll('.page')];
                  const total = pages.length;
                  const chapterIndicator = document.getElementById('chapterIndicator');
                  const prevBtn = document.getElementById('prevChapter');
                  const nextBtn = document.getElementById('nextChapter');
                  const zoomIndicator = document.getElementById('zoomIndicator');
                  const zoomInBtn = document.getElementById('zoomIn');
                  const zoomOutBtn = document.getElementById('zoomOut');
                  const stack = document.querySelector('.page-stack');
                  const progressFill = document.getElementById('progress-fill');
                  let current = 0;
                  let zoom = 1;

                  function updateButtons() {{
                    prevBtn.disabled = current <= 0;
                    nextBtn.disabled = current >= total - 1;
                    chapterIndicator.textContent = (current + 1) + ' / ' + total;
                  }}
                  function goTo(index) {{
                    index = Math.max(0, Math.min(total - 1, index));
                    pages[index].scrollIntoView({{behavior: 'smooth', block: 'start'}});
                  }}
                  prevBtn.addEventListener('click', function () {{ goTo(current - 1); }});
                  nextBtn.addEventListener('click', function () {{ goTo(current + 1); }});

                  function setZoom(value) {{
                    zoom = Math.max(0.6, Math.min(2, value));
                    stack.style.zoom = zoom;
                    zoomIndicator.textContent = Math.round(zoom * 100) + '%';
                  }}
                  zoomInBtn.addEventListener('click', function () {{ setZoom(zoom + 0.1); }});
                  zoomOutBtn.addEventListener('click', function () {{ setZoom(zoom - 0.1); }});

                  const observer = new IntersectionObserver(function (entries) {{
                    entries.forEach(function (entry) {{
                      if (entry.isIntersecting && entry.intersectionRatio > 0.5) {{
                        current = Number(entry.target.dataset.index);
                        updateButtons();
                      }}
                    }});
                  }}, {{ threshold: [0.5] }});
                  pages.forEach(function (page) {{ observer.observe(page); }});

                  function updateProgress() {{
                    const max = document.body.scrollHeight - window.innerHeight;
                    const ratio = max > 0 ? window.scrollY / max : 0;
                    progressFill.style.width = (Math.max(0, Math.min(1, ratio)) * 100) + '%';
                  }}
                  window.addEventListener('scroll', updateProgress, {{passive: true}});

                  document.addEventListener('keydown', function (event) {{
                    if (['ArrowDown', 'ArrowRight', 'PageDown', ' '].includes(event.key)) {{
                      event.preventDefault();
                      window.scrollBy({{top: window.innerHeight * 0.85, behavior: 'smooth'}});
                    }} else if (['ArrowUp', 'ArrowLeft', 'PageUp'].includes(event.key)) {{
                      event.preventDefault();
                      window.scrollBy({{top: -window.innerHeight * 0.85, behavior: 'smooth'}});
                    }} else if (event.key === 'Home') {{
                      event.preventDefault();
                      window.scrollTo({{top: 0, behavior: 'smooth'}});
                    }} else if (event.key === 'End') {{
                      event.preventDefault();
                      window.scrollTo({{top: document.body.scrollHeight, behavior: 'smooth'}});
                    }} else if (event.key === ']') {{
                      goTo(current + 1);
                    }} else if (event.key === '[') {{
                      goTo(current - 1);
                    }} else if ((event.ctrlKey || event.metaKey) && (event.key === '+' || event.key === '=')) {{
                      event.preventDefault();
                      setZoom(zoom + 0.1);
                    }} else if ((event.ctrlKey || event.metaKey) && event.key === '-') {{
                      event.preventDefault();
                      setZoom(zoom - 0.1);
                    }} else if ((event.ctrlKey || event.metaKey) && event.key === '0') {{
                      event.preventDefault();
                      setZoom(1);
                    }}
                  }});

                  updateButtons();
                  updateProgress();
                }})();
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
