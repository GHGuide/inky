"""SQLite store. Every table is (id, bot_id, status, ts, data JSON): one generic shape, no ORM."""
import json
import sqlite3
import threading
import time

TABLES = ("bots", "skills", "runs", "results", "messages", "events", "needs", "computers", "mcp", "diary")


def now():
    return time.time()


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.on_event = None  # the engine publishes each event live
        with self.lock:
            for t in TABLES:
                old = self.db.execute("select sql from sqlite_master where type='table' and name=?", (t,)).fetchone()
                if old and "autoincrement" not in old[0].lower():  # ids must never come back: a moved bot points at one
                    self.db.execute(f"alter table {t} rename to {t}_old")
                    self.db.execute(f"drop index if exists {t}_bot")
                self.db.execute(f"create table if not exists {t} (id integer primary key autoincrement, bot_id integer, "
                                f"status text, key text, ts real, data text)")
                if old and "autoincrement" not in old[0].lower():
                    self.db.execute(f"insert into {t} (id, bot_id, status, key, ts, data) select id, bot_id, status, key, ts, data from {t}_old")
                    self.db.execute(f"drop table {t}_old")
                self.db.execute(f"create index if not exists {t}_bot on {t}(bot_id)")
            self.db.execute("create table if not exists settings (key text primary key, value text)")
            self.db.commit()

    # ---- generic rows
    def _row(self, r):
        if r is None:
            return None
        d = json.loads(r["data"])
        d.update(id=r["id"], bot_id=r["bot_id"], status=r["status"], key=r["key"], ts=r["ts"])
        return d

    def insert(self, table, data, bot_id=None, status=None, key=None):
        with self.lock:
            cur = self.db.execute(f"insert into {table} (bot_id, status, key, ts, data) values (?,?,?,?,?)",
                                  (bot_id, status, key, now(), json.dumps(data)))
            self.db.commit()
            return cur.lastrowid

    def get(self, table, id):
        with self.lock:
            return self._row(self.db.execute(f"select * from {table} where id=?", (id,)).fetchone())

    def find(self, table, bot_id=None, status=None, key=None, limit=500, desc=True):
        q, args = f"select * from {table} where 1=1", []
        for col, val in (("bot_id", bot_id), ("status", status), ("key", key)):
            if val is not None:
                q += f" and {col}=?"
                args.append(val)
        q += f" order by id {'desc' if desc else 'asc'} limit ?"
        args.append(limit)
        with self.lock:
            return [self._row(r) for r in self.db.execute(q, args).fetchall()]

    def update(self, table, id, status=None, **patch):
        with self.lock:
            cur = self.get(table, id)
            if cur is None:
                return None
            for k in ("id", "bot_id", "status", "key", "ts"):
                cur.pop(k, None)
            cur.update(patch)
            if status is None:
                self.db.execute(f"update {table} set data=? where id=?", (json.dumps(cur), id))
            else:
                self.db.execute(f"update {table} set data=?, status=? where id=?", (json.dumps(cur), status, id))
            self.db.commit()
            return self.get(table, id)

    def delete(self, table, id=None, bot_id=None):
        with self.lock:
            if id is not None:
                self.db.execute(f"delete from {table} where id=?", (id,))
            elif bot_id is not None:
                self.db.execute(f"delete from {table} where bot_id=?", (bot_id,))
            self.db.commit()

    def upsert_key(self, table, bot_id, key, data):
        """One row per (bot, key): used for results so reruns can tell new items from seen ones."""
        with self.lock:
            r = self.db.execute(f"select id from {table} where bot_id=? and key=?", (bot_id, key)).fetchone()
            if r:
                self.update(table, r["id"], **data)
                return r["id"], False
            return self.insert(table, data, bot_id=bot_id, key=key), True

    # ---- settings
    def setting(self, key, default=None):
        with self.lock:
            r = self.db.execute("select value from settings where key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_setting(self, key, value):
        with self.lock:
            self.db.execute("insert into settings (key, value) values (?, ?) on conflict(key) do update set value=excluded.value",
                            (key, json.dumps(value)))
            self.db.commit()

    # ---- conveniences
    def event(self, bot_id, kind, text, **meta):
        i = self.insert("events", dict(kind=kind, text=text, **meta), bot_id=bot_id, status=kind)
        if self.on_event:
            self.on_event(bot_id, kind, text)
        return i

    def message(self, bot_id, role, text, **meta):
        return self.insert("messages", dict(role=role, text=text, **meta), bot_id=bot_id, status=role)
