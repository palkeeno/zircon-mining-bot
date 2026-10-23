"""Personal balances, mining claims and audit entries share one SQLite transaction."""
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timedelta

import config.config as config
from domain.mining_period import JST, scheduled_period

MAX_AMOUNT = 2**63 - 1


def period_start(now=None):
    return scheduled_period(now, config.get_announce_hour(), config.get_announce_minute())


@contextmanager
def transaction():
    connection = sqlite3.connect(config.DB_USERS, timeout=15)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    with transaction() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS USERS (
            id INTEGER PRIMARY KEY AUTOINCREMENT, userid INTEGER,
            curr_total INTEGER, lt_total INTEGER, m_cnt INTEGER, ex_cnt INTEGER,
            updated_at TEXT)""")
        # Fail loudly on corrupt legacy duplicate accounts instead of discarding money.
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS wallet_user ON USERS(userid)")
        db.execute("""CREATE TABLE IF NOT EXISTS CLAIMS (
            userid INTEGER PRIMARY KEY, period TEXT NOT NULL, count INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS LEDGER (
            request_id TEXT PRIMARY KEY, actor INTEGER, source INTEGER, target INTEGER,
            amount INTEGER, kind TEXT, created_at TEXT)""")
        db.execute("CREATE TABLE IF NOT EXISTS WALLET_META (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("""CREATE TABLE IF NOT EXISTS RESET_LOG (
            request_id TEXT PRIMARY KEY, actor INTEGER NOT NULL,
            period TEXT NOT NULL, created_at TEXT NOT NULL)""")


def ensure_user(db, uid):
    if uid <= 4:
        raise ValueError("Discordユーザーを指定してください。")
    db.execute("""INSERT OR IGNORE INTO USERS
        (userid,curr_total,lt_total,m_cnt,ex_cnt,updated_at) VALUES (?,0,0,0,0,?)""",
        (uid, datetime.now(JST).isoformat()))


def positive(amount):
    if type(amount) is not int or not 1 <= amount <= MAX_AMOUNT:
        raise ValueError("数量は1以上の整数で指定してください。")


def balance(uid):
    with closing(sqlite3.connect(config.DB_USERS)) as db:
        row = db.execute("SELECT curr_total,m_cnt,ex_cnt FROM USERS WHERE userid=?", (uid,)).fetchone()
        return row or (0, 0, 0)


def audit(db, request_id, actor, source, target, amount, kind):
    db.execute("INSERT INTO LEDGER VALUES (?,?,?,?,?,?,?)",
               (str(request_id), actor, source, target, amount, kind, datetime.now(JST).isoformat()))


def change(amount, *, actor, request_id, source=None, target=None, kind="transfer"):
    positive(amount)
    if source is None and target is None or source == target:
        raise ValueError("異なる転送元・転送先を指定してください。")
    with transaction() as db:
        if db.execute("SELECT 1 FROM LEDGER WHERE request_id=?", (str(request_id),)).fetchone():
            raise ValueError("この操作は処理済みです。")
        for uid in (source, target):
            if uid is not None:
                ensure_user(db, uid)
        if source is not None:
            updated = db.execute("UPDATE USERS SET curr_total=curr_total-? WHERE userid=? AND curr_total>=?",
                                 (amount, source, amount))
            if not updated.rowcount:
                raise ValueError("ジルコンの残高が不足しています。")
        if target is not None:
            updated = db.execute("UPDATE USERS SET curr_total=curr_total+? WHERE userid=? AND curr_total<=?",
                                 (amount, target, MAX_AMOUNT - amount))
            if not updated.rowcount:
                raise ValueError("転送先の残高が上限を超えます。")
        audit(db, request_id, actor, source, target, amount, kind)


def claim(uid, amount, excellent, request_id, now=None):
    positive(amount)
    limit = int(config.settings.get("mining_limit", 1))
    with transaction() as db:
        period = current_period(now, db=db)
        ensure_user(db, uid)
        row = db.execute("SELECT period,count FROM CLAIMS WHERE userid=?", (uid,)).fetchone()
        # Never move backwards after schedule changes or clock corrections.
        count = row[1] if row and row[0] >= period else 0
        if count >= limit:
            raise ValueError("この期間の採掘回数を使い切りました。次のリセットをお待ちください。")
        effective_period = max(period, row[0]) if row else period
        db.execute("""INSERT INTO CLAIMS VALUES (?,?,?)
            ON CONFLICT(userid) DO UPDATE SET period=excluded.period,count=excluded.count""",
                   (uid, effective_period, count + 1))
        updated = db.execute("""UPDATE USERS SET curr_total=curr_total+?,lt_total=lt_total+?,
            m_cnt=m_cnt+1,ex_cnt=ex_cnt+?,updated_at=? WHERE userid=?
            AND curr_total<=? AND lt_total<=?""",
            (amount, amount, int(excellent), datetime.now(JST).isoformat(), uid,
             MAX_AMOUNT - amount, MAX_AMOUNT - amount))
        if not updated.rowcount:
            raise ValueError("残高が上限を超えます。")
        audit(db, request_id, uid, None, uid, amount, "mine")
        return db.execute("SELECT curr_total FROM USERS WHERE userid=?", (uid,)).fetchone()[0]


def current_period(now=None, *, db=None):
    if db is None:
        with closing(sqlite3.connect(config.DB_USERS)) as connection:
            return current_period(now, db=connection)
    manual = db.execute("SELECT value FROM WALLET_META WHERE key='manual_period'").fetchone()
    return max(period_start(now), manual[0]) if manual else period_start(now)


def reset_claims(*, actor, request_id, now=None):
    """Start a fresh claim period without changing balances or mining records."""
    now = (now or datetime.now(JST)).astimezone(JST)
    with transaction() as db:
        if db.execute("SELECT 1 FROM RESET_LOG WHERE request_id=?", (str(request_id),)).fetchone():
            raise ValueError("このリセットは処理済みです。")
        previous = db.execute("SELECT value FROM WALLET_META WHERE key='manual_period'").fetchone()
        boundary = max(now, datetime.fromisoformat(period_start(now)))
        if previous:
            boundary = max(boundary, datetime.fromisoformat(previous[0]) + timedelta(microseconds=1))
        period = boundary.isoformat()
        db.execute("DELETE FROM CLAIMS")
        db.execute("""INSERT INTO WALLET_META VALUES ('manual_period',?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (period,))
        db.execute("INSERT INTO RESET_LOG VALUES (?,?,?,?)",
                   (str(request_id), actor, period, now.isoformat()))
        return period


def ranking(kind):
    order = {"balance": "curr_total", "excellent": "ex_cnt"}[kind]
    with closing(sqlite3.connect(config.DB_USERS)) as db:
        return db.execute(f"""SELECT userid,curr_total,ex_cnt,m_cnt FROM USERS
            WHERE userid>4 ORDER BY {order} DESC,userid ASC""").fetchall()
