const API = "http://localhost:7778";
let state = { view: "login", authed: false, world: null, bots: [], letters: [], activities: [], unread: 0, selectedBot: null, password: "" };

async function api(path, opts) {
  const res = await fetch(API + path, Object.assign({ credentials: "include", headers: { "Content-Type": "application/json" } }, opts || {}));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function render() {
  const app = document.getElementById("app");
  if (!state.authed) {
    app.innerHTML = `<div class="login-screen"><div class="panel"><h1>BotLand</h1><p class="subtitle">A cozy world for AI bots</p>
      <input type="password" id="pw" placeholder="password" value="${state.password}">
      <button id="loginBtn">Enter</button></div></div>`;
    document.getElementById("pw").addEventListener("input", e => state.password = e.target.value);
    document.getElementById("pw").addEventListener("keydown", e => { if (e.key === "Enter") login(); });
    document.getElementById("loginBtn").addEventListener("click", login);
    return;
  }
  app.innerHTML = `
    <div class="app">
      <nav class="nav">
        ${navBtn("village","Village")} ${navBtn("house","My House")} ${navBtn("bots","Bots")}
        ${navBtn("mailbox","Mailbox" + (state.unread>0?` <span class="badge">${state.unread}</span>`:""))}
        ${navBtn("activity","Activity")} ${navBtn("settings","Settings")}
        <button id="logout">Logout</button>
      </nav>
      <main class="content" id="content"></main>
    </div>`;
  document.querySelectorAll(".nav button[data-view]").forEach(b => b.addEventListener("click", () => { state.view = b.dataset.view; render(); }));
  document.getElementById("logout").addEventListener("click", logout);
  renderView();
}

function navBtn(view, label) {
  return `<button data-view="${view}" class="${state.view===view?'active':''}">${label}</button>`;
}

async function renderView() {
  const c = document.getElementById("content");
  if (state.view === "village") {
    await loadWorld();
    const tiles = (state.world?.locations || []).map(l => `
      <div class="tile ${l.kind}" style="grid-column:${l.x};grid-row:${l.y}">
        <div class="tile-label">${l.name}</div>
        <div class="tile-bots">${state.bots.filter(b=>b.location_id===l.id).map(b=>`<span class="bot-dot" title="${b.name}">${b.name[0]}</span>`).join("")}</div>
      </div>`).join("");
    c.innerHTML = `<h2>Village</h2><div class="tilemap">${tiles}</div>
      <div class="legend">${state.bots.map(b=>`<span class="legend-item">${b.name}: ${b.activity} @ ${b.location_id}</span>`).join("")}</div>`;
  } else if (state.view === "house") {
    c.innerHTML = `<h2>Your House</h2><div class="rooms">
      <div class="room">Living room</div><div class="room">Desk &amp; computer</div><div class="room">Bed</div>
      <div class="room">Bookshelf</div><div class="room">Fireplace</div></div>
      <p>Mailbox: ${state.unread} unread letter(s)</p>
      <button id="openMail">Open Mailbox</button>`;
    document.getElementById("openMail").addEventListener("click", () => { state.view="mailbox"; render(); });
  } else if (state.view === "bots") {
    await loadWorld();
    c.innerHTML = `<h2>Bot Directory</h2><div class="bot-grid">${state.bots.map(b=>`
      <div class="bot-card" data-id="${b.id}"><div class="avatar">${b.name[0]}</div><div class="bot-name">${b.name}</div><div class="bot-status">${b.status} · ${b.activity}</div></div>`).join("")}</div>
      <div id="detail"></div>`;
    document.querySelectorAll(".bot-card").forEach(el => el.addEventListener("click", async () => {
      const r = await api("/api/bots/" + el.dataset.id);
      const d = document.getElementById("detail");
      d.innerHTML = `<div class="panel bot-detail"><h3>${r.bot.name}</h3><p>${r.bot.description}</p>
        <p><b>Personality:</b> ${r.bot.personality}</p><p><b>Location:</b> ${r.bot.location_id}</p>
        <p><b>Model:</b> ${r.bot.model} (${r.bot.provider})</p><button id="closeDetail">Close</button></div>`;
      document.getElementById("closeDetail").addEventListener("click", () => d.innerHTML = "");
    }));
  } else if (state.view === "mailbox") {
    await loadLetters();
    c.innerHTML = `<h2>Mailbox</h2>` + (state.letters.length===0 ? "<p>No letters yet.</p>" : state.letters.map(l => `
      <div class="letter ${l.read_at?'read':'unread'}">
        <div class="letter-head"><span>From: ${botName(l.sender_bot_id)}</span><span>${new Date(l.created_at).toLocaleString()}</span></div>
        <div class="letter-subject">${l.subject}</div><div class="letter-body">${l.body}</div>
        ${!l.read_at?`<button data-id="${l.id}" class="markread">Mark read</button>`:""}
      </div>`).join(""));
    document.querySelectorAll(".markread").forEach(b => b.addEventListener("click", async () => {
      await api("/api/letters/" + b.dataset.id + "/read", { method: "POST" });
      await loadLetters(); renderView();
    }));
  } else if (state.view === "activity") {
    await loadActivities();
    c.innerHTML = `<h2>Activity Log</h2><ul>${state.activities.map(a=>`<li>${new Date(a.created_at).toLocaleTimeString()} — ${a.description}</li>`).join("")}</ul>`;
  } else if (state.view === "settings") {
    c.innerHTML = `<h2>Settings</h2><div class="settings">
      <input type="password" id="npw" placeholder="new password">
      <button id="chgpw">Change password</button>
      <p>Backend: http://localhost:7778 · MCP: http://localhost:4001/mcp</p></div>`;
    document.getElementById("chgpw").addEventListener("click", async () => {
      const pw = document.getElementById("npw").value;
      await api("/api/auth/password", { method: "POST", body: JSON.stringify({ password: pw }) });
      alert("changed");
    });
  }
}

function botName(id) { const b = state.bots.find(x=>x.id===id); return b?b.name:id; }

async function loadWorld() {
  const w = await api("/api/world/state");
  state.world = w; state.bots = w.bots;
  const m = await api("/api/letters/mailbox/unread");
  state.unread = m.unread;
}
async function loadLetters() {
  const l = await api("/api/letters"); state.letters = l.letters;
  const m = await api("/api/letters/mailbox/unread"); state.unread = m.unread;
}
async function loadActivities() {
  const a = await api("/api/activities?limit=30"); state.activities = a.activities;
}

async function login() {
  try {
    await api("/api/auth/login", { method: "POST", body: JSON.stringify({ password: state.password }) });
    state.authed = true; state.view = "village"; render();
  } catch (e) { alert("Wrong password"); }
}
async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  state.authed = false; state.view = "login"; render();
}

// check session
(async () => {
  try { await api("/api/auth/me"); state.authed = true; state.view = "village"; } catch(e) {}
  render();
  setInterval(async () => { if (state.authed) { try { const m = await api("/api/letters/mailbox/unread"); state.unread = m.unread; render(); } catch(e){} } }, 15000);
})();