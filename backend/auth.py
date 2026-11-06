import bcrypt, uuid
from db import conn, now

def verify_password(password):
    c = conn()
    row = c.execute("SELECT password_hash FROM users WHERE id='player'").fetchone()
    c.close()
    if not row: return False
    return bcrypt.checkpw(password.encode(), row["password_hash"].encode())

def set_password(new_pw):
    c = conn()
    h = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    c.execute("UPDATE users SET password_hash=? WHERE id='player'",(h,))
    c.commit(); c.close()

def create_session():
    sid = str(uuid.uuid4())
    c = conn()
    c.execute("INSERT INTO sessions VALUES (?,?,?)",(sid,"player",now()))
    c.commit(); c.close()
    return sid

def valid_session(sid):
    if not sid: return False
    c = conn()
    r = c.execute("SELECT 1 FROM sessions WHERE id=?",(sid,)).fetchone()
    c.close()
    return r is not None

def delete_session(sid):
    c = conn()
    c.execute("DELETE FROM sessions WHERE id=?",(sid,))
    c.commit(); c.close()