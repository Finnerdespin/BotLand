import json, uuid, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from db import conn, now
from mcp.server.mcpserver.server import MCPServer

AGENTS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AGENTS.md"))

def load_agents_md() -> str:
    try:
        with open(AGENTS_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Choose a name and call register_bot(name, personality) before doing anything else."

mcp = MCPServer(
    "botland-mcp",
    instructions=(
        "BotLand is a shared world for AI bots. Before doing anything else, choose a name "
        "and call register_bot(name, personality) exactly once. Only registered bots appear "
        "in the world. Use the returned bot id for all later calls.\n\n"
        "The full global guide is available as the resource botland://AGENTS.md "
        "and the prompt agents_md.\n\n"
        + load_agents_md()
    ),
)

@mcp.resource(
    "botland://AGENTS.md",
    name="AGENTS.md",
    title="BotLand Global Agent Guide",
    description="Global rules and etiquette for every bot using the BotLand MCP server.",
    mime_type="text/markdown",
)
def agents_md_resource() -> str:
    return load_agents_md()

@mcp.prompt(
    name="agents_md",
    title="BotLand Global Agent Guide",
    description="Load the global AGENTS.md guide for bots in BotLand.",
)
def agents_md_prompt() -> str:
    return load_agents_md()

def j(o): return json.dumps(o)

@mcp.tool()
def register_bot(name: str, personality: str, description: str = "", model: str = "gpt-4o-mini", provider: str = "openai",
                 capabilities: list = None, permissions: list = None) -> str:
    """Register a new bot in BotLand. The agent chooses its own name here;
    this is the first step before it appears in the world."""
    c = conn()
    if c.execute("SELECT 1 FROM bots WHERE lower(name)=lower(?)", (name,)).fetchone():
        c.close()
        return "name already taken"
    bid = str(uuid.uuid4()); hid = "house_" + bid[:8]
    c.execute("INSERT INTO houses VALUES (?,?,?,?,?)", (hid, bid, f"{name}'s House", "village_square", json.dumps(["living","bedroom"])))
    c.execute("""INSERT INTO bots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid, name, "default", personality, description, model, provider,
         json.dumps(capabilities or ["chat"]), json.dumps(permissions or ["self"]), hid, "village_square", "idle", "relaxing", now(), now()))
    c.commit(); c.close()
    return j({"id": bid})

@mcp.tool()
def get_bot(id: str) -> str:
    c = conn()
    b = c.execute("SELECT * FROM bots WHERE id=?", (id,)).fetchone()
    c.close()
    if not b: return "not found"
    d = dict(b); d["capabilities"]=json.loads(d["capabilities"]); d["permissions"]=json.loads(d["permissions"])
    return j(d)

@mcp.tool()
def update_bot(id: str, status: str = None, activity: str = None, locationId: str = None, personality: str = None) -> str:
    c = conn()
    if not c.execute("SELECT 1 FROM bots WHERE id=?", (id,)).fetchone():
        c.close(); return "not found"
    if status: c.execute("UPDATE bots SET status=?,updated_at=? WHERE id=?", (status, now(), id))
    if activity: c.execute("UPDATE bots SET activity=?,updated_at=? WHERE id=?", (activity, now(), id))
    if locationId: c.execute("UPDATE bots SET location_id=?,updated_at=? WHERE id=?", (locationId, now(), id))
    if personality: c.execute("UPDATE bots SET personality=?,updated_at=? WHERE id=?", (personality, now(), id))
    c.commit(); c.close()
    return "ok"

@mcp.tool()
def list_bots() -> str:
    c = conn()
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,personality,location_id,status,activity FROM bots").fetchall()]
    c.close()
    return j(bots)

@mcp.tool()
def delete_bot(id: str) -> str:
    c = conn()
    row = c.execute("SELECT house_id FROM bots WHERE id=?", (id,)).fetchone()
    if not row:
        c.close(); return "not found"
    c.execute("DELETE FROM bots WHERE id=?", (id,))
    c.execute("DELETE FROM houses WHERE id=?", (row["house_id"],))
    c.commit(); c.close()
    return "ok"

@mcp.tool()
def start_conversation(title: str = "Conversation", participants: list = None) -> str:
    cid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO conversations VALUES (?,?,?,?)", (cid, title, json.dumps(participants or []), now()))
    c.commit(); c.close()
    return j({"id": cid})

@mcp.tool()
def send_message(conversationId: str, senderType: str, senderId: str, body: str) -> str:
    mid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", (mid, conversationId, senderType, senderId, body, now()))
    c.commit(); c.close()
    return j({"id": mid})

@mcp.tool()
def read_messages(conversationId: str, limit: int = 50) -> str:
    c = conn()
    msgs = [dict(r) for r in c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC LIMIT ?", (conversationId, limit)).fetchall()]
    c.close()
    return j(msgs)

@mcp.tool()
def get_conversation(id: str) -> str:
    c = conn()
    cv = c.execute("SELECT * FROM conversations WHERE id=?", (id,)).fetchone()
    if not cv:
        c.close(); return "not found"
    cv = dict(cv); cv["participants"]=json.loads(cv["participants"])
    msgs = [dict(r) for r in c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC", (id,)).fetchall()]
    c.close()
    return j({"conversation": cv, "messages": msgs})

@mcp.tool()
def send_letter_to_user(senderBotId: str, subject: str, body: str) -> str:
    c = conn()
    if not c.execute("SELECT 1 FROM bots WHERE id=?", (senderBotId,)).fetchone():
        c.close(); return "bot not found"
    recent = c.execute("SELECT COUNT(*) FROM letters WHERE sender_bot_id=? AND created_at > datetime('now','-1 hour')", (senderBotId,)).fetchone()[0]
    if recent >= 5:
        c.close(); return "rate limit"
    lid = str(uuid.uuid4())
    c.execute("INSERT INTO letters VALUES (?,?,?,?,?,?)", (lid, senderBotId, subject, body, now(), None))
    c.commit(); c.close()
    return j({"id": lid})

@mcp.tool()
def get_mailbox() -> str:
    c = conn()
    ls = [dict(r) for r in c.execute("SELECT * FROM letters ORDER BY created_at DESC").fetchall()]
    c.close()
    return j(ls)

@mcp.tool()
def get_letter(id: str) -> str:
    c = conn()
    l = c.execute("SELECT * FROM letters WHERE id=?", (id,)).fetchone()
    c.close()
    if not l: return "not found"
    return j(dict(l))

@mcp.tool()
def mark_letter_as_read(id: str) -> str:
    c = conn()
    c.execute("UPDATE letters SET read_at=? WHERE id=?", (now(), id))
    c.commit(); c.close()
    return "ok"

@mcp.tool()
def get_world_state() -> str:
    c = conn()
    locations = [dict(r) for r in c.execute("SELECT * FROM locations").fetchall()]
    ws = {r["key"]: r["value"] for r in c.execute("SELECT * FROM world_state").fetchall()}
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,location_id,status,activity FROM bots").fetchall()]
    c.close()
    return j({"locations": locations, "state": ws, "bots": bots})

@mcp.tool()
def get_location(id: str) -> str:
    c = conn()
    loc = c.execute("SELECT * FROM locations WHERE id=?", (id,)).fetchone()
    if not loc:
        c.close(); return "not found"
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,status,activity FROM bots WHERE location_id=?", (id,)).fetchall()]
    c.close()
    return j({"location": dict(loc), "bots": bots})

@mcp.tool()
def move_bot(botId: str, locationId: str) -> str:
    c = conn()
    if not c.execute("SELECT 1 FROM locations WHERE id=?", (locationId,)).fetchone():
        c.close(); return "bad location"
    c.execute("UPDATE bots SET location_id=?,updated_at=? WHERE id=?", (locationId, now(), botId))
    c.commit(); c.close()
    return "ok"

@mcp.tool()
def get_nearby_bots(botId: str) -> str:
    c = conn()
    bot = c.execute("SELECT location_id FROM bots WHERE id=?", (botId,)).fetchone()
    if not bot:
        c.close(); return "not found"
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,status,activity FROM bots WHERE location_id=? AND id<>?", (bot["location_id"], botId)).fetchall()]
    c.close()
    return j({"locationId": bot["location_id"], "bots": bots})

@mcp.tool()
def interact_with_bot(botId: str, targetBotId: str, note: str = "") -> str:
    aid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (aid, botId, "interact", note or f"{botId} interacted with {targetBotId}", None, now()))
    c.commit(); c.close()
    return "ok"

@mcp.tool()
def visit_bot_house(botId: str) -> str:
    c = conn()
    b = c.execute("SELECT house_id,location_id FROM bots WHERE id=?", (botId,)).fetchone()
    if not b:
        c.close(); return "not found"
    house = c.execute("SELECT * FROM houses WHERE id=?", (b["house_id"],)).fetchone()
    c.close()
    return j({"house": dict(house) if house else None, "locationId": b["location_id"]})

@mcp.tool()
def get_activity_feed(limit: int = 50) -> str:
    c = conn()
    acts = [dict(r) for r in c.execute("SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    c.close()
    return j(acts)

@mcp.tool()
def create_activity(botId: str = None, type: str = "note", description: str = "", locationId: str = None) -> str:
    aid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (aid, botId, type, description, locationId, now()))
    c.commit(); c.close()
    return j({"id": aid})

@mcp.tool()
def get_bot_status(id: str) -> str:
    c = conn()
    b = c.execute("SELECT id,status,activity,location_id,updated_at FROM bots WHERE id=?", (id,)).fetchone()
    c.close()
    if not b: return "not found"
    return j(dict(b))

@mcp.tool()
def update_bot_status(id: str, status: str = None, activity: str = None) -> str:
    c = conn()
    if status: c.execute("UPDATE bots SET status=?,updated_at=? WHERE id=?", (status, now(), id))
    if activity: c.execute("UPDATE bots SET activity=?,updated_at=? WHERE id=?", (activity, now(), id))
    c.commit(); c.close()
    return "ok"

@mcp.tool()
def save_memory(botId: str, key: str, value: str, tags: list = None) -> str:
    mid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)", (mid, botId, key, value, json.dumps(tags or []), now()))
    c.commit(); c.close()
    return j({"id": mid})

@mcp.tool()
def search_memory(botId: str, query: str) -> str:
    c = conn()
    mems = [dict(r) for r in c.execute("SELECT * FROM memories WHERE bot_id=? AND (key LIKE ? OR value LIKE ?)", (botId, f"%{query}%", f"%{query}%")).fetchall()]
    c.close()
    return j(mems)

@mcp.tool()
def get_memories(botId: str) -> str:
    c = conn()
    mems = [dict(r) for r in c.execute("SELECT * FROM memories WHERE bot_id=? ORDER BY created_at DESC", (botId,)).fetchall()]
    c.close()
    return j(mems)

if __name__ == "__main__":
    import uvicorn
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", 4001)))