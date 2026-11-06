"""Cross-process protection against repeat dialing of the same number."""
from contextlib import closing
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent / "scratch" / "call_guard.sqlite3"

def claim_call(phone: str, cooldown: int = 600) -> bool:
    phone = "+" + "".join(c for c in phone if c.isdigit())
    DB.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(DB, timeout=10)) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS calls (phone TEXT PRIMARY KEY, claimed REAL)")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT claimed FROM calls WHERE phone=?", (phone,)).fetchone()
        now = time.time()
        if row and now - row[0] < cooldown:
            return False
        conn.execute("INSERT OR REPLACE INTO calls VALUES (?, ?)", (phone, now))
        return True
