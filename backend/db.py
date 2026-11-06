import sqlite3, os, uuid, json, hashlib
from datetime import datetime, timezone

DB_PATH = os.environ.get("BOTLAND_DB", os.path.join(os.path.dirname(__file__), "..", "botland.db"))
DB_PATH = os.path.abspath(DB_PATH)

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def now():
    return datetime.now(timezone.utc).isoformat()

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

def init():
    c = conn()
    c.executescript(SCHEMA)
    # seed locations
    if c.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0:
        locs = [
            ("village_square","Village Square","village_square",10,10,"The heart of BotLand."),
            ("park","Park","park",6,6,"A sunny park."),
            ("forest","Forest","forest",2,14,"Quiet pine forest."),
            ("lake","Lake","lake",16,14,"Calm lake."),
            ("cafe","Cafe","cafe",12,6,"Warm drinks."),
            ("library","Library","library",8,14,"Reading nook."),
            ("player_house","Your House","player_house",14,10,"Your cozy home."),
        ]
        c.executemany("INSERT INTO locations VALUES (?,?,?,?,?,?)", locs)
        c.execute("INSERT INTO houses VALUES (?,?,?,?,?)", ("house_player","player","Your House","player_house",json.dumps(["living","desk","bed","bookshelf","fireplace"])))
        for k,v in [("time",now()),("season","spring"),("weather","sunny")]:
            c.execute("INSERT INTO world_state VALUES (?,?)",(k,v))
    # Remove legacy demo bots from older seeds. Bots now only exist when an
    # agent registers itself and chooses a name via the MCP server.
    for name, avatar in [("Pip","pip"),("Moss","moss"),("Bram","bram"),("Luna","luna")]:
        row = c.execute("SELECT id, house_id FROM bots WHERE name=? AND avatar=?", (name, avatar)).fetchone()
        if row:
            c.execute("DELETE FROM bots WHERE id=?", (row["id"],))
            c.execute("DELETE FROM houses WHERE id=?", (row["house_id"],))
    # ensure user
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]==0:
        import bcrypt
        pw = os.environ.get("BOTLAND_PASSWORD","botland")
        h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        c.execute("INSERT INTO users VALUES (?,?,?)",("player",h,now()))
        print("[auth] default password:", pw)
    c.commit()
    c.close()

def rows_to_list(rows):
    return [dict(r) for r in rows]

def row_to_dict(row):
    return dict(row) if row else None