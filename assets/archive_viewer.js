function toggleFolder(row) {
  const folder = row.dataset.folder;
  const open = row.dataset.open === '1';
  document.querySelectorAll('.entry[data-parent]').forEach(function (item) {
    if (item.dataset.parent === folder) item.style.display = open ? 'none' : '';
  });
  row.dataset.open = open ? '0' : '1';
}
