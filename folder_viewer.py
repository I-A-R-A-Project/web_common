"""Safe, dependency-free HTML views for local folders and text files."""

import html
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

from PyQt6.QtCore import QObject, QUrl, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLineEdit, QMessageBox, QTextEdit, QVBoxLayout,
)
from . import local_viewer

MAX_TEXT_BYTES = 2 * 1024 * 1024
TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".css", ".csv", ".go", ".h", ".hpp", ".ini", ".java",
    ".js", ".json", ".jsx", ".md", ".py", ".rs", ".sh", ".sql", ".toml", ".ts",
    ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
_TOKEN_RE = re.compile(r'(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)'
                       r'|(?P<comment>//[^\n]*|#[^\n]*|;[^\n]*)|(?P<number>\b\d+(?:\.\d+)?\b)'
                       r'|(?P<word>[A-Za-z_][A-Za-z0-9_]*)')
_KEYWORDS = {
    "and", "as", "async", "await", "break", "class", "const", "def", "delete",
    "else", "elif", "export", "False", "for", "from", "function", "if", "import",
    "in", "is", "let", "None", "not", "null", "or", "pass", "print", "return",
    "static", "this", "throw", "True", "try", "var", "while", "with", "yield",
}


class _EditorBridge(QObject):
    def __init__(self, page, path):
        super().__init__(page)
        self.page = page
        self.path = Path(path).resolve()

    @pyqtSlot(str)
    def save(self, source):
        try:
            if len(source.encode("utf-8")) > MAX_TEXT_BYTES:
                raise ValueError("El texto supera el límite de 2 MiB.")
            if not is_text_file(self.path):
                raise ValueError("El archivo no es editable.")
            self.path.write_text(source, encoding="utf-8", newline="")
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self.page.view_widget, "Error", str(exc))
            return
        render_file_view(self.page, self.path)

    @pyqtSlot()
    def cancel(self):
        render_file_view(self.page, self.path)


def is_text_file(path):
    return Path(path).suffix.lower() in TEXT_EXTENSIONS


def _highlight(source, suffix):
    if suffix == ".md":
        return "\n".join(
            '<span class="md-heading">' + html.escape(line) + "</span>"
            if re.match(r"^#{1,6}\s+", line) else html.escape(line)
            for line in source.splitlines()
        )
    # Tokenize triple-quoted Python strings and block comments before the
    # single-line tokenizer so newlines remain inside one highlighted token.
    token_re = re.compile(
        r'(?P<multiline>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|/\*[\s\S]*?\*/)'
        r'|' + _TOKEN_RE.pattern
    )
    output, last = [], 0
    for match in token_re.finditer(source):
        output.append(html.escape(source[last:match.start()]))
        kind, value = match.lastgroup, html.escape(match.group(0))
        cls = "string" if kind == "multiline" else (
            "keyword" if kind == "word" and match.group(0) in _KEYWORDS else kind
        )
        output.append(f'<span class="{cls}">{value}</span>')
        last = match.end()
    output.append(html.escape(source[last:]))
    return "".join(output)


def _code_html(source, suffix):
    lines = []
    multiline = False
    for raw_line in source.split("\n"):
        markers = len(re.findall(r'"""|\'\'\'', raw_line))
        if multiline or markers:
            lines.append(f'<span class="string">{html.escape(raw_line) or " "}</span>')
        else:
            lines.append(_highlight(raw_line, suffix))
        if markers % 2:
            multiline = not multiline
    return "".join(
        f'<span class="code-line" data-line="{index}"><span class="ln" contenteditable="false">{index}</span>'
        f'<span class="code-text">{line or " "}</span></span>'
        for index, line in enumerate(lines, 1)
    )


def render_file_html(path, editing=False):
    path = Path(path).resolve()
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            body = f"<h1>{html.escape(path.name)}</h1><p class='muted'>Archivo demasiado grande para la vista previa.</p>"
        else:
            source = path.read_text(encoding="utf-8", errors="replace")
            body = _file_body(path, source, editing)
    except (OSError, UnicodeError) as exc:
        return render_error(str(path), f"No se pudo leer el archivo: {exc}")
    return _page(path.name, body, file_view=True)


def _file_body(path, source, editing=False):
    actions = (
        f'{_action_link("cancel", path, "Cancelar")}'
        f'<a class="button" href="#" onclick="return saveEditLink(this)">Guardar</a>'
        if editing else _action_link("edit", path, "✏ Editar")
    )
    editor_hidden = "" if editing else " hidden"
    viewer_hidden = " hidden" if editing else ""
    return (
        f"<header>📄 {html.escape(str(path))} "
        f"{_action_link('rename', path, '↔ Renombrar')}{actions}</header>"
        f"<div id='viewer'{viewer_hidden}><pre class='code'><code>{_code_html(source, path.suffix.lower())}</code></pre></div>"
        f"<div id='editor' data-path='{html.escape(str(path))}'{editor_hidden}>"
        f"<pre class='line-numbers' aria-hidden='true'>{''.join(str(i) + chr(10) for i in range(1, source.count(chr(10)) + 2))}</pre>"
        f"<pre class='editable-code' contenteditable='true' spellcheck='false'><code>{_highlight(source, path.suffix.lower())}</code></pre></div>"
    )


def _git_root(path):
    try:
        result = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 and result.stdout.strip() else None


def _git_run(root, args):
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _git_branches(root):
    result = _git_run(root, ["for-each-ref", "--format=%(refname:short)", "refs/heads"])
    return [x.strip() for x in (result.stdout if result else "").splitlines() if x.strip()]


def _git_commits(root, limit=50, branch="HEAD"):
    result = _git_run(root, ["log", branch, f"-{limit}", "--date=iso",
                             "--pretty=format:%H%x1f%h%x1f%ad%x1f%an%x1f%s"])
    return [line.split("\x1f", 4) for line in (result.stdout if result else "").splitlines() if line.strip()]


def _action_link(action, path, label, **params):
    query = f"path={quote(str(Path(path).absolute()))}"
    for key, value in params.items():
        query += f"&{quote(key)}={quote(str(value))}"
    return f'<a class="button" href="browser-action://{action}?{query}">{label}</a>'


def render_folder_html(folder_path, branch=None, selected_commit=None):
    folder = Path(folder_path).resolve()
    archive_root = folder
    archive_source = None
    while archive_root.parent != archive_root:
        source = local_viewer.archive_source(archive_root)
        if source:
            archive_source = source
            break
        archive_root = archive_root.parent
    is_archive_root = archive_source is not None and folder == archive_root
    rows = []
    try:
        entries = sorted(
            (entry for entry in folder.iterdir() if not entry.name.startswith(".iara_")),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
    except OSError:
        entries = []
    parent = archive_source.parent if is_archive_root else folder.parent
    if parent != folder:
        rows.append(f'<a class="entry dir" href="{html.escape(parent.as_uri() + "/")}">⬆ .. (subir un nivel)</a>')
    for entry in entries:
        url = html.escape(entry.as_uri() + ("/" if entry.is_dir() else ""))
        if entry.is_dir():
            rows.append(f'<a class="entry dir" href="{url}">📁 {html.escape(entry.name)}</a>')
        else:
            try:
                size = entry.stat().st_size
                size_text = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
            except OSError:
                size_text = ""
            rows.append(f'<span class="entry file"><a href="{url}">📄 {html.escape(entry.name)}'
                        f'<span class="size">{html.escape(size_text)}</span></a>'
                        f'{_action_link("edit", entry, "✏") if is_text_file(entry) else ""}'
                        f'{_action_link("rename", entry, "↔")}</span>')
    root = _git_root(folder)
    git_html = ""
    if root is not None:
        branches = _git_branches(root)
        branch = branch if branch in branches else (branches[0] if branches else "HEAD")
        options = "".join(f'<option {"selected" if b == branch else ""}>{html.escape(b)}</option>' for b in branches)
        selector = (f'<select onchange="location.href=\'browser-action://branch?path={quote(str(folder))}&branch=\'+encodeURIComponent(this.value)">'
                    f'{options}</select>') if branches else ""
        commits = _git_commits(root, branch=branch)
        items = "".join(
            f'<div class="commit"><a href="browser-action://commit?path={quote(str(folder))}&branch={quote(branch)}&hash={quote(c[0])}">'
            f'{html.escape(c[1])} {html.escape(c[2])} {html.escape(c[3])} {html.escape(c[4])}</a></div>' for c in commits
        )
        detail = _git_commit_detail(root, selected_commit) if selected_commit else ""
        git_html = (f'<section class="git"><h2>Historial de Git {selector}</h2>'
                    f'<div class="muted">🔀 Repositorio: {html.escape(str(root))}</div>{items or "<p class=\"muted\">Sin commits todavía.</p>"}{detail}</section>')
    if archive_source:
        relative = folder.relative_to(archive_root)
        display_name = str(archive_source)
        if relative.parts:
            display_name += "\\" + "\\".join(relative.parts)
        heading = f"📦 {html.escape(display_name)}"
        page_title = display_name
    else:
        heading = f"📁 {html.escape(str(folder))}"
        page_title = folder.name or str(folder)
    body = (
        f"<header>{heading}</header><main>"
        f"<section class='folder-scroll'><h2>Contenido</h2>"
        f"{''.join(rows) or '<p class=\"muted\">Carpeta vacía</p>'}</section>"
        f"{git_html}</main>"
    )
    return _page(page_title, body)


def _git_commit_detail(root, commit):
    result = _git_run(root, ["show", "--stat", "--format=fuller", "--no-renames", commit])
    return f"<pre class='commit-detail'>{html.escape(result.stdout if result else 'No se pudo leer el commit.')}</pre>"


def render_folder_view(page, folder_path):
    page.setProperty("_folder_path", str(Path(folder_path).resolve()))
    page.setHtml(render_folder_html(folder_path), QUrl.fromLocalFile(str(Path(folder_path)) + os.sep))


def render_file_view(page, file_path, editing=False):
    path = Path(file_path).resolve()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        page.setHtml(render_file_html(path, editing), QUrl.fromLocalFile(str(path)))
        return
    bridge = _EditorBridge(page, path)
    channel = QWebChannel(page)
    channel.registerObject("editor", bridge)
    page.setWebChannel(channel)
    page._folder_viewer_bridge = bridge
    page._folder_viewer_channel = channel
    page.setProperty("_file_path", str(path))
    page.setHtml(render_file_html(path, editing), QUrl.fromLocalFile(str(path)))


def _page(title, body, file_view=False):
    extra = '.code { white-space: pre; } .code-line { display:block; } .ln { display:inline-block; width:4em; text-align:right; margin-right:1em; color:#666; user-select:none; pointer-events:none; } .code-text { white-space:pre-wrap; } button { margin-left:8px; padding:3px 7px; background:#383838; color:#eee; border:1px solid #555; border-radius:4px; } #editor { display:grid; grid-template-columns:5em minmax(0,1fr); min-height:80vh; outline:1px solid #555; } #editor .line-numbers { margin:0; padding:20px 8px; text-align:right; color:#666; user-select:none; pointer-events:none; } #editor .editable-code { margin:0; min-height:80vh; padding:20px; outline:0; background:#181818; color:#ddd; font:13px/1.5 "SF Mono",Consolas,monospace; white-space:pre-wrap; }' if file_view else ""
    style = f"""<style>* {{ box-sizing:border-box; }} body {{ margin:0; background:#1e1e1e; color:#e6e6e6; font-family:-apple-system,"Segoe UI",Arial,sans-serif; }} header {{ padding:14px 20px; border-bottom:1px solid #3a3a3a; color:#aaa; word-break:break-all; }} main {{ display:flex; gap:20px; height:calc(100vh - 65px); padding:16px; }} section {{ flex:1; min-width:0; min-height:0; }} .folder-scroll,.git {{ overflow:auto; }} h2 {{ font-size:12px; text-transform:uppercase; color:#888; }} a {{ color:#e6e6e6; }} a.entry {{ display:flex; justify-content:space-between; padding:7px 10px; border-radius:6px; text-decoration:none; font-size:13.5px; }} a.entry:hover,.commit:hover {{ background:#2c2c2c; }} .entry.file {{ display:flex; align-items:center; padding:7px 10px; }} .entry.file>a:first-child {{ flex:1; text-decoration:none; }} .button {{ margin-left:8px; padding:3px 6px; background:#383838; border-radius:4px; text-decoration:none; }} .size,.muted {{ color:#888; font-size:12px; }} .size {{ margin-left:12px; }} .commit {{ padding:6px 10px; font:12px "SF Mono",Consolas,monospace; }} .code {{ margin:0; padding:20px; overflow:auto; font:13px/1.5 "SF Mono",Consolas,monospace; background:#181818; color:#ddd; }} .commit-detail {{ white-space:pre-wrap; background:#181818; padding:10px; }} .string {{ color:#ce9178; }} .comment {{ color:#6a9955; }} .keyword {{ color:#569cd6; }} .number {{ color:#b5cea8; }} .md-heading {{ color:#4ec9b0; font-weight:bold; }} {extra}</style>"""
    script = """<script>
document.addEventListener('DOMContentLoaded',function(){
 const lines=[...document.querySelectorAll('.code-line')];
 const content=line=>line.textContent.slice(line.querySelector('.ln').textContent.length);
 function matchingBlock(start, opener, closer) {
  let depth=0;
  for(let j=start;j<lines.length;j++) {
   const text=content(lines[j]);
   for(const ch of text) {
    if(ch===opener) depth++;
    if(ch===closer) depth--;
   }
   if(depth===0 && j>start) return j;
  }
  return lines.length;
 }
 lines.forEach((line,i)=>{
  const text=content(line), trimmed=text.trim();
  const declaration=/\\b(class|def|function|async\\s+function|interface|struct|enum|namespace|switch|try)\\b/.test(trimmed);
  const opener=(trimmed.match(/[({\\[]\\s*$/)||[])[0];
  if (declaration || opener) {
   line.classList.add('foldable'); line.title='Click para plegar';
   line.onclick=function(e){
    if(e.target.closest('a,button')) return;
    const hidden=line.dataset.folded==='1';
    let end=i+1;
    const bracket=trimmed.endsWith('{')?'{}':trimmed.endsWith('[')?'[]':trimmed.endsWith('(')?'()':null;
    if(bracket) end=matchingBlock(i,bracket[0],bracket[1]);
    else {
     const base=(text.match(/^\\s*/)||[''])[0].length;
     while(end<lines.length) {
      const next=content(lines[end]), indent=(next.match(/^\\s*/)||[''])[0].length;
      if(next.trim() && indent<=base) break;
      end++;
     }
    }
    for(let j=i+1;j<end;j++) lines[j].style.display=hidden?'block':'none';
    line.dataset.folded=hidden?'0':'1';
   };
  }
 });
});
</script>""" if file_view else ""
    editor_script = """<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
let editorBridge;
new QWebChannel(qt.webChannelTransport, function(channel) {
  editorBridge = channel.objects.editor;
});
function startEdit() {
  document.getElementById('viewer').hidden = true;
  document.querySelector('header button').hidden = true;
  const editor = document.getElementById('editor');
  editor.hidden = false;
  if (!document.getElementById('edit-actions')) {
    const actions = document.createElement('span');
    actions.id = 'edit-actions';
    actions.innerHTML = '<button type="button" onclick="cancelEdit()">Cancelar</button><button type="button" onclick="saveEdit()">Guardar</button>';
    document.querySelector('header').appendChild(actions);
  }
  editor.focus();
}
function cancelEdit() {
  const path = encodeURIComponent(document.getElementById('editor').dataset.path);
  location.href = 'browser-action://cancel?path=' + path;
}
function saveEdit() {
  if (!editorBridge) { setTimeout(saveEdit, 100); return; }
  const editor = document.getElementById('editor');
  const source = editor.querySelector('.editable-code').innerText;
  editorBridge.save(source);
}
function saveEditLink(link) {
  const editor = document.getElementById('editor');
  const source = editor.querySelector('.editable-code').innerText;
  link.href = 'browser-action://save?path=' + encodeURIComponent(editor.dataset.path)
    + '&content=' + encodeURIComponent(source);
  return true;
}
</script>""" if file_view else ""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>{style}</head><body>{body}{script}{editor_script}</body></html>"


def handle_action(page, url):
    """Handle only the narrowly scoped actions generated by this module."""
    query = parse_qs(url.query())
    action = url.host()
    raw_path = unquote(query.get("path", [""])[0])
    path = Path(raw_path).absolute()
    allowed_folder = Path(str(page.property("_folder_path"))).absolute() if page.property("_folder_path") else None
    current_file = Path(page.url().toLocalFile()).absolute() if page.url().isLocalFile() else None
    if action in {"rename", "edit", "cancel", "save"}:
        if allowed_folder is not None:
            if path.parent != allowed_folder:
                return True
        elif current_file is None or path != current_file:
            return True
        try:
            if path.resolve().parent != path.parent:
                return True
        except OSError:
            return True
    if action in {"rename", "edit"} and (not path.exists() or not path.is_file()):
        QMessageBox.warning(page.view_widget, "Error", "El archivo ya no existe.")
        return True
    if action == "rename":
        dialog = QDialog(page.view_widget)
        dialog.setWindowTitle("Renombrar archivo")
        layout = QVBoxLayout(dialog)
        edit = QLineEdit(path.name)
        layout.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = edit.text().strip()
            target = (path.parent / name).resolve()
            if not name or Path(name).name != name or target.parent != path.parent.resolve() or target.exists():
                QMessageBox.warning(page.view_widget, "Error", "Nombre inválido o destino existente.")
            else:
                try: path.rename(target)
                except OSError as exc: QMessageBox.warning(page.view_widget, "Error", str(exc))
                else: render_folder_view(page, path.parent)
        return True
    if action == "edit":
        render_file_view(page, path, editing=True)
        return True
    if action == "cancel":
        render_file_view(page, path, editing=False)
        return True
    if action == "save":
        source = query.get("content", [""])[0]
        try:
            if len(source.encode("utf-8")) > MAX_TEXT_BYTES:
                raise ValueError("El texto supera el límite de 2 MiB.")
            path.write_text(source, encoding="utf-8", newline="")
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(page.view_widget, "Error", str(exc))
        else:
            render_file_view(page, path, editing=False)
        return True
    if action in {"branch", "commit"}:
        folder = Path(unquote(query.get("path", [""])[0])).absolute()
        if allowed_folder is not None and folder != allowed_folder:
            return True
        root = _git_root(folder)
        if root is None: return True
        branch = query.get("branch", [""])[0]
        branches = _git_branches(root)
        if branch and branch not in branches: return True
        commit = query.get("hash", [""])[0] if action == "commit" else None
        if commit and not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit): return True
        if commit:
            check = _git_run(root, ["merge-base", "--is-ancestor", commit, branch or "HEAD"])
            if check is None or check.returncode != 0:
                return True
        page.setHtml(render_folder_html(folder, branch or None, commit), QUrl.fromLocalFile(str(folder) + os.sep))
        return True
    return False


def render_error(path, message):
    return _page(os.path.basename(path), f"<h1>{html.escape(os.path.basename(path))}</h1><p class='muted'>{html.escape(message)}</p>")
