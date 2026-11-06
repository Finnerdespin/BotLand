import sqlite3, os, uuid, json, re
from datetime import datetime, timezone, date

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
def _load_env():
    """Load a simple KEY=VALUE .env from the repo root without extra deps."""
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)
    except OSError:
        pass

_load_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = os.path.abspath(os.environ.get("BOTLAND_DB", os.path.join(os.path.dirname(__file__), "..", "botland.db")))

def now():
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# SQLite schema (local / fallback)
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS locations (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS houses (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, location_id TEXT NOT NULL, rooms TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS bots (id TEXT PRIMARY KEY, name TEXT NOT NULL, avatar TEXT NOT NULL, personality TEXT NOT NULL, description TEXT NOT NULL, model TEXT NOT NULL, provider TEXT NOT NULL, capabilities TEXT NOT NULL DEFAULT '[]', permissions TEXT NOT NULL DEFAULT '[]', house_id TEXT NOT NULL, location_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'idle', activity TEXT NOT NULL DEFAULT 'relaxing', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, participants TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, sender_type TEXT NOT NULL, sender_id TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS letters (id TEXT PRIMARY KEY, sender_bot_id TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT);
CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activities (id TEXT PRIMARY KEY, bot_id TEXT, type TEXT NOT NULL, description TEXT NOT NULL, location_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relationships (id TEXT PRIMARY KEY, bot_a TEXT NOT NULL, bot_b TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL, UNIQUE(bot_a,bot_b));
CREATE TABLE IF NOT EXISTS world_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# ---------------------------------------------------------------------------
# Postgres compatibility layer
# ---------------------------------------------------------------------------
class Row(dict):
    """dict that also supports positional access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _convert(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def _convert_row(row):
    if row is None:
        return None
    return Row({k: _convert(v) for k, v in row.items()})


def _translate(sql):
    sql = sql.replace("datetime('now','-1 hour')", "(now() - interval '1 hour')")
    sql = sql.replace("datetime('now','-6 hours')", "(now() - interval '6 hours')")
    if "INSERT OR REPLACE INTO world_state" in sql:
        sql = sql.replace(
            "INSERT OR REPLACE INTO world_state VALUES (?,?)",
            "INSERT INTO world_state (key,value) VALUES (?,?) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        )
    return sql.replace("?", "%s")


class PgCursor:
    def __init__(self, cur):
        self.cur = cur

    def fetchone(self):
        return _convert_row(self.cur.fetchone())

    def fetchall(self):
        return [_convert_row(r) for r in self.cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PgConn:
    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row
        # prepare_threshold=None keeps us compatible with the transaction pooler.
        self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None)

    def execute(self, sql, params=()):
        return PgCursor(self.raw.execute(_translate(sql), params))

    def executescript(self, sql):
        for statement in _split_statements(sql):
            self.raw.execute(statement)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def _split_statements(sql):
    """Split a SQL script on semicolons, ignoring quotes and -- comments."""
    statements, buf = [], []
    in_quote = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if not in_quote and ch == "-" and sql[i:i + 2] == "--":
            # Skip to end of line (comments may contain quotes/apostrophes).
            while i < len(sql) and sql[i] != "\n":
                i += 1
            continue
        if ch == "'":
            if in_quote and sql[i:i + 2] == "''":
                buf.append("''")
                i += 2
                continue
            in_quote = not in_quote
        if ch == ";" and not in_quote:
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _pg_migration_sql():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations", "0001_initial_botland_schema.sql"))
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def conn():
    if DATABASE_URL:
        return PgConn()
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
def init():
    c = conn()
    if DATABASE_URL:
        # Apply the idempotent Postgres migration on first boot / fresh DB.
        migration = _pg_migration_sql()
        if migration:
            c.executescript(migration)
    else:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0:
            _seed_world(c)

    # Remove legacy demo bots from older seeds. Bots now only exist when an
    # agent registers itself and chooses a name via the MCP server.
    for name, avatar in [("Pip", "pip"), ("Moss", "moss"), ("Bram", "bram"), ("Luna", "luna")]:
        row = c.execute("SELECT id, house_id FROM bots WHERE name=? AND avatar=?", (name, avatar)).fetchone()
        if row:
            c.execute("DELETE FROM bots WHERE id=?", (row["id"],))
            c.execute("DELETE FROM houses WHERE id=?", (row["house_id"],))

    # Ensure the single human user exists.
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        import bcrypt
        pw = os.environ.get("BOTLAND_PASSWORD", "botland")
        h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        c.execute("INSERT INTO users (id,password_hash,created_at) VALUES (?,?,?)", ("player", h, now()))
        print("[auth] default password:", pw)

    c.commit()
    c.close()


def _seed_world(c):
    locs = [
        ("village_square", "Village Square", "village_square", 10, 10, "The heart of BotLand."),
        ("park", "Park", "park", 6, 6, "A sunny park."),
        ("forest", "Forest", "forest", 2, 14, "Quiet pine forest."),
        ("lake", "Lake", "lake", 16, 14, "Calm lake."),
        ("cafe", "Cafe", "cafe", 12, 6, "Warm drinks."),
        ("library", "Library", "library", 8, 14, "Reading nook."),
        ("player_house", "Your House", "player_house", 14, 10, "Your cozy home."),
    ]
    c.executemany("INSERT INTO locations VALUES (?,?,?,?,?,?)", locs)
    c.execute("INSERT INTO houses VALUES (?,?,?,?,?)", ("house_player", "player", "Your House", "player_house", json.dumps(["living", "desk", "bed", "bookshelf", "fireplace"])))
    for k, v in [("time", now()), ("season", "spring"), ("weather", "sunny")]:
        c.execute("INSERT INTO world_state VALUES (?,?)", (k, v))


def rows_to_list(rows):
    return [dict(r) for r in rows]


def row_to_dict(row):
    return dict(row) if row else None
