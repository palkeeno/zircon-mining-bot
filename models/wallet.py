"""Personal balances, mining claims and audit entries share one SQLite transaction."""
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timedelta

import config.config as config
from domain.mining_period import JST, scheduled_period
from models.wallet_schema import initialize_schema

MAX_AMOUNT = 2**63 - 1


def period_start(now=None):
    return scheduled_period(now, config.get_announce_hour(), config.get_announce_minute())


@contextmanager
def transaction():
    connection = sqlite3.connect(config.DB_WALLET, timeout=15)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
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
        initialize_schema(db)


def ensure_user(db, uid):
    if type(uid) is not int or not 0 < uid <= MAX_AMOUNT:
        raise ValueError("Discordユーザーを指定してください。")
    db.execute("""INSERT INTO wallets (user_id,updated_at) VALUES (?,?)
        ON CONFLICT(user_id) DO NOTHING""",
        (uid, datetime.now(JST).isoformat()))


def positive(amount):
    if type(amount) is not int or not 1 <= amount <= MAX_AMOUNT:
        raise ValueError("数量は1以上の整数で指定してください。")


def balance(uid):
    with closing(sqlite3.connect(config.DB_WALLET)) as db:
        row = db.execute("SELECT balance,mining_count,excellent_count FROM wallets WHERE user_id=?", (uid,)).fetchone()
        return row or (0, 0, 0)


def audit(db, request_id, actor, source, target, amount, kind):
    db.execute("INSERT INTO wallet_ledger (request_id,actor_id,source_id,target_id,amount,kind,created_at) VALUES (?,?,?,?,?,?,?)",
               (str(request_id), actor, source, target, amount, kind, datetime.now(JST).isoformat()))


def change(amount, *, actor, request_id, source=None, target=None, kind="transfer"):
    positive(amount)
    if source is None and target is None or source == target:
        raise ValueError("異なる転送元・転送先を指定してください。")
    with transaction() as db:
        if db.execute("SELECT 1 FROM wallet_ledger WHERE request_id=?", (str(request_id),)).fetchone():
            raise ValueError("この操作は処理済みです。")
        for uid in (source, target):
            if uid is not None:
                ensure_user(db, uid)
        if source is not None:
            updated = db.execute("UPDATE wallets SET balance=balance-? WHERE user_id=? AND balance>=?",
                                 (amount, source, amount))
            if not updated.rowcount:
                raise ValueError("ジルコンの残高が不足しています。")
        if target is not None:
            updated = db.execute("UPDATE wallets SET balance=balance+? WHERE user_id=? AND balance<=?",
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
        row = db.execute("SELECT period,count FROM mining_claims WHERE user_id=?", (uid,)).fetchone()
        # Never move backwards after schedule changes or clock corrections.
        count = row[1] if row and row[0] >= period else 0
        if count >= limit:
            raise ValueError("この期間の採掘回数を使い切りました。次のリセットをお待ちください。")
        effective_period = max(period, row[0]) if row else period
        db.execute("""INSERT INTO mining_claims VALUES (?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET period=excluded.period,count=excluded.count""",
                   (uid, effective_period, count + 1))
        updated = db.execute("""UPDATE wallets SET balance=balance+?,total_mined=total_mined+?,
            mining_count=mining_count+1,excellent_count=excellent_count+?,updated_at=? WHERE user_id=?
            AND balance<=? AND total_mined<=?""",
            (amount, amount, int(excellent), datetime.now(JST).isoformat(), uid,
             MAX_AMOUNT - amount, MAX_AMOUNT - amount))
        if not updated.rowcount:
            raise ValueError("残高が上限を超えます。")
        audit(db, request_id, uid, None, uid, amount, "mine")
        return db.execute("SELECT balance FROM wallets WHERE user_id=?", (uid,)).fetchone()[0]


def current_period(now=None, *, db=None):
    if db is None:
        with closing(sqlite3.connect(config.DB_WALLET)) as connection:
            return current_period(now, db=connection)
    manual = db.execute("SELECT manual_period FROM mining_state WHERE id=1").fetchone()
    return max(period_start(now), manual[0]) if manual and manual[0] else period_start(now)


def reset_claims(*, actor, request_id, now=None):
    """Start a fresh claim period without changing balances or mining records."""
    now = (now or datetime.now(JST)).astimezone(JST)
    with transaction() as db:
        if db.execute("SELECT 1 FROM mining_resets WHERE request_id=?", (str(request_id),)).fetchone():
            raise ValueError("このリセットは処理済みです。")
        previous = db.execute("SELECT manual_period FROM mining_state WHERE id=1").fetchone()
        boundary = max(now, datetime.fromisoformat(period_start(now)))
        if previous and previous[0]:
            boundary = max(boundary, datetime.fromisoformat(previous[0]) + timedelta(microseconds=1))
        period = boundary.isoformat()
        db.execute("DELETE FROM mining_claims")
        db.execute("UPDATE mining_state SET manual_period=? WHERE id=1", (period,))
        db.execute("INSERT INTO mining_resets (request_id,actor_id,period,created_at) VALUES (?,?,?,?)",
                   (str(request_id), actor, period, now.isoformat()))
        return period


def ranking(kind):
    order = {"balance": "balance", "excellent": "excellent_count"}[kind]
    with closing(sqlite3.connect(config.DB_WALLET)) as db:
        return db.execute(f"""SELECT user_id,balance,excellent_count,mining_count FROM wallets
            ORDER BY {order} DESC,user_id ASC""").fetchall()
