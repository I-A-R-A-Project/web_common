"""Safe, dependency-free HTML views for local folders and text files."""

import html
import os
import re
import subprocess
from pathlib import Path


MAX_TEXT_BYTES = 2 * 1024 * 1024
TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".css", ".csv", ".go", ".h", ".hpp",
    ".ini", ".java", ".js", ".json", ".jsx", ".md", ".py", ".rs", ".sh",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

_TOKEN_RE = re.compile(
    r'(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)'
    r'|(?P<comment>//[^\n]*|#[^\n]*|;[^\n]*)'
    r'|(?P<number>\b\d+(?:\.\d+)?\b)'
    r'|(?P<word>[A-Za-z_][A-Za-z0-9_]*)'
)
_KEYWORDS = {
    "and", "as", "async", "await", "break", "class", "const", "def", "delete",
    "else", "elif", "export", "False", "for", "from", "function", "if",
    "import", "in", "is", "let", "None", "not", "null", "or", "pass",
    "print", "return", "static", "this", "throw", "True", "try", "var",
    "while", "with", "yield",
}


def is_text_file(path):
    path = Path(path)
    return path.suffix.lower() in TEXT_EXTENSIONS


def _highlight(source, suffix):
    if suffix == ".md":
        lines = []
        for line in source.splitlines():
            prefix = re.match(r"^(#{1,6})(\s+)", line)
            if prefix:
                lines.append(
                    '<span class="md-heading">'
                    + html.escape(line)
                    + "</span>"
                )
            else:
                lines.append(html.escape(line))
        return "\n".join(lines)

    output = []
    last = 0
    for match in _TOKEN_RE.finditer(source):
        output.append(html.escape(source[last:match.start()]))
        kind = match.lastgroup
        value = html.escape(match.group(0))
        if kind == "word" and match.group(0) in _KEYWORDS:
            cls = "keyword"
        else:
            cls = kind
        output.append(f'<span class="{cls}">{value}</span>')
        last = match.end()
    output.append(html.escape(source[last:]))
    return "".join(output)


def render_file_html(path):
    path = Path(path)
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return _page(path.name, f"<h1>{html.escape(path.name)}</h1>"
                            "<p class='muted'>Archivo demasiado grande para la vista previa.</p>")
        source = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError) as exc:
        return render_error(str(path), f"No se pudo leer el archivo: {exc}")
    code = _highlight(source, path.suffix.lower())
    return _page(
        path.name,
        f"<header>📄 {html.escape(str(path))}</header>"
        f"<pre class='code'><code>{code}</code></pre>",
        file_view=True,
    )


def _git_root(path):
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    root = result.stdout.strip()
    return Path(root) if result.returncode == 0 and root else None


def _git_commits(root, limit=50):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", f"-{limit}", "--date=short",
             "--pretty=format:%h  %ad  %an  %s"],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def render_folder_html(folder_path):
    folder = Path(folder_path).resolve()
    rows = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        entries = []
    if folder.parent != folder:
        rows.append(f'<a class="entry dir" href="{html.escape(folder.parent.as_uri() + "/")}">⬆ .. (subir un nivel)</a>')
    for entry in entries:
        url = entry.as_uri() + ("/" if entry.is_dir() else "")
        if entry.is_dir():
            rows.append(f'<a class="entry dir" href="{html.escape(url)}">📁 {html.escape(entry.name)}</a>')
        else:
            try:
                size = entry.stat().st_size
                size_text = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
            except OSError:
                size_text = ""
            rows.append(
                f'<a class="entry file" href="{html.escape(url)}">📄 {html.escape(entry.name)}'
                f'<span class="size">{html.escape(size_text)}</span></a>'
            )
    root = _git_root(folder)
    git_html = ""
    if root is not None:
        commits = _git_commits(root)
        items = "".join(f'<div class="commit">{html.escape(commit)}</div>' for commit in commits)
        git_html = (
            '<section class="git"><h2>Historial de Git</h2>'
            f'<div class="muted">🔀 Repositorio: {html.escape(str(root))}</div>'
            f'{items or "<p class=\"muted\">Sin commits todavía.</p>"}</section>'
        )
    body = (
        f"<header>📁 {html.escape(str(folder))}</header><main>"
        f"<section><h2>Contenido</h2>{''.join(rows) or '<p class=\"muted\">Carpeta vacía</p>'}</section>"
        f"{git_html}</main>"
    )
    return _page(folder.name or str(folder), body)


def render_folder_view(page, folder_path):
    from PyQt6.QtCore import QUrl
    page.setHtml(render_folder_html(folder_path), QUrl.fromLocalFile(str(Path(folder_path)) + os.sep))


def _page(title, body, file_view=False):
    extra = ".code { white-space: pre-wrap; }" if file_view else ""
    style = f"""
    <style>
    * {{ box-sizing: border-box; }} body {{ margin:0; background:#1e1e1e; color:#e6e6e6;
      font-family:-apple-system,"Segoe UI",Arial,sans-serif; }}
    header {{ padding:14px 20px; border-bottom:1px solid #3a3a3a; color:#aaa; word-break:break-all; }}
    main {{ display:flex; gap:20px; padding:16px; }} section {{ flex:1; min-width:0; }}
    h2 {{ font-size:12px; text-transform:uppercase; color:#888; }}
    a.entry {{ display:flex; justify-content:space-between; padding:7px 10px; border-radius:6px;
      color:#e6e6e6; text-decoration:none; font-size:13.5px; }} a.entry:hover {{ background:#2c2c2c; }}
    .size,.muted {{ color:#888; font-size:12px; }} .size {{ margin-left:12px; }}
    .commit {{ padding:6px 10px; font:12px "SF Mono",Consolas,monospace; }}
    .commit:hover {{ background:#2c2c2c; }} .code {{ margin:0; padding:20px; overflow:auto;
      font:13px/1.5 "SF Mono",Consolas,monospace; background:#181818; color:#ddd; }}
    .string {{ color:#ce9178; }} .comment {{ color:#6a9955; }} .keyword {{ color:#569cd6; }}
    .number {{ color:#b5cea8; }} .md-heading {{ color:#4ec9b0; font-weight:bold; }}
    {extra}
    </style>"""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>{style}</head><body>{body}</body></html>"


def render_error(path, message):
    return _page(os.path.basename(path), f"<h1>{html.escape(os.path.basename(path))}</h1><p class='muted'>{html.escape(message)}</p>")
