import json
import os
import shutil


class JsonListStore:
    def __init__(self, path, default_items=None):
        self.path = path
        self.default_items = default_items or []
        self._items = []
        self._next_id = 1
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._items = data.get("items", [])
                self._next_id = data.get("next_id", self._compute_next_id())
                return
            except Exception as exc:
                print(f"No se pudo leer {self.path}, se usan valores por defecto: {exc}")

        self._items = []
        self._next_id = 1
        for item in self.default_items:
            self._add_no_save(item["name"], item["url"])
        self.save()

    def save(self):
        data = {"next_id": self._next_id, "items": self._items}
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    def _compute_next_id(self):
        return max((i["id"] for i in self._items), default=0) + 1

    def all(self):
        return list(self._items)

    def get(self, item_id):
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def count(self):
        return len(self._items)

    def _add_no_save(self, name, url, **extra):
        item = {"id": self._next_id, "name": name, "url": url}
        item.update(extra)
        item.setdefault("kind", "link")
        self._items.append(item)
        self._next_id += 1
        return item

    def add(self, name, url, **extra):
        item = self._add_no_save(name, url, **extra)
        self.save()
        return item

    def remove(self, item_id):
        self._items = [i for i in self._items if i["id"] != item_id]
        self.save()

    def update_item(self, item_id, **fields):
        item = self.get(item_id)
        if item is None:
            return None
        item.update(fields)
        self.save()
        return item

    def export_to(self, dest_path):
        shutil.copyfile(self.path, dest_path)

    def import_from(self, src_path):
        with open(src_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_items = data.get("items", data) if isinstance(data, dict) else data
        normalized = []
        next_id = 1
        for entry in raw_items:
            item = {
                "id": next_id,
                "name": entry.get("name", "Sin nombre"),
                "url": entry.get("url", ""),
            }
            for extra_key in (
                "kind",
                "download_url",
                "local_entry",
                "icon_path",
                "favicon",
            ):
                if extra_key in entry:
                    item[extra_key] = entry[extra_key]
            item.setdefault("kind", "link")
            normalized.append(item)
            next_id += 1

        self._items = normalized
        self._next_id = next_id
        self.save()


class SidebarAppsStore(JsonListStore):
    pass


class GamesStore(JsonListStore):
    def add_offline_zip(self, name, download_url):
        return self.add(name, "", kind="offline_zip", download_url=download_url, local_entry=None)

    def set_local_entry(self, item_id, local_path):
        return self.update_item(item_id, local_entry=local_path)

