function entryClick(link, evt) {
  evt.preventDefault();
  const row = link.closest('.entry');
  if (!row || row.classList.contains('renaming')) return false;
  if (row._renameTimer) clearTimeout(row._renameTimer);
  if (row.classList.contains('selected')) {
    row._renameTimer = setTimeout(function () { beginRename(row.querySelector('.entry-name')); }, 280);
  } else {
    document.querySelectorAll('.entry.selected').forEach(function (r) { r.classList.remove('selected'); });
    row.classList.add('selected');
  }
  return false;
}
function entryDblClick(link, evt) {
  evt.preventDefault();
  if (link.closest('.entry')._renameTimer) clearTimeout(link.closest('.entry')._renameTimer);
  if (link.dataset.url) location.href = link.dataset.url;
  return false;
}
function beginRename(nameEl) {
  if (!nameEl || nameEl.isContentEditable) return;
  const row = nameEl.closest('.entry'), original = nameEl.textContent;
  row.classList.add('renaming'); nameEl.contentEditable = 'true'; nameEl.spellcheck = false; nameEl.focus();
  document.execCommand('selectAll', false, null);
  function finish(commit) {
    nameEl.removeEventListener('blur', onBlur); nameEl.removeEventListener('keydown', onKey);
    nameEl.contentEditable = 'false'; row.classList.remove('renaming'); row.classList.remove('selected');
    const value = nameEl.textContent.trim();
    if (commit && value && value !== original) location.href = 'browser-action://rename?path=' + encodeURIComponent(nameEl.dataset.path) + '&name=' + encodeURIComponent(value);
    else nameEl.textContent = original;
  }
  function onBlur() { finish(true); }
  function onKey(e) { if (e.key === 'Enter') { e.preventDefault(); nameEl.blur(); } else if (e.key === 'Escape') { e.preventDefault(); finish(false); } }
  nameEl.addEventListener('blur', onBlur); nameEl.addEventListener('keydown', onKey);
}
function openImport(link) { location.href = link.dataset.action; return false; }
let folderSortDescending = false;
function sortFolderEntries(field) {
  const container = document.querySelector('.folder-scroll');
  if (!container) return;
  const entries = [...container.querySelectorAll('.folder-entry')];
  entries.sort(function (a, b) {
    let comparison;
    if (field === 'name') {
      comparison = a.dataset.name.localeCompare(b.dataset.name);
    } else {
      comparison = Number(a.dataset[field]) - Number(b.dataset[field]);
      if (!comparison) comparison = a.dataset.name.localeCompare(b.dataset.name);
    }
    return folderSortDescending ? -comparison : comparison;
  });
  entries.forEach(function (entry) { container.appendChild(entry); });
}
function toggleFolderSortDirection() {
  folderSortDescending = !folderSortDescending;
  const button = document.getElementById('folder-sort-direction');
  button.textContent = folderSortDescending ? '↓' : '↑';
  sortFolderEntries(document.getElementById('folder-sort').value);
}
function startEdit() { document.getElementById('viewer').hidden = true; document.querySelector('header button').hidden = true; document.getElementById('editor').hidden = false; document.getElementById('editor').focus(); }
function cancelEdit() { location.href = 'browser-action://cancel?path=' + encodeURIComponent(document.getElementById('editor').dataset.path); }
function saveEditLink(link) {
  const editor = document.getElementById('editor');
  link.href = 'browser-action://save?path=' + encodeURIComponent(editor.dataset.path) + '&content=' + encodeURIComponent(editor.querySelector('.editable-code').innerText);
  return true;
}
let editorBridge;
if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
  new QWebChannel(qt.webChannelTransport, function (channel) { editorBridge = channel.objects.editor; });
}
function saveEdit() {
  if (!editorBridge) { setTimeout(saveEdit, 100); return; }
  editorBridge.save(document.getElementById('editor').querySelector('.editable-code').innerText);
}
document.addEventListener('click', function (e) {
  if (!e.target.closest('.entry-link') && !e.target.closest('.entry-name[contenteditable="true"]'))
    document.querySelectorAll('.entry.selected').forEach(function (r) { r.classList.remove('selected'); });
});
document.addEventListener('DOMContentLoaded', function () {
  const lines = [...document.querySelectorAll('.code-line')];
  lines.forEach(function (line, i) {
    const text = line.textContent.slice(line.querySelector('.ln').textContent.length);
    if (!/\b(class|def|function|async\s+function|interface|struct|enum|namespace|switch|try)\b/.test(text.trim()) && !/[({\[]\s*$/.test(text.trim())) return;
    line.classList.add('foldable'); line.title = 'Click para plegar';
    line.onclick = function (e) {
      if (e.target.closest('a,button')) return;
      const hidden = line.dataset.folded === '1';
      let end = i + 1, base = (text.match(/^\s*/) || [''])[0].length;
      while (end < lines.length) { const next = lines[end].textContent.slice(lines[end].querySelector('.ln').textContent.length); if (next.trim() && (next.match(/^\s*/) || [''])[0].length <= base) break; end++; }
      for (let j = i + 1; j < end; j++) lines[j].style.display = hidden ? 'block' : 'none';
      line.dataset.folded = hidden ? '0' : '1';
    };
  });
});
