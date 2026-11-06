import json, uuid, random, threading, time
from db import conn, now

LOCATIONS = ["village_square","park","forest","lake","cafe","library"]
ACTIVITIES = ["reading","walking","working","talking","visiting","relaxing","exploring","writing"]

def tick():
    c = conn()
    bots = [dict(r) for r in c.execute("SELECT * FROM bots").fetchall()]
    for b in bots:
        new_loc = random.choice(LOCATIONS) if random.random() < 0.4 else b["location_id"]
        new_act = random.choice(ACTIVITIES)
        c.execute("UPDATE bots SET location_id=?,activity=?,status=?,updated_at=? WHERE id=?",
                  (new_loc, new_act, "chatting" if random.random()<0.2 else "active", now(), b["id"]))
        if random.random() < 0.3:
            c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)",
                      (str(uuid.uuid4()), b["id"], new_act, f"{b['name']} is {new_act} at {new_loc}", new_loc, now()))
        if random.random() < 0.05:
            recent = c.execute("SELECT COUNT(*) FROM letters WHERE sender_bot_id=? AND created_at > datetime('now','-6 hours')", (b["id"],)).fetchone()[0]
            if recent == 0:
                c.execute("INSERT INTO letters VALUES (?,?,?,?,?,?)",
                          (str(uuid.uuid4()), b["id"], f"Hello from {b['name']}", f"{b['name']} wanted to say hi. Weather is lovely.", now(), None))
    # relationships
    groups = {}
    for b in bots:
        groups.setdefault(b["location_id"], []).append(b["id"])
    for loc, ids in groups.items():
        for i in range(len(ids)):
            for j in range(i+1, len(ids)):
                a, bb = ids[i], ids[j]
                ex = c.execute("SELECT id,score FROM relationships WHERE (bot_a=? AND bot_b=?) OR (bot_a=? AND bot_b=?)", (a,bb,bb,a)).fetchone()
                if ex:
                    c.execute("UPDATE relationships SET score=?,updated_at=? WHERE id=?", (min(100, ex["score"]+1), now(), ex["id"]))
                else:
                    c.execute("INSERT INTO relationships VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), a, bb, 1, "", now()))
    c.execute("INSERT OR REPLACE INTO world_state VALUES (?,?)", ("time", now()))
    c.commit()
    c.close()

def start(interval=30):
    def loop():
        while True:
            try:
                tick()
            except Exception as e:
                print("sim error", e)
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()
    tick()