"""Historial de navegación compartido por las aplicaciones web de IARA."""

import sqlite3
import uuid
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class HistoryStore:
    """Persiste las visitas y las agrupa por sesión de navegación."""

    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                visited_at TEXT NOT NULL,
                session_id TEXT
            )
            """
        )

        cur.execute("PRAGMA table_info(history)")
        columns = [row[1] for row in cur.fetchall()]
        if "session_id" not in columns:
            cur.execute("ALTER TABLE history ADD COLUMN session_id TEXT")
        cur.execute(
            "UPDATE history SET session_id = lower(hex(randomblob(16))) "
            "WHERE session_id IS NULL"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_session ON history(session_id)"
        )
        self.conn.commit()

    def new_session_id(self):
        return uuid.uuid4().hex

    def add_history(self, url, title, session_id=None):
        if session_id is None:
            session_id = self.new_session_id()
        self.conn.execute(
            "INSERT INTO history (url, title, visited_at, session_id) VALUES (?, ?, ?, ?)",
            (url, title, datetime.now().isoformat(timespec="seconds"), session_id),
        )
        self.conn.commit()

    def get_history_grouped(self, search=None, limit_sessions=300):
        """Devuelve sesiones recientes con todas sus visitas en orden cronológico."""
        cur = self.conn.cursor()
        if search:
            like = f"%{search}%"
            cur.execute(
                "SELECT DISTINCT session_id FROM history "
                "WHERE url LIKE ? OR title LIKE ?",
                (like, like),
            )
            session_ids = [row[0] for row in cur.fetchall()]
            if not session_ids:
                return []
            placeholders = ",".join("?" for _ in session_ids)
            cur.execute(
                f"SELECT session_id, MAX(id) AS last_id, "
                f"MAX(visited_at) AS last_visited, COUNT(*) AS visits "
                f"FROM history WHERE session_id IN ({placeholders}) "
                f"GROUP BY session_id ORDER BY last_id DESC LIMIT ?",
                (*session_ids, limit_sessions),
            )
        else:
            cur.execute(
                "SELECT session_id, MAX(id) AS last_id, "
                "MAX(visited_at) AS last_visited, COUNT(*) AS visits "
                "FROM history GROUP BY session_id "
                "ORDER BY last_id DESC LIMIT ?",
                (limit_sessions,),
            )

        result = []
        for session_id, _last_id, last_visited, visits in cur.fetchall():
            cur.execute(
                "SELECT url, title, visited_at FROM history "
                "WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            entries = cur.fetchall()
            if entries:
                result.append(
                    {
                        "session_id": session_id,
                        "visits": visits,
                        "last_visited": last_visited,
                        "entries": entries,
                    }
                )
        return result

    def clear_history(self):
        self.conn.execute("DELETE FROM history")
        self.conn.commit()


class HistoryDialog(QDialog):
    """Diálogo desplegable para consultar y abrir el historial."""

    def __init__(self, history_store, on_open=None):
        super().__init__()
        self.setWindowTitle("Historial")
        self.resize(600, 480)
        self.history_store = history_store
        self.on_open = on_open

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar en el historial...")
        self.search_input.textChanged.connect(lambda _: self._reload())
        layout.addWidget(self.search_input)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(lambda item, _column: self._open_item(item))
        layout.addWidget(self.tree)

        button_row = QHBoxLayout()
        open_button = QPushButton("Abrir")
        open_button.clicked.connect(lambda: self._open_item(self.tree.currentItem()))
        button_row.addWidget(open_button)

        clear_button = QPushButton("Vaciar todo")
        clear_button.clicked.connect(self._clear_all)
        button_row.addWidget(clear_button)
        layout.addLayout(button_row)

        self._reload()

    def _reload(self):
        query = self.search_input.text().strip()
        self.tree.clear()
        sessions = self.history_store.get_history_grouped(search=query or None)
        for session in sessions:
            entries = session["entries"]
            last_url, last_title, last_timestamp = entries[-1]
            label = f"{last_title or last_url}   [{last_timestamp}]"
            if len(entries) > 1:
                label += f"  —  {len(entries)} páginas visitadas en esta sesión"

            top = QTreeWidgetItem([label])
            top.setData(0, Qt.ItemDataRole.UserRole, last_url)
            for url, title, timestamp in entries:
                child = QTreeWidgetItem([f"{title or url}   [{timestamp}]"])
                child.setData(0, Qt.ItemDataRole.UserRole, url)
                top.addChild(child)
            self.tree.addTopLevelItem(top)

    def _open_item(self, item):
        if not item:
            return
        url = item.data(0, Qt.ItemDataRole.UserRole)
        if url and self.on_open:
            self.on_open(url)
            self.accept()

    def _clear_all(self):
        self.history_store.clear_history()
        self.tree.clear()
