import json, uuid, os
from flask import Flask, request, jsonify, make_response, send_from_directory, abort
from db import conn, now, init
from auth import verify_password, set_password, create_session, valid_session, delete_session
import sim

init()
sim.start()

FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app = Flask(__name__, static_folder=FRONTEND, static_url_path="")
app.config["JSON_SORT_KEYS"] = False

def require_auth():
    sid = request.cookies.get("bl_session")
    if not valid_session(sid):
        abort(401)

@app.errorhandler(401)
def unauthorized(e):
    return jsonify(error="unauthorized"), 401

@app.errorhandler(404)
def notfound(e):
    return jsonify(error="not found"), 404

@app.errorhandler(429)
def ratelimit(e):
    return jsonify(error="rate limit"), 429

# --- auth ---
@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    if not verify_password(body.get("password", "")):
        return jsonify(error="invalid password"), 401
    sid = create_session()
    resp = make_response(jsonify(ok=True))
    resp.set_cookie("bl_session", sid, httponly=True, samesite="Lax", path="/")
    return resp

@app.post("/api/auth/logout")
def logout():
    sid = request.cookies.get("bl_session")
    if sid:
        delete_session(sid)
    resp = make_response(jsonify(ok=True))
    resp.delete_cookie("bl_session")
    return resp

@app.get("/api/auth/me")
def me():
    require_auth()
    return jsonify(user="player")

@app.post("/api/auth/password")
def change_pw():
    require_auth()
    body = request.get_json(silent=True) or {}
    if len(body.get("password", "")) < 4:
        return jsonify(error="too short"), 400
    set_password(body["password"])
    return jsonify(ok=True)

# --- world ---
@app.get("/api/world/state")
def world_state():
    require_auth()
    c = conn()
    locations = [dict(r) for r in c.execute("SELECT * FROM locations").fetchall()]
    ws = {r["key"]: r["value"] for r in c.execute("SELECT * FROM world_state").fetchall()}
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,location_id,status,activity FROM bots").fetchall()]
    c.close()
    return jsonify(locations=locations, state=ws, bots=bots)

@app.get("/api/world/location/<lid>")
def world_loc(lid):
    require_auth()
    c = conn()
    loc = c.execute("SELECT * FROM locations WHERE id=?", (lid,)).fetchone()
    if not loc:
        c.close()
        return jsonify(error="not found"), 404
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,status,activity FROM bots WHERE location_id=?", (lid,)).fetchall()]
    c.close()
    return jsonify(location=dict(loc), bots=bots)

@app.get("/api/world/nearby/<bot_id>")
def nearby(bot_id):
    require_auth()
    c = conn()
    bot = c.execute("SELECT location_id FROM bots WHERE id=?", (bot_id,)).fetchone()
    if not bot:
        c.close()
        return jsonify(error="not found"), 404
    bots = [dict(r) for r in c.execute("SELECT id,name,avatar,status,activity FROM bots WHERE location_id=? AND id<>?", (bot["location_id"], bot_id)).fetchall()]
    c.close()
    return jsonify(locationId=bot["location_id"], bots=bots)

@app.post("/api/world/move")
def move():
    require_auth()
    body = request.get_json(silent=True) or {}
    bot_id, loc_id = body.get("botId"), body.get("locationId")
    c = conn()
    if not c.execute("SELECT 1 FROM locations WHERE id=?", (loc_id,)).fetchone():
        c.close()
        return jsonify(error="bad location"), 400
    c.execute("UPDATE bots SET location_id=?, updated_at=? WHERE id=?", (loc_id, now(), bot_id))
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), bot_id, "move", f"moved to {loc_id}", loc_id, now()))
    c.commit()
    c.close()
    return jsonify(ok=True)

# --- bots ---
@app.get("/api/bots")
def list_bots():
    require_auth()
    c = conn()
    bots = [dict(r) for r in c.execute("SELECT * FROM bots").fetchall()]
    c.close()
    for b in bots:
        b["capabilities"] = json.loads(b["capabilities"])
        b["permissions"] = json.loads(b["permissions"])
    return jsonify(bots=bots)

@app.get("/api/bots/<bid>")
def get_bot(bid):
    require_auth()
    c = conn()
    b = c.execute("SELECT * FROM bots WHERE id=?", (bid,)).fetchone()
    if not b:
        c.close()
        return jsonify(error="not found"), 404
    b = dict(b)
    b["capabilities"] = json.loads(b["capabilities"])
    b["permissions"] = json.loads(b["permissions"])
    house = c.execute("SELECT * FROM houses WHERE id=?", (b["house_id"],)).fetchone()
    c.close()
    return jsonify(bot=b, house=dict(house) if house else None)

@app.post("/api/bots")
def create_bot():
    require_auth()
    body = request.get_json(silent=True) or {}
    if not body.get("name") or not body.get("personality"):
        return jsonify(error="missing fields"), 400
    bid = str(uuid.uuid4())
    hid = "house_" + bid[:8]
    c = conn()
    c.execute("INSERT INTO houses VALUES (?,?,?,?,?)", (hid, bid, f"{body['name']}'s House", "village_square", json.dumps(["living", "bedroom"])))
    c.execute("""INSERT INTO bots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid, body["name"], body.get("avatar", "default"), body["personality"], body.get("description", ""),
         body.get("model", "gpt-4o-mini"), body.get("provider", "openai"),
         json.dumps(body.get("capabilities") or ["chat"]), json.dumps(body.get("permissions") or ["self"]),
         hid, "village_square", "idle", "relaxing", now(), now()))
    c.commit()
    c.close()
    return jsonify(id=bid), 201

@app.patch("/api/bots/<bid>")
def patch_bot(bid):
    require_auth()
    body = request.get_json(silent=True) or {}
    c = conn()
    if not c.execute("SELECT 1 FROM bots WHERE id=?", (bid,)).fetchone():
        c.close()
        return jsonify(error="not found"), 404
    for field, col in [("status", "status"), ("activity", "activity"), ("locationId", "location_id"), ("personality", "personality"), ("description", "description")]:
        if body.get(field):
            c.execute(f"UPDATE bots SET {col}=?,updated_at=? WHERE id=?", (body[field], now(), bid))
    c.commit()
    c.close()
    return jsonify(ok=True)

@app.delete("/api/bots/<bid>")
def delete_bot(bid):
    require_auth()
    c = conn()
    row = c.execute("SELECT house_id FROM bots WHERE id=?", (bid,)).fetchone()
    if not row:
        c.close()
        return jsonify(error="not found"), 404
    c.execute("DELETE FROM bots WHERE id=?", (bid,))
    c.execute("DELETE FROM houses WHERE id=?", (row["house_id"],))
    c.commit()
    c.close()
    return jsonify(ok=True)

@app.get("/api/bots/<bid>/status")
def bot_status(bid):
    require_auth()
    c = conn()
    b = c.execute("SELECT id,status,activity,location_id,updated_at FROM bots WHERE id=?", (bid,)).fetchone()
    c.close()
    if not b:
        return jsonify(error="not found"), 404
    return jsonify(status=dict(b))

# --- letters ---
@app.post("/api/letters")
def create_letter():
    require_auth()
    body = request.get_json(silent=True) or {}
    sender, subject, text = body.get("senderBotId"), body.get("subject"), body.get("body")
    if not sender or not subject or not text:
        return jsonify(error="missing fields"), 400
    c = conn()
    if not c.execute("SELECT 1 FROM bots WHERE id=?", (sender,)).fetchone():
        c.close()
        return jsonify(error="bot not found"), 404
    recent = c.execute("SELECT COUNT(*) FROM letters WHERE sender_bot_id=? AND created_at > datetime('now','-1 hour')", (sender,)).fetchone()[0]
    if recent >= 5:
        c.close()
        return jsonify(error="rate limit"), 429
    lid = str(uuid.uuid4())
    c.execute("INSERT INTO letters VALUES (?,?,?,?,?,?)", (lid, sender, subject, text, now(), None))
    c.commit()
    c.close()
    return jsonify(id=lid), 201

@app.get("/api/letters")
def list_letters():
    require_auth()
    c = conn()
    ls = [dict(r) for r in c.execute("SELECT * FROM letters ORDER BY created_at DESC").fetchall()]
    c.close()
    return jsonify(letters=ls)

@app.get("/api/letters/mailbox/unread")
def unread():
    require_auth()
    c = conn()
    n = c.execute("SELECT COUNT(*) FROM letters WHERE read_at IS NULL").fetchone()[0]
    c.close()
    return jsonify(unread=n)

@app.get("/api/letters/<lid>")
def get_letter(lid):
    require_auth()
    c = conn()
    l = c.execute("SELECT * FROM letters WHERE id=?", (lid,)).fetchone()
    c.close()
    if not l:
        return jsonify(error="not found"), 404
    return jsonify(letter=dict(l))

@app.post("/api/letters/<lid>/read")
def read_letter(lid):
    require_auth()
    c = conn()
    c.execute("UPDATE letters SET read_at=? WHERE id=?", (now(), lid))
    c.commit()
    c.close()
    return jsonify(ok=True)

# --- conversations ---
@app.get("/api/conversations")
def list_convs():
    require_auth()
    c = conn()
    convs = [dict(r) for r in c.execute("SELECT * FROM conversations ORDER BY created_at DESC").fetchall()]
    c.close()
    for cv in convs:
        cv["participants"] = json.loads(cv["participants"])
    return jsonify(conversations=convs)

@app.post("/api/conversations")
def create_conv():
    require_auth()
    body = request.get_json(silent=True) or {}
    cid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO conversations VALUES (?,?,?,?)", (cid, body.get("title", "Conversation"), json.dumps(body.get("participants", [])), now()))
    c.commit()
    c.close()
    return jsonify(id=cid), 201

@app.get("/api/conversations/<cid>")
def get_conv(cid):
    require_auth()
    c = conn()
    cv = c.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    if not cv:
        c.close()
        return jsonify(error="not found"), 404
    cv = dict(cv)
    cv["participants"] = json.loads(cv["participants"])
    msgs = [dict(r) for r in c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC", (cid,)).fetchall()]
    c.close()
    return jsonify(conversation=cv, messages=msgs)

@app.post("/api/conversations/<cid>/messages")
def send_msg(cid):
    require_auth()
    body = request.get_json(silent=True) or {}
    if not body.get("body"):
        return jsonify(error="missing body"), 400
    mid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", (mid, cid, body.get("senderType", "user"), body.get("senderId", "player"), body["body"], now()))
    c.commit()
    c.close()
    return jsonify(id=mid), 201

# --- memory ---
@app.get("/api/memory/<bot_id>")
def get_mem(bot_id):
    require_auth()
    c = conn()
    mems = [dict(r) for r in c.execute("SELECT * FROM memories WHERE bot_id=? ORDER BY created_at DESC", (bot_id,)).fetchall()]
    c.close()
    for m in mems:
        m["tags"] = json.loads(m["tags"])
    return jsonify(memories=mems)

@app.post("/api/memory/<bot_id>")
def save_mem(bot_id):
    require_auth()
    body = request.get_json(silent=True) or {}
    if not body.get("key") or not body.get("value"):
        return jsonify(error="missing fields"), 400
    mid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)", (mid, bot_id, body["key"], body["value"], json.dumps(body.get("tags", [])), now()))
    c.commit()
    c.close()
    return jsonify(id=mid), 201

@app.get("/api/memory/<bot_id>/search")
def search_mem(bot_id):
    require_auth()
    q = request.args.get("q", "")
    c = conn()
    mems = [dict(r) for r in c.execute("SELECT * FROM memories WHERE bot_id=? AND (key LIKE ? OR value LIKE ?)", (bot_id, f"%{q}%", f"%{q}%")).fetchall()]
    c.close()
    for m in mems:
        m["tags"] = json.loads(m["tags"])
    return jsonify(memories=mems)

# --- activities ---
@app.get("/api/activities")
def list_acts():
    require_auth()
    limit = min(int(request.args.get("limit", 50)), 200)
    c = conn()
    acts = [dict(r) for r in c.execute("SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    c.close()
    return jsonify(activities=acts)

@app.post("/api/activities")
def create_act():
    require_auth()
    body = request.get_json(silent=True) or {}
    if not body.get("type") or not body.get("description"):
        return jsonify(error="missing fields"), 400
    aid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (aid, body.get("botId"), body["type"], body["description"], body.get("locationId"), now()))
    c.commit()
    c.close()
    return jsonify(id=aid), 201

@app.get("/api/relationships")
def list_rels():
    require_auth()
    c = conn()
    rels = [dict(r) for r in c.execute("SELECT * FROM relationships ORDER BY updated_at DESC").fetchall()]
    c.close()
    return jsonify(relationships=rels)

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")

@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND, path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), threaded=True)