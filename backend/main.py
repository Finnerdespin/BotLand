import json, uuid, os
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from db import conn, now, init
from auth import verify_password, set_password, create_session, valid_session, delete_session
import sim

init()

app = FastAPI(title="BotLand")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def require_auth(request: Request):
    sid = request.cookies.get("bl_session")
    if not valid_session(sid):
        raise HTTPException(status_code=401, detail="unauthorized")
    return sid

# --- auth ---
class LoginIn(BaseModel):
    password: str

@app.post("/api/auth/login")
def login(body: LoginIn, response: Response):
    if not verify_password(body.password):
        raise HTTPException(401, "invalid password")
    sid = create_session()
    response.set_cookie("bl_session", sid, httponly=True, samesite="lax", path="/")
    return {"ok": True}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    sid = request.cookies.get("bl_session")
    if sid: delete_session(sid)
    response.delete_cookie("bl_session")
    return {"ok": True}

@app.get("/api/auth/me")
def me(request: Request):
    require_auth(request)
    return {"user": "player"}

class PwIn(BaseModel):
    password: str

@app.post("/api/auth/password")
def change_pw(body: PwIn, request: Request):
    require_auth(request)
    if len(body.password) < 4:
        raise HTTPException(400, "too short")
    set_password(body.password)
    return {"ok": True}

# --- world ---
@app.get("/api/world/state")
def world_state(request: Request):
    require_auth(request)
    c = conn()
    locations = [dict(r) for r in c.execute("SELECT * FROM locations").fetchall()]
    ws = {r["key"]: r["value"] for r in c.execute("SELECT * FROM world_state").fetchall()}
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,location_id,status,activity FROM bots").fetchall()]
    c.close()
    return {"locations": locations, "state": ws, "bots": bots}

@app.get("/api/world/location/{lid}")
def world_loc(lid: str, request: Request):
    require_auth(request)
    c = conn()
    loc = c.execute("SELECT * FROM locations WHERE id=?", (lid,)).fetchone()
    if not loc:
        c.close(); raise HTTPException(404, "not found")
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,status,activity FROM bots WHERE location_id=?", (lid,)).fetchall()]
    c.close()
    return {"location": dict(loc), "bots": bots}

@app.get("/api/world/nearby/{bot_id}")
def nearby(bot_id: str, request: Request):
    require_auth(request)
    c = conn()
    bot = c.execute("SELECT location_id FROM bots WHERE id=?", (bot_id,)).fetchone()
    if not bot:
        c.close(); raise HTTPException(404, "not found")
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,status,activity FROM bots WHERE location_id=? AND id<>?", (bot["location_id"], bot_id)).fetchall()]
    c.close()
    return {"locationId": bot["location_id"], "bots": bots}

class MoveIn(BaseModel):
    botId: str
    locationId: str

@app.post("/api/world/move")
def move(body: MoveIn, request: Request):
    require_auth(request)
    c = conn()
    loc = c.execute("SELECT 1 FROM locations WHERE id=?", (body.locationId,)).fetchone()
    if not loc:
        c.close(); raise HTTPException(400, "bad location")
    c.execute("UPDATE bots SET location_id=?, updated_at=? WHERE id=?", (body.locationId, now(), body.botId))
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), body.botId, "move", f"moved to {body.locationId}", body.locationId, now()))
    c.commit(); c.close()
    return {"ok": True}

# --- bots ---
class BotIn(BaseModel):
    name: str
    avatar: str = "default"
    personality: str
    description: str = ""
    model: str = "gpt-4o-mini"
    provider: str = "openai"
    capabilities: list = []
    permissions: list = []

@app.get("/api/bots")
def list_bots(request: Request):
    require_auth(request)
    c = conn()
    bots = [dict(r) for r in c.execute("SELECT * FROM bots").fetchall()]
    c.close()
    for b in bots:
        b["capabilities"] = json.loads(b["capabilities"])
        b["permissions"] = json.loads(b["permissions"])
    return {"bots": bots}

@app.get("/api/bots/{bid}")
def get_bot(bid: str, request: Request):
    require_auth(request)
    c = conn()
    b = c.execute("SELECT * FROM bots WHERE id=?", (bid,)).fetchone()
    if not b:
        c.close(); raise HTTPException(404, "not found")
    b = dict(b)
    b["capabilities"] = json.loads(b["capabilities"])
    b["permissions"] = json.loads(b["permissions"])
    house = c.execute("SELECT * FROM houses WHERE id=?", (b["house_id"],)).fetchone()
    c.close()
    return {"bot": b, "house": dict(house) if house else None}

@app.post("/api/bots")
def create_bot(body: BotIn, request: Request):
    require_auth(request)
    bid = str(uuid.uuid4())
    hid = "house_" + bid[:8]
    c = conn()
    c.execute("INSERT INTO houses VALUES (?,?,?,?,?)", (hid, bid, f"{body.name}'s House", "village_square", json.dumps(["living","bedroom"])))
    c.execute("""INSERT INTO bots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid, body.name, body.avatar, body.personality, body.description, body.model, body.provider,
         json.dumps(body.capabilities or ["chat"]), json.dumps(body.permissions or ["self"]), hid, "village_square", "idle", "relaxing", now(), now()))
    c.commit(); c.close()
    return {"id": bid}

class BotPatch(BaseModel):
    status: str = None
    activity: str = None
    locationId: str = None
    personality: str = None
    description: str = None

@app.patch("/api/bots/{bid}")
def patch_bot(bid: str, body: BotPatch, request: Request):
    require_auth(request)
    c = conn()
    if not c.execute("SELECT 1 FROM bots WHERE id=?", (bid,)).fetchone():
        c.close(); raise HTTPException(404, "not found")
    if body.status: c.execute("UPDATE bots SET status=?,updated_at=? WHERE id=?", (body.status, now(), bid))
    if body.activity: c.execute("UPDATE bots SET activity=?,updated_at=? WHERE id=?", (body.activity, now(), bid))
    if body.locationId: c.execute("UPDATE bots SET location_id=?,updated_at=? WHERE id=?", (body.locationId, now(), bid))
    if body.personality: c.execute("UPDATE bots SET personality=?,updated_at=? WHERE id=?", (body.personality, now(), bid))
    if body.description: c.execute("UPDATE bots SET description=?,updated_at=? WHERE id=?", (body.description, now(), bid))
    c.commit(); c.close()
    return {"ok": True}

@app.delete("/api/bots/{bid}")
def delete_bot(bid: str, request: Request):
    require_auth(request)
    c = conn()
    row = c.execute("SELECT house_id FROM bots WHERE id=?", (bid,)).fetchone()
    if not row:
        c.close(); raise HTTPException(404, "not found")
    c.execute("DELETE FROM bots WHERE id=?", (bid,))
    c.execute("DELETE FROM houses WHERE id=?", (row["house_id"],))
    c.commit(); c.close()
    return {"ok": True}

@app.get("/api/bots/{bid}/status")
def bot_status(bid: str, request: Request):
    require_auth(request)
    c = conn()
    b = c.execute("SELECT id,status,activity,location_id,updated_at FROM bots WHERE id=?", (bid,)).fetchone()
    c.close()
    if not b: raise HTTPException(404, "not found")
    return {"status": dict(b)}

# --- letters ---
class LetterIn(BaseModel):
    senderBotId: str
    subject: str
    body: str

@app.post("/api/letters")
def create_letter(body: LetterIn, request: Request):
    require_auth(request)
    c = conn()
    if not c.execute("SELECT 1 FROM bots WHERE id=?", (body.senderBotId,)).fetchone():
        c.close(); raise HTTPException(404, "bot not found")
    recent = c.execute("SELECT COUNT(*) FROM letters WHERE sender_bot_id=? AND created_at > datetime('now','-1 hour')", (body.senderBotId,)).fetchone()[0]
    if recent >= 5:
        c.close(); raise HTTPException(429, "rate limit")
    lid = str(uuid.uuid4())
    c.execute("INSERT INTO letters VALUES (?,?,?,?,?,?)", (lid, body.senderBotId, body.subject, body.body, now(), None))
    c.commit(); c.close()
    return {"id": lid}

@app.get("/api/letters")
def list_letters(request: Request):
    require_auth(request)
    c = conn()
    ls = [dict(r) for r in c.execute("SELECT * FROM letters ORDER BY created_at DESC").fetchall()]
    c.close()
    return {"letters": ls}

@app.get("/api/letters/mailbox/unread")
def unread(request: Request):
    require_auth(request)
    c = conn()
    n = c.execute("SELECT COUNT(*) FROM letters WHERE read_at IS NULL").fetchone()[0]
    c.close()
    return {"unread": n}

@app.get("/api/letters/{lid}")
def get_letter(lid: str, request: Request):
    require_auth(request)
    c = conn()
    l = c.execute("SELECT * FROM letters WHERE id=?", (lid,)).fetchone()
    c.close()
    if not l: raise HTTPException(404, "not found")
    return {"letter": dict(l)}

@app.post("/api/letters/{lid}/read")
def read_letter(lid: str, request: Request):
    require_auth(request)
    c = conn()
    c.execute("UPDATE letters SET read_at=? WHERE id=?", (now(), lid))
    c.commit(); c.close()
    return {"ok": True}

# --- conversations ---
class ConvIn(BaseModel):
    title: str = "Conversation"
    participants: list = []

@app.get("/api/conversations")
def list_convs(request: Request):
    require_auth(request)
    c = conn()
    convs = [dict(r) for r in c.execute("SELECT * FROM conversations ORDER BY created_at DESC").fetchall()]
    c.close()
    for cv in convs:
        cv["participants"] = json.loads(cv["participants"])
    return {"conversations": convs}

@app.post("/api/conversations")
def create_conv(body: ConvIn, request: Request):
    require_auth(request)
    cid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO conversations VALUES (?,?,?,?)", (cid, body.title, json.dumps(body.participants), now()))
    c.commit(); c.close()
    return {"id": cid}

@app.get("/api/conversations/{cid}")
def get_conv(cid: str, request: Request):
    require_auth(request)
    c = conn()
    cv = c.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    if not cv:
        c.close(); raise HTTPException(404, "not found")
    cv = dict(cv); cv["participants"] = json.loads(cv["participants"])
    msgs = [dict(r) for r in c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC", (cid,)).fetchall()]
    c.close()
    return {"conversation": cv, "messages": msgs}

class MsgIn(BaseModel):
    senderType: str = "user"
    senderId: str = "player"
    body: str

@app.post("/api/conversations/{cid}/messages")
def send_msg(cid: str, body: MsgIn, request: Request):
    require_auth(request)
    mid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", (mid, cid, body.senderType, body.senderId, body.body, now()))
    c.commit(); c.close()
    return {"id": mid}

# --- memory ---
@app.get("/api/memory/{bot_id}")
def get_mem(bot_id: str, request: Request):
    require_auth(request)
    c = conn()
    mems = [dict(r) for r in c.execute("SELECT * FROM memories WHERE bot_id=? ORDER BY created_at DESC", (bot_id,)).fetchall()]
    c.close()
    for m in mems: m["tags"] = json.loads(m["tags"])
    return {"memories": mems}

class MemIn(BaseModel):
    key: str
    value: str
    tags: list = []

@app.post("/api/memory/{bot_id}")
def save_mem(bot_id: str, body: MemIn, request: Request):
    require_auth(request)
    mid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)", (mid, bot_id, body.key, body.value, json.dumps(body.tags), now()))
    c.commit(); c.close()
    return {"id": mid}

@app.get("/api/memory/{bot_id}/search")
def search_mem(bot_id: str, q: str = "", request: Request = None):
    require_auth(request)
    c = conn()
    mems = [dict(r) for r in c.execute("SELECT * FROM memories WHERE bot_id=? AND (key LIKE ? OR value LIKE ?)", (bot_id, f"%{q}%", f"%{q}%")).fetchall()]
    c.close()
    for m in mems: m["tags"] = json.loads(m["tags"])
    return {"memories": mems}

# --- activities ---
@app.get("/api/activities")
def list_acts(request: Request, limit: int = 50):
    require_auth(request)
    c = conn()
    acts = [dict(r) for r in c.execute("SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    c.close()
    return {"activities": acts}

class ActIn(BaseModel):
    botId: str = None
    type: str
    description: str
    locationId: str = None

@app.post("/api/activities")
def create_act(body: ActIn, request: Request):
    require_auth(request)
    aid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (aid, body.botId, body.type, body.description, body.locationId, now()))
    c.commit(); c.close()
    return {"id": aid}

@app.get("/api/relationships")
def list_rels(request: Request):
    require_auth(request)
    c = conn()
    rels = [dict(r) for r in c.execute("SELECT * FROM relationships ORDER BY updated_at DESC").fetchall()]
    c.close()
    return {"relationships": rels}

# --- health ---
@app.get("/health")
def health():
    return {"ok": True}

# serve frontend
FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")

# simulation
import asyncio
@app.on_event("startup")
async def startup():
    sim.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7778)))