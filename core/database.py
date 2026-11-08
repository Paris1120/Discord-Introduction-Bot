import json
import time
from datetime import datetime, timezone

import aiosqlite

from config import (DEFAULT_ALT_DAYS, DEFAULT_BANNED_WORDS, DEFAULT_NEWFACE_DAYS,
                    DEFAULT_UNV_KICK_HOURS, DEFAULT_UNV_WARN_HOURS)
from core.messages import DEFAULT_MESSAGES
from core.validators import normalize

SETTINGS_COLUMNS = {
    "intro_channel_id":   ("INTEGER", None),
    "log_channel_id":     ("INTEGER", None),
    "leave_channel_id":   ("INTEGER", None),
    "admin_channel_id":   ("INTEGER", None),
    "role_id":            ("INTEGER", None),
    "unverified_role_id": ("INTEGER", None),
    "male_role_id":       ("INTEGER", None),
    "female_role_id":     ("INTEGER", None),
    "nick_prefix":        ("TEXT DEFAULT ''", ""),
    "newface_enabled":    ("INTEGER DEFAULT 0", 0),
    "newface_days":       (f"INTEGER DEFAULT {DEFAULT_NEWFACE_DAYS}", DEFAULT_NEWFACE_DAYS),
    "alt_warn_enabled":   ("INTEGER DEFAULT 0", 0),
    "alt_warn_days":      (f"INTEGER DEFAULT {DEFAULT_ALT_DAYS}", DEFAULT_ALT_DAYS),
    "welcome_dm_enabled": ("INTEGER DEFAULT 1", 1),
    "unv_enabled":        ("INTEGER DEFAULT 0", 0),
    "unv_since":          ("INTEGER", None),
    "unv_warn_hours":     (f"INTEGER DEFAULT {DEFAULT_UNV_WARN_HOURS}", DEFAULT_UNV_WARN_HOURS),
    "unv_kick_hours":     (f"INTEGER DEFAULT {DEFAULT_UNV_KICK_HOURS}", DEFAULT_UNV_KICK_HOURS),
    "unv_lock_auto":      ("INTEGER DEFAULT 1", 1),
    "banned_seeded":      ("INTEGER DEFAULT 0", 0),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS intros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    name TEXT NOT NULL, age INTEGER NOT NULL, gender TEXT NOT NULL, route TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prefix TEXT DEFAULT '', prefix_removed INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_intros_guild_user ON intros(guild_id, user_id);
CREATE TABLE IF NOT EXISTS age_roles (
    guild_id INTEGER, bracket TEXT, role_id INTEGER, PRIMARY KEY (guild_id, bracket));
CREATE TABLE IF NOT EXISTS main_channels (
    guild_id INTEGER, channel_id INTEGER, description TEXT, added_at TEXT,
    PRIMARY KEY (guild_id, channel_id));
CREATE TABLE IF NOT EXISTS messages (
    guild_id INTEGER, key TEXT, title TEXT, body TEXT, PRIMARY KEY (guild_id, key));
CREATE TABLE IF NOT EXISTS banned_words (
    guild_id INTEGER, word TEXT, added_at INTEGER, PRIMARY KEY (guild_id, word));
CREATE TABLE IF NOT EXISTS exempt_roles (
    guild_id INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, role_id));
CREATE TABLE IF NOT EXISTS saved_roles (
    guild_id INTEGER, user_id INTEGER, role_ids TEXT, saved_at INTEGER,
    PRIMARY KEY (guild_id, user_id));
CREATE TABLE IF NOT EXISTS unv_warns (
    guild_id INTEGER, user_id INTEGER, warned_at INTEGER, PRIMARY KEY (guild_id, user_id));
CREATE TABLE IF NOT EXISTS filter_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER, user_id INTEGER, content TEXT, reason TEXT, created_at INTEGER);
CREATE INDEX IF NOT EXISTS idx_filter_guild_user ON filter_logs(guild_id, user_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.cache: dict[int, dict] = {}

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self._migrate()
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def _columns(self, table: str) -> set[str]:
        async with self.conn.execute(f"PRAGMA table_info({table})") as cur:
            return {r["name"] for r in await cur.fetchall()}

    async def _migrate(self):
        cols = await self._columns("settings")
        for col, (typ, _) in SETTINGS_COLUMNS.items():
            if col not in cols:
                await self.conn.execute(f"ALTER TABLE settings ADD COLUMN {col} {typ}")
        if "remove_role_id" in cols:  # v1/v2의 '제거 역할'을 미인증 역할로 이전
            await self.conn.execute(
                "UPDATE settings SET unverified_role_id = remove_role_id "
                "WHERE unverified_role_id IS NULL AND remove_role_id IS NOT NULL")
        icols = await self._columns("intros")
        if "prefix" not in icols:
            await self.conn.execute("ALTER TABLE intros ADD COLUMN prefix TEXT DEFAULT ''")
        if "prefix_removed" not in icols:
            await self.conn.execute("ALTER TABLE intros ADD COLUMN prefix_removed INTEGER DEFAULT 0")

    # ── settings ──
    async def get_settings(self, guild_id: int) -> dict:
        if guild_id in self.cache:
            return self.cache[guild_id]
        async with self.conn.execute("SELECT * FROM settings WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
        data = {k: default for k, (_, default) in SETTINGS_COLUMNS.items()}
        if row:
            for k in SETTINGS_COLUMNS:
                if row[k] is not None:
                    data[k] = row[k]
        self.cache[guild_id] = data
        return data

    async def set_settings(self, guild_id: int, **values):
        for k in values:
            if k not in SETTINGS_COLUMNS:
                raise ValueError(f"잘못된 설정 키: {k}")
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        updates = ", ".join(f"{k} = excluded.{k}" for k in values)
        await self.conn.execute(
            f"INSERT INTO settings (guild_id, {cols}) VALUES (?, {marks}) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {updates}",
            (guild_id, *values.values()))
        await self.conn.commit()
        self.cache.pop(guild_id, None)

    # ── intros ──
    async def add_intro(self, guild_id: int, user_id: int, d: dict, prefix: str,
                        prefix_removed: bool = False, created_at: str | None = None):
        await self.conn.execute(
            "INSERT INTO intros (guild_id, user_id, name, age, gender, route, created_at, prefix, prefix_removed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, d["name"], d["age"], d["gender"], d["route"],
             created_at or datetime.now(timezone.utc).isoformat(), prefix, int(prefix_removed)))
        await self.conn.commit()

    async def get_latest(self, guild_id: int, user_id: int):
        async with self.conn.execute(
            "SELECT * FROM intros WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
            (guild_id, user_id)) as cur:
            return await cur.fetchone()

    async def get_records(self, guild_id: int):
        """유저별 최신 1건, 최신순"""
        async with self.conn.execute("""
            SELECT * FROM intros
            WHERE id IN (SELECT MAX(id) FROM intros WHERE guild_id = ? GROUP BY user_id)
            ORDER BY id DESC""", (guild_id,)) as cur:
            return await cur.fetchall()

    async def delete_user_intros(self, guild_id: int, user_id: int):
        await self.conn.execute("DELETE FROM intros WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await self.conn.commit()

    async def mark_prefix_removed(self, intro_id: int):
        await self.conn.execute("UPDATE intros SET prefix_removed = 1 WHERE id = ?", (intro_id,))
        await self.conn.commit()

    # ── age roles ──
    async def get_age_roles(self, guild_id: int) -> dict[str, int]:
        async with self.conn.execute(
            "SELECT bracket, role_id FROM age_roles WHERE guild_id = ?", (guild_id,)) as cur:
            return {r["bracket"]: r["role_id"] for r in await cur.fetchall()}

    async def set_age_role(self, guild_id: int, bracket: str, role_id: int | None):
        if role_id is None:
            await self.conn.execute("DELETE FROM age_roles WHERE guild_id = ? AND bracket = ?", (guild_id, bracket))
        else:
            await self.conn.execute(
                "INSERT INTO age_roles (guild_id, bracket, role_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, bracket) DO UPDATE SET role_id = excluded.role_id",
                (guild_id, bracket, role_id))
        await self.conn.commit()

    # ── main channels ──
    async def get_main_channels(self, guild_id: int) -> list[tuple[int, str]]:
        async with self.conn.execute(
            "SELECT channel_id, description FROM main_channels WHERE guild_id = ? ORDER BY added_at",
            (guild_id,)) as cur:
            return [(r["channel_id"], r["description"]) for r in await cur.fetchall()]

    async def add_main_channel(self, guild_id: int, channel_id: int, desc: str):
        await self.conn.execute(
            "INSERT INTO main_channels (guild_id, channel_id, description, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, channel_id) DO UPDATE SET description = excluded.description",
            (guild_id, channel_id, desc, datetime.now(timezone.utc).isoformat()))
        await self.conn.commit()

    async def remove_main_channel(self, guild_id: int, channel_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM main_channels WHERE guild_id = ? AND channel_id = ?", (guild_id, channel_id))
        await self.conn.commit()
        return cur.rowcount > 0

    # ── custom messages ──
    async def get_message(self, guild_id: int, key: str) -> tuple[str, str]:
        async with self.conn.execute(
            "SELECT title, body FROM messages WHERE guild_id = ? AND key = ?", (guild_id, key)) as cur:
            row = await cur.fetchone()
        return (row["title"], row["body"]) if row else DEFAULT_MESSAGES[key]

    async def set_message(self, guild_id: int, key: str, title: str, body: str):
        await self.conn.execute(
            "INSERT INTO messages (guild_id, key, title, body) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET title = excluded.title, body = excluded.body",
            (guild_id, key, title, body))
        await self.conn.commit()

    async def reset_message(self, guild_id: int, key: str):
        await self.conn.execute("DELETE FROM messages WHERE guild_id = ? AND key = ?", (guild_id, key))
        await self.conn.commit()

    # ── banned words ──
    async def get_banned_words(self, guild_id: int) -> list[str]:
        s = await self.get_settings(guild_id)
        if not s["banned_seeded"]:
            now = int(time.time())
            await self.conn.executemany(
                "INSERT OR IGNORE INTO banned_words (guild_id, word, added_at) VALUES (?, ?, ?)",
                [(guild_id, normalize(w), now) for w in DEFAULT_BANNED_WORDS])
            await self.conn.commit()
            await self.set_settings(guild_id, banned_seeded=1)
        async with self.conn.execute(
            "SELECT word FROM banned_words WHERE guild_id = ? ORDER BY added_at, word", (guild_id,)) as cur:
            return [r["word"] for r in await cur.fetchall()]

    async def add_banned_word(self, guild_id: int, word: str) -> bool:
        await self.get_banned_words(guild_id)
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO banned_words (guild_id, word, added_at) VALUES (?, ?, ?)",
            (guild_id, word, int(time.time())))
        await self.conn.commit()
        return cur.rowcount > 0

    async def remove_banned_word(self, guild_id: int, word: str) -> bool:
        await self.get_banned_words(guild_id)
        cur = await self.conn.execute(
            "DELETE FROM banned_words WHERE guild_id = ? AND word = ?", (guild_id, word))
        await self.conn.commit()
        return cur.rowcount > 0

    # ── exempt roles ──
    async def get_exempt_roles(self, guild_id: int) -> list[int]:
        async with self.conn.execute("SELECT role_id FROM exempt_roles WHERE guild_id = ?", (guild_id,)) as cur:
            return [r["role_id"] for r in await cur.fetchall()]

    async def add_exempt_role(self, guild_id: int, role_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO exempt_roles (guild_id, role_id) VALUES (?, ?)", (guild_id, role_id))
        await self.conn.commit()

    async def remove_exempt_role(self, guild_id: int, role_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM exempt_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        await self.conn.commit()
        return cur.rowcount > 0

    # ── saved roles (재입장 복구) ──
    async def save_roles(self, guild_id: int, user_id: int, role_ids: list[int]):
        await self.conn.execute(
            "INSERT OR REPLACE INTO saved_roles (guild_id, user_id, role_ids, saved_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, json.dumps(role_ids), int(time.time())))
        await self.conn.commit()

    async def get_saved_roles(self, guild_id: int, user_id: int) -> list[int]:
        async with self.conn.execute(
            "SELECT role_ids FROM saved_roles WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)) as cur:
            row = await cur.fetchone()
        return json.loads(row["role_ids"]) if row else []

    async def delete_saved_roles(self, guild_id: int, user_id: int):
        await self.conn.execute("DELETE FROM saved_roles WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await self.conn.commit()

    # ── 미인증 알림 기록 ──
    async def get_unv_warns(self, guild_id: int) -> dict[int, int]:
        async with self.conn.execute(
            "SELECT user_id, warned_at FROM unv_warns WHERE guild_id = ?", (guild_id,)) as cur:
            return {r["user_id"]: r["warned_at"] for r in await cur.fetchall()}

    async def set_unv_warn(self, guild_id: int, user_id: int, ts: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO unv_warns (guild_id, user_id, warned_at) VALUES (?, ?, ?)",
            (guild_id, user_id, ts))
        await self.conn.commit()

    async def delete_unv_warn(self, guild_id: int, user_id: int):
        await self.conn.execute("DELETE FROM unv_warns WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await self.conn.commit()

    async def clear_unv_warns(self, guild_id: int):
        await self.conn.execute("DELETE FROM unv_warns WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()

    # ── 필터 차단 기록 ──
    async def add_filter_log(self, guild_id: int, user_id: int, content: str, reason: str):
        await self.conn.execute(
            "INSERT INTO filter_logs (guild_id, user_id, content, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, content, reason, int(time.time())))
        await self.conn.commit()

    async def count_filter_logs(self, guild_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS c FROM filter_logs WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)) as cur:
            return (await cur.fetchone())["c"]