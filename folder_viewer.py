"""Safe, dependency-free HTML views for local folders and text files."""

import html
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

from PyQt6.QtCore import QObject, QUrl, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWidgets import QMessageBox
from . import local_viewer
from .local_file_types import is_text_file

MAX_TEXT_BYTES = 2 * 1024 * 1024
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
    dir_text = html.escape(str(path.parent) + os.sep)
    name_span = _entry_name_span(path)
    return (
        f"<header><span class='entry name-only'><a class='entry-link' href='#' "
        f"onclick='return entryClick(this,event)'>📄 <span class='path-dir'>{dir_text}</span>"
        f"{name_span}</a></span>{actions}</header>"
        f"<div id='viewer'{viewer_hidden}><pre class='code'><code>{_code_html(source, path.suffix.lower())}</code></pre></div>"
        f"<div id='editor' data-path='{html.escape(str(path))}'{editor_hidden}><div class='editor-scroll'>"
        f"<pre class='line-numbers' aria-hidden='true'>{''.join(str(i) + chr(10) for i in range(1, source.count(chr(10)) + 2))}</pre>"
        f"<pre class='editable-code' contenteditable='true' spellcheck='false' translate='no'>{html.escape(source)}</pre>"
        f"</div></div>"
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


def _entry_name_span(path):
    p = Path(path).absolute()
    return (
        f'<span class="entry-name" data-path="{html.escape(str(p), quote=True)}">'
        f'{html.escape(p.name)}</span>'
    )


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
        name_span = _entry_name_span(entry)
        if entry.is_dir():
            rows.append(
                f'<span class="entry dir"><a class="entry-link" href="#" data-url="{url}" '
                f'onclick="return entryClick(this,event)" ondblclick="return entryDblClick(this,event)">'
                f'📁 {name_span}</a></span>'
            )
        else:
            try:
                size = entry.stat().st_size
                size_text = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
            except OSError:
                size_text = ""
            rows.append(
                f'<span class="entry file"><a class="entry-link" href="#" data-url="{url}" '
                f'onclick="return entryClick(this,event)" ondblclick="return entryDblClick(this,event)">'
                f'📄 {name_span}<span class="size">{html.escape(size_text)}</span></a></span>'
            )
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
    extra = ('.code { white-space: pre; } .code-line { display:block; border-radius:4px; } '
             '.code-line.foldable { cursor:pointer; } .code-line.foldable:hover { background:#1c1d21; } '
             '.ln { display:inline-block; width:4em; text-align:right; margin-right:1em; color:#5a5e66; user-select:none; pointer-events:none; } '
             '.code-text { white-space:pre-wrap; } '
             'button { margin-left:6px; padding:4px 10px; background:#2a2b30; color:#f1f3f4; border:1px solid #3a3b42; '
             'border-radius:6px; cursor:pointer; font-size:12px; } button:hover { background:#3a3b42; } '
             '#editor:not([hidden]) .editor-scroll { display:grid; grid-template-columns:5em minmax(0,1fr); '
             'height:80vh; overflow:auto; border-radius:8px; outline:1px solid #2c2d31; } '
             '#editor .line-numbers { margin:0; padding:20px 8px; text-align:right; color:#5a5e66; user-select:none; '
             'pointer-events:none; background:#101114; } '
             '#editor .editable-code { margin:0; padding:20px; outline:0; background:#141518; color:#ddd; '
             'font:13px/1.5 "SF Mono",Consolas,monospace; white-space:pre; tab-size:2; }') if file_view else ""
    style = f"""<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#16171a; color:#e6e6e6; font-family:-apple-system,"Segoe UI",Arial,sans-serif; }}
header {{ display:flex; align-items:center; flex-wrap:wrap; gap:10px; padding:14px 20px; background:#1c1d21;
  border-bottom:1px solid #2c2d31; color:#9aa0a6; word-break:break-all; }}
main {{ display:flex; gap:20px; height:calc(100vh - 65px); padding:16px; }}
section {{ flex:1; min-width:0; min-height:0; }}
.folder-scroll,.git {{ overflow:auto; }}
h2 {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:#7b8087; margin:4px 0 10px; display:flex; align-items:center; gap:8px; }}
a {{ color:#e6e6e6; }}
.entry {{ display:flex; align-items:center; padding:6px 10px; border-radius:8px; font-size:13.5px;
  text-decoration:none; transition:background-color .1s; }}
a.entry {{ justify-content:space-between; }}
.entry:hover, .commit:hover {{ background:#24252a; }}
.entry.selected {{ background:#20262e; outline:1px solid #33404d; }}
.entry.renaming {{ background:#20262e; outline:1px solid #4a90e2; }}
.entry.name-only {{ padding:2px 4px; }}
.entry.name-only:hover {{ background:none; }}
.entry.name-only.selected, .entry.name-only.renaming {{ background:none; outline:none; }}
.entry-link {{ flex:1; min-width:0; display:flex; align-items:center; gap:8px; color:#e6e6e6;
  text-decoration:none; overflow:hidden; cursor:pointer; }}
.entry-name {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; border-radius:4px; padding:1px 3px; }}
.entry-name[contenteditable="true"] {{ background:#101114; outline:1px solid #4a90e2; white-space:normal; overflow:visible; cursor:text; }}
.path-dir {{ color:#6c7077; }}
.action, .button {{ display:inline-flex; align-items:center; justify-content:center; padding:3px 7px;
  background:#2a2b30; color:#c7cad0; border-radius:6px; text-decoration:none; font-size:12px; border:none; }}
.action:hover, .button:hover {{ background:#3a3b42; color:#f1f3f4; }}
.size,.muted {{ color:#7b8087; font-size:12px; }}
.size {{ margin-left:8px; flex-shrink:0; }}
.commit {{ padding:6px 10px; border-radius:6px; font:12px "SF Mono",Consolas,monospace; color:#c7cad0; }}
.commit a {{ text-decoration:none; color:inherit; }}
.code {{ margin:0; padding:20px; overflow:auto; font:13px/1.5 "SF Mono",Consolas,monospace; background:#141518; color:#ddd; }}
.commit-detail {{ white-space:pre-wrap; background:#141518; padding:10px; border-radius:6px; margin-top:6px; }}
.string {{ color:#ce9178; }}
.comment {{ color:#6a9955; }}
.keyword {{ color:#569cd6; }}
.number {{ color:#b5cea8; }}
.md-heading {{ color:#4ec9b0; font-weight:bold; }}
::-webkit-scrollbar {{ width:10px; height:10px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:#3a3b42; border-radius:5px; }}
::-webkit-scrollbar-thumb:hover {{ background:#4a4b52; }}
{extra}
</style>"""
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
(function () {
  const editor = document.getElementById('editor');
  if (!editor) return;
  const codeEl = editor.querySelector('.editable-code');
  const numsEl = editor.querySelector('.line-numbers');
  function syncLineNumbers() {
    const lines = codeEl.innerText.split('\\n').length;
    let out = '';
    for (let i = 1; i <= lines; i++) out += i + '\\n';
    numsEl.textContent = out;
  }
  codeEl.addEventListener('input', syncLineNumbers);
  codeEl.addEventListener('keydown', function (e) {
    if (e.key === 'Tab') {
      e.preventDefault();
      document.execCommand('insertText', false, '  ');
    } else if (e.key === 'Enter') {
      e.preventDefault();
      document.execCommand('insertText', false, '\\n');
    }
  });
  codeEl.addEventListener('paste', function (e) {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData('text/plain');
    document.execCommand('insertText', false, text);
  });
})();
</script>""" if file_view else ""
    rename_script = """<script>
function entryClick(link, evt) {
  evt.preventDefault();
  const row = link.closest('.entry');
  if (!row || row.classList.contains('renaming')) return false;
  if (row._renameTimer) { clearTimeout(row._renameTimer); row._renameTimer = null; }
  if (row.classList.contains('selected')) {
    row._renameTimer = setTimeout(function () {
      row._renameTimer = null;
      beginRename(row.querySelector('.entry-name'));
    }, 280);
  } else {
    document.querySelectorAll('.entry.selected').forEach(function (r) { r.classList.remove('selected'); });
    row.classList.add('selected');
  }
  return false;
}
function entryDblClick(link, evt) {
  evt.preventDefault();
  const row = link.closest('.entry');
  if (row && row._renameTimer) { clearTimeout(row._renameTimer); row._renameTimer = null; }
  const url = link.dataset.url;
  if (url) location.href = url;
  return false;
}
function beginRename(nameEl) {
  if (!nameEl || nameEl.isContentEditable) return;
  const row = nameEl.closest('.entry');
  const original = nameEl.textContent;
  row.classList.add('renaming');
  nameEl.contentEditable = 'true';
  nameEl.spellcheck = false;
  nameEl.focus();
  document.execCommand('selectAll', false, null);
  function finish(commit) {
    nameEl.removeEventListener('blur', onBlur);
    nameEl.removeEventListener('keydown', onKey);
    nameEl.contentEditable = 'false';
    row.classList.remove('renaming');
    row.classList.remove('selected');
    const value = nameEl.textContent.trim();
    if (commit && value && value !== original) {
      const path = nameEl.dataset.path;
      location.href = 'browser-action://rename?path=' + encodeURIComponent(path)
        + '&name=' + encodeURIComponent(value);
    } else {
      nameEl.textContent = original;
    }
  }
  function onBlur() { finish(true); }
  function onKey(e) {
    if (e.key === 'Enter') { e.preventDefault(); nameEl.blur(); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  }
  nameEl.addEventListener('blur', onBlur);
  nameEl.addEventListener('keydown', onKey);
}
document.addEventListener('click', function (e) {
  if (!e.target.closest('.entry-link') && !e.target.closest('.entry-name[contenteditable="true"]')) {
    document.querySelectorAll('.entry.selected').forEach(function (r) { r.classList.remove('selected'); });
  }
});
</script>"""
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>{style}</head>"
            f"<body>{body}{rename_script}{script}{editor_script}</body></html>")


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
    if action in {"rename", "edit"} and not path.exists():
        QMessageBox.warning(page.view_widget, "Error", "El elemento ya no existe.")
        return True
    if action == "edit" and not path.is_file():
        return True
    if action == "rename":
        name = unquote(query.get("name", [""])[0]).strip()
        target = (path.parent / name).resolve()
        if not name or Path(name).name != name or target.parent != path.parent.resolve() or target.exists():
            QMessageBox.warning(page.view_widget, "Error", "Nombre inválido o destino existente.")
            return True
        try:
            path.rename(target)
        except OSError as exc:
            QMessageBox.warning(page.view_widget, "Error", str(exc))
            return True
        if current_file is not None and path == current_file:
            render_file_view(page, target)
        else:
            render_folder_view(page, path.parent)
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
