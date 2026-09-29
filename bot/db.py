import sqlite3
import os
import zoneinfo
from datetime import datetime

_TZ = zoneinfo.ZoneInfo("Europe/Helsinki")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "trades.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")   # allows concurrent reads during writes
    conn.execute("PRAGMA synchronous=NORMAL") # safe with WAL, faster than FULL
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS balance_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            balance     REAL    NOT NULL,
            mode        TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            pair        TEXT    NOT NULL,
            side        TEXT    NOT NULL,
            price       REAL    NOT NULL,
            amount      REAL    NOT NULL,
            value_eur   REAL    NOT NULL,
            fee         REAL    NOT NULL,
            mode        TEXT    NOT NULL,
            pnl         REAL,
            notes       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            pair        TEXT    NOT NULL,
            interval    TEXT    NOT NULL,
            open_time   INTEGER NOT NULL,
            open        REAL    NOT NULL,
            high        REAL    NOT NULL,
            low         REAL    NOT NULL,
            close       REAL    NOT NULL,
            volume      REAL    NOT NULL,
            PRIMARY KEY (pair, interval, open_time)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles (pair, interval, open_time)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS archived_shadow_snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            db_mode          TEXT    NOT NULL,
            archive_reason   TEXT    NOT NULL,
            archived_at      TEXT    NOT NULL,
            started_at       TEXT,
            pairs            TEXT,
            overrides        TEXT    NOT NULL,
            starting_balance REAL    NOT NULL,
            final_balance    REAL    NOT NULL,
            total_trades     INTEGER NOT NULL,
            total_pnl        REAL    NOT NULL,
            total_fees       REAL    NOT NULL,
            first_trade_at   TEXT,
            last_trade_at    TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS archived_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL REFERENCES archived_shadow_snapshots(id),
            orig_id     INTEGER,
            timestamp   TEXT    NOT NULL,
            pair        TEXT    NOT NULL,
            side        TEXT    NOT NULL,
            price       REAL    NOT NULL,
            amount      REAL    NOT NULL,
            value_eur   REAL    NOT NULL,
            fee         REAL    NOT NULL,
            pnl         REAL,
            notes       TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_arch_trades_snap ON archived_trades (snapshot_id)")
    conn.commit()
    conn.close()


def log_trade(pair, side, price, amount, value_eur, fee, mode, pnl=None, notes=None):
    from bot import tax as _tax
    ts = datetime.now(tz=_TZ).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        INSERT INTO trades (timestamp, pair, side, price, amount, value_eur, fee, mode, pnl, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ts, pair, side, price, amount, value_eur, fee, mode, pnl, notes))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()

    if mode == "live":
        _tax.init_schema()
        asset = _tax._asset(pair)
        fee_eur = _tax._fee_to_eur(side, fee, price, amount)
        tax_conn = sqlite3.connect(DB_PATH)
        if side == "BUY":
            _tax._add_lot(tax_conn, trade_id, asset, pair, ts, amount, value_eur + fee_eur)
        elif side == "SELL":
            _tax._dispose_fifo(tax_conn, trade_id, asset, pair, ts, amount, value_eur, fee_eur)
        tax_conn.commit()
        tax_conn.close()


def get_hold_times(mode: str) -> dict:
    """Returns {sell_trade_id: hold_hours}.

    Tracks the first non-DCA BUY that opened each position. Subsequent
    non-DCA BUYs (manual adds) while a position is already open are ignored
    so they don't corrupt the hold time of the next independent position.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, timestamp, pair, side, notes FROM trades WHERE mode=? ORDER BY timestamp",
        (mode,)
    ).fetchall()
    conn.close()

    from datetime import datetime as _dt
    entry_time: dict = {}  # pair → open timestamp
    result: dict = {}
    for tid, ts, pair, side, notes in rows:
        if side == 'BUY' and 'dca' not in (notes or '').lower():
            if pair not in entry_time:
                entry_time[pair] = ts
        elif side == 'SELL' and pair in entry_time:
            try:
                b = _dt.fromisoformat(entry_time[pair])
                s = _dt.fromisoformat(ts)
                result[tid] = round((s - b).total_seconds() / 3600, 1)
            except Exception:
                pass
            del entry_time[pair]
    return result


def get_trades(limit=50, mode: str = None, offset: int = 0):
    conn = sqlite3.connect(DB_PATH)
    if mode:
        rows = conn.execute(
            "SELECT * FROM trades WHERE mode = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (mode, limit, offset)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    conn.close()
    return rows


def get_trade_count(mode: str = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    if mode:
        row = conn.execute("SELECT COUNT(*) FROM trades WHERE mode = ?", (mode,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM trades").fetchone()
    conn.close()
    return row[0] if row else 0


def clear_shadow_trades(mode: str):
    """Delete all trades and balance history for a shadow mode (used on config change)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM trades WHERE mode = ?", (mode,))
    conn.execute("DELETE FROM balance_history WHERE mode = ?", (mode,))
    conn.commit()
    conn.close()


def log_balance(balance: float, mode: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO balance_history (timestamp, balance, mode) VALUES (?, ?, ?)",
        (datetime.now(tz=_TZ).strftime("%Y-%m-%d %H:%M:%S"), balance, mode)
    )
    conn.commit()
    conn.close()


def get_starting_balance(mode: str) -> float | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT balance FROM balance_history WHERE mode=? ORDER BY timestamp ASC LIMIT 1", (mode,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_balance_history(mode: str, days: float = 30):
    conn = sqlite3.connect(DB_PATH)
    if days > 0:
        hours = days * 24
        modifier = f'-{hours} hours'
        rows = conn.execute("""
            SELECT timestamp, balance FROM balance_history
            WHERE mode = ? AND timestamp >= datetime('now', ?)
            ORDER BY timestamp ASC
        """, (mode, modifier)).fetchall()
    else:
        rows = conn.execute("""
            SELECT timestamp, balance FROM balance_history
            WHERE mode = ? ORDER BY timestamp ASC
        """, (mode,)).fetchall()
    conn.close()
    return rows


def get_trade_stats(mode: str):
    conn = sqlite3.connect(DB_PATH)
    sell_rows = conn.execute("""
        SELECT pnl, timestamp, pair
        FROM trades WHERE mode = ? AND side = 'SELL' AND pnl IS NOT NULL
    """, (mode,)).fetchall()
    buy_rows_raw = conn.execute("""
        SELECT timestamp, pair, notes
        FROM trades WHERE mode = ? AND side = 'BUY'
    """, (mode,)).fetchall()
    conn.close()

    sells = sell_rows
    if not sells:
        return None

    pnls       = [s[0] for s in sells]
    wins       = [p for p in pnls if p > 0]
    losses     = [p for p in pnls if p <= 0]
    best       = max(pnls)
    worst      = min(pnls)
    avg_pnl    = sum(pnls) / len(pnls)
    win_rate   = len(wins) / len(pnls) * 100

    # avg hold time: match BUY→SELL pairs per pair
    hold_times   = []
    buys_by_pair = {}
    for ts, pair, notes in buy_rows_raw:
        if 'dca' not in (notes or '').lower():
            buys_by_pair.setdefault(pair, []).append(ts)
    for _, ts, pair in sells:
        if buys_by_pair.get(pair):
            buy_ts = buys_by_pair[pair].pop(0)
            try:
                from datetime import datetime as dt
                b = dt.fromisoformat(buy_ts)
                s = dt.fromisoformat(ts)
                hold_times.append((s - b).total_seconds() / 3600)
            except Exception:
                pass

    avg_hold_h = sum(hold_times) / len(hold_times) if hold_times else None

    return {
        "total":      len(pnls),
        "wins":       len(wins),
        "losses":     len(losses),
        "win_rate":   round(win_rate, 1),
        "avg_pnl":    round(avg_pnl, 2),
        "best":       round(best, 2),
        "worst":      round(worst, 2),
        "avg_hold_h": round(avg_hold_h, 1) if avg_hold_h is not None else None,
    }


def get_tax_summary(mode="live"):
    """Realized P&L grouped by year for tax reporting."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT
            strftime('%Y', timestamp)                           AS year,
            SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END)        AS gains,
            SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END)   AS losses,
            SUM(pnl)                                            AS net_pnl
        FROM trades
        WHERE pnl IS NOT NULL AND mode = ?
        GROUP BY year
        ORDER BY year DESC
    """, (mode,)).fetchall()
    conn.close()
    return rows


def archive_shadow(name: str, db_mode: str, reason: str, state_data: dict, overrides: dict):
    """Archive a shadow's trades + state snapshot, then wipe from live tables."""
    import json as _json
    conn = sqlite3.connect(DB_PATH)
    try:
        archived_at = datetime.now(tz=_TZ).isoformat()
        date_row = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM trades WHERE mode = ?", (db_mode,)
        ).fetchone()
        first_trade_at = date_row[0] if date_row else None
        last_trade_at  = date_row[1] if date_row else None
        pairs = overrides.get("pairs") or state_data.get("overrides", {}).get("pairs")
        cur = conn.execute("""
            INSERT INTO archived_shadow_snapshots
                (name, db_mode, archive_reason, archived_at, started_at, pairs, overrides,
                 starting_balance, final_balance, total_trades, total_pnl, total_fees,
                 first_trade_at, last_trade_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, db_mode, reason, archived_at,
            state_data.get("started_at"),
            _json.dumps(pairs) if pairs else None,
            _json.dumps(overrides),
            float(state_data.get("starting_balance", 0.0)),
            float(state_data.get("balance", 0.0)),
            int(state_data.get("total_trades", 0)),
            float(state_data.get("total_pnl", 0.0)),
            float(state_data.get("total_fees", 0.0)),
            first_trade_at, last_trade_at,
        ))
        snapshot_id = cur.lastrowid
        conn.execute("""
            INSERT INTO archived_trades
                (snapshot_id, orig_id, timestamp, pair, side, price, amount, value_eur, fee, pnl, notes)
            SELECT ?, id, timestamp, pair, side, price, amount, value_eur, fee, pnl, notes
            FROM trades WHERE mode = ?
        """, (snapshot_id, db_mode))
        conn.execute("DELETE FROM trades WHERE mode = ?", (db_mode,))
        conn.execute("DELETE FROM balance_history WHERE mode = ?", (db_mode,))
        conn.commit()
        import logging
        logging.getLogger("cryptobot").info(
            f"[ARCHIVE] {name}: {state_data.get('total_trades', 0)} trades archived (reason={reason})"
        )
    except Exception as e:
        conn.rollback()
        import logging
        logging.getLogger("cryptobot").error(f"[ARCHIVE] Failed to archive {name}: {e}")
    finally:
        conn.close()


def get_archived_snapshots() -> list:
    import json as _json
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM archived_shadow_snapshots ORDER BY archived_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["pairs"]     = _json.loads(d["pairs"])     if d["pairs"]     else []
        d["overrides"] = _json.loads(d["overrides"]) if d["overrides"] else {}
        result.append(d)
    return result


def get_archived_snapshot(snapshot_id: int):
    import json as _json
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM archived_shadow_snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["pairs"]     = _json.loads(d["pairs"])     if d["pairs"]     else []
    d["overrides"] = _json.loads(d["overrides"]) if d["overrides"] else {}
    return d


def get_archived_trades(snapshot_id: int, limit: int = 50, offset: int = 0) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM archived_trades WHERE snapshot_id = ?
        ORDER BY timestamp ASC LIMIT ? OFFSET ?
    """, (snapshot_id, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_archived_trade_count(snapshot_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*) FROM archived_trades WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0
