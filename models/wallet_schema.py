"""Fresh wallet schema. Old databases are deliberately not imported."""
SCHEMA_VERSION = 1

SCHEMA = (
    """CREATE TABLE wallets (
        user_id INTEGER PRIMARY KEY CHECK (user_id > 0),
        balance INTEGER NOT NULL DEFAULT 0 CHECK (typeof(balance)='integer' AND balance>=0),
        total_mined INTEGER NOT NULL DEFAULT 0 CHECK (typeof(total_mined)='integer' AND total_mined>=0),
        mining_count INTEGER NOT NULL DEFAULT 0 CHECK (typeof(mining_count)='integer' AND mining_count>=0),
        excellent_count INTEGER NOT NULL DEFAULT 0 CHECK (
            typeof(excellent_count)='integer' AND excellent_count>=0 AND excellent_count<=mining_count),
        updated_at TEXT NOT NULL)""",
    """CREATE TABLE mining_claims (
        user_id INTEGER PRIMARY KEY REFERENCES wallets(user_id),
        period TEXT NOT NULL,
        count INTEGER NOT NULL CHECK (typeof(count)='integer' AND count>=0))""",
    """CREATE TABLE wallet_ledger (
        request_id TEXT PRIMARY KEY NOT NULL,
        actor_id INTEGER NOT NULL CHECK (actor_id>0),
        source_id INTEGER REFERENCES wallets(user_id),
        target_id INTEGER REFERENCES wallets(user_id),
        amount INTEGER NOT NULL CHECK (typeof(amount)='integer' AND amount>0),
        kind TEXT NOT NULL CHECK (kind IN ('mine','grant','remove','transfer','donate')),
        created_at TEXT NOT NULL,
        CHECK (
            (kind IN ('mine','grant') AND source_id IS NULL AND target_id IS NOT NULL) OR
            (kind='remove' AND source_id IS NOT NULL AND target_id IS NULL) OR
            (kind IN ('transfer','donate') AND source_id IS NOT NULL AND target_id IS NOT NULL
                AND source_id<>target_id)))""",
    """CREATE TABLE mining_state (
        id INTEGER PRIMARY KEY CHECK (id=1), manual_period TEXT)""",
    "INSERT INTO mining_state (id) VALUES (1)",
    """CREATE TABLE mining_resets (
        request_id TEXT PRIMARY KEY NOT NULL,
        actor_id INTEGER NOT NULL CHECK (actor_id>0),
        period TEXT NOT NULL, created_at TEXT NOT NULL)""",
)


def initialize_schema(db):
    """Called inside a transaction; never recreate an existing database."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise RuntimeError(f'未対応のwallet DBバージョンです: {version}')
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
        raise RuntimeError('既存DBは使用できません。DB_WALLETに新規DBのパスを指定してください。')
    for statement in SCHEMA:
        db.execute(statement)
    db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
