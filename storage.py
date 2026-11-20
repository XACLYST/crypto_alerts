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
    direction: str
    triggered: bool = False


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                symbol TEXT,
                threshold REAL,
                direction TEXT,
                triggered BOOLEAN DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_premium BOOLEAN DEFAULT 0
            )
        """)
        await db.commit()


# ---------- alerts ----------

async def add_alert(alert: Alert) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO alerts (user_id, chat_id, symbol, threshold, direction, triggered) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (alert.user_id, alert.chat_id, alert.symbol, alert.threshold,
             alert.direction, alert.triggered),
        )
        await db.commit()
        return cursor.lastrowid


async def get_alerts_for_symbol(symbol: str) -> list[Alert]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, user_id, chat_id, symbol, threshold, direction, triggered "
            "FROM alerts WHERE symbol = ?",
            (symbol,),
        )
        rows = await cursor.fetchall()
        return [Alert(*row) for row in rows]


async def get_all_symbols() -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT symbol FROM alerts")
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


async def update_triggered(alert_id: int, triggered: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alerts SET triggered = ? WHERE id = ?", (triggered, alert_id)
        )
        await db.commit()


async def get_user_alerts(user_id: int) -> list[Alert]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, user_id, chat_id, symbol, threshold, direction, triggered "
            "FROM alerts WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [Alert(*row) for row in rows]


async def count_user_alerts(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM alerts WHERE user_id = ?", (user_id,)
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
        cursor = await db.execute(
            "DELETE FROM alerts WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        return cursor.rowcount


# ---------- users ----------

async def is_user_premium(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_premium FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return bool(row[0]) if row else False


async def set_user_premium(user_id: int, value: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, is_premium) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET is_premium = excluded.is_premium",
            (user_id, int(value)),
        )
        await db.commit()