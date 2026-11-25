import time
from dataclasses import dataclass

import aiosqlite

DB_PATH = "alerts.db"


@dataclass
class Alert:
    id: int | None
    user_id: int
    chat_id: int
    symbol: str
    threshold: float
    direction: str          # price/volume/funding: above|below; pct: up|down
    triggered: bool = False
    kind: str = "price"     # price | pct | volume | funding
    window_sec: int = 0     # только для pct


_COLUMNS = "id, user_id, chat_id, symbol, threshold, direction, triggered, kind, window_sec"


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in await cursor.fetchall()}


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                symbol TEXT,
                threshold REAL,
                direction TEXT,
                triggered BOOLEAN DEFAULT 0,
                kind TEXT DEFAULT 'price',
                window_sec INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_premium BOOLEAN DEFAULT 0,
                premium_until INTEGER DEFAULT 0
            )
        """)

        # --- миграции старой БД ---
        alert_cols = await _columns(db, "alerts")
        if "kind" not in alert_cols:
            await db.execute("ALTER TABLE alerts ADD COLUMN kind TEXT DEFAULT 'price'")
        if "window_sec" not in alert_cols:
            await db.execute("ALTER TABLE alerts ADD COLUMN window_sec INTEGER DEFAULT 0")
        if "premium_until" not in await _columns(db, "users"):
            await db.execute("ALTER TABLE users ADD COLUMN premium_until INTEGER DEFAULT 0")

        # у подписки продления приходят отдельными платежами, поэтому
        # уникальность — по паре (charge_id, expires_at), а не по одному charge_id
        pay_cols = await _columns(db, "payments")
        if pay_cols and "expires_at" not in pay_cols:
            await db.execute("ALTER TABLE payments RENAME TO payments_legacy")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                charge_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                payload TEXT,
                is_recurring INTEGER DEFAULT 0,
                expires_at INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (charge_id, expires_at)
            )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id)")
        await db.commit()


# ---------- alerts ----------

async def add_alert(alert: Alert) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO alerts (user_id, chat_id, symbol, threshold, direction, "
            "triggered, kind, window_sec) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (alert.user_id, alert.chat_id, alert.symbol, alert.threshold,
             alert.direction, int(alert.triggered), alert.kind, alert.window_sec),
        )
        await db.commit()
        return cursor.lastrowid


async def get_all_alerts() -> list[Alert]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(f"SELECT {_COLUMNS} FROM alerts")
        return [Alert(*row) for row in await cursor.fetchall()]


async def update_triggered(alert_id: int, triggered: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alerts SET triggered = ? WHERE id = ?", (int(triggered), alert_id)
        )
        await db.commit()


async def get_user_alerts(user_id: int) -> list[Alert]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT {_COLUMNS} FROM alerts WHERE user_id = ? ORDER BY id", (user_id,)
        )
        return [Alert(*row) for row in await cursor.fetchall()]


async def count_user_alerts(user_id: int, kind: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if kind is None:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM alerts WHERE user_id = ?", (user_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            )
        row = await cursor.fetchone()
        return row[0]


async def delete_alert(alert_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM alerts WHERE id = ? AND user_id = ?", (alert_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_all_user_alerts(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount


# ---------- premium / payments ----------

async def get_premium_status(user_id: int) -> tuple[bool, int]:
    """(lifetime, premium_until). lifetime — старый разовый премиум (is_premium=1)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_premium, premium_until FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    if not row:
        return False, 0
    return bool(row[0]), int(row[1] or 0)


async def is_user_premium(user_id: int) -> bool:
    lifetime, until = await get_premium_status(user_id)
    return lifetime or until > time.time()


async def get_premium_user_ids() -> set[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE is_premium = 1 OR premium_until > ?",
            (int(time.time()),),
        )
        return {row[0] for row in await cursor.fetchall()}


async def record_subscription_payment(
    user_id: int,
    charge_id: str,
    amount: int,
    payload: str,
    expires_at: int,
    is_recurring: bool,
) -> bool:
    """Записывает платёж и продлевает премиум до expires_at (одной транзакцией).

    Возвращает False, если такой платёж уже был записан (повторная доставка апдейта).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO payments "
            "(user_id, charge_id, amount, payload, is_recurring, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, charge_id, amount, payload, int(is_recurring), expires_at),
        )
        if cursor.rowcount == 0:
            await db.commit()
            return False
        await db.execute(
            "INSERT INTO users (user_id, premium_until) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "premium_until = MAX(COALESCE(users.premium_until, 0), excluded.premium_until)",
            (user_id, expires_at),
        )
        await db.commit()
        return True