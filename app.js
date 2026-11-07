/* Folihen Lotto Center
 * Saves draw results to results/draws.csv in the private GitHub repository FOLIHENWEB/lotto_ecosystem.
 * The PC program tools/sync_master_data.py copies them into the MASTER_DATA Word files.
 * No data is stored in this app's own code. The GitHub token stays only on this device.
 */
"use strict";

const REPO = "FOLIHENWEB/lotto_ecosystem";
const CSV_PATH = "results/draws.csv";
const BRANCH = "main";
const API = "https://api.github.com";
const FIELDS = ["game", "date", "numbers", "machine", "source", "added_at", "note"];
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// file stem -> [display name, weekday 0=Mon, slot 0=Noon 1=main 2=VAG]  (same as tools/lotto_data.py)
const GAMES = {
  "noon monday": ["Noon Monday", 0, 0], "monday special": ["Monday Special", 0, 1], "vag monday": ["VAG Monday", 0, 2],
  "noon tuesday": ["Noon Tuesday", 1, 0], "lucky tuesday": ["Lucky Tuesday", 1, 1], "vag tuesday": ["VAG Tuesday", 1, 2],
  "noon wednesday": ["Noon Wednesday", 2, 0], "wednesday midweek": ["Wednesday Midweek", 2, 1], "vag wednesday": ["VAG Wednesday", 2, 2],
  "noon thursday": ["Noon Thursday", 3, 0], "fortune thursday": ["Fortune Thursday", 3, 1], "vag thursday": ["VAG Thursday", 3, 2],
  "noon friday": ["Noon Friday", 4, 0], "friday bonanza": ["Friday Bonanza", 4, 1], "vag friday": ["VAG Friday", 4, 2],
  "noon saturday": ["Noon Saturday", 5, 0], "saturday national": ["Saturday National", 5, 1], "vag saturday": ["VAG Saturday", 5, 2],
  "sunday aseda": ["Sunday Aseda", 6, 1],
};
const gameName = (g) => (GAMES[g] ? GAMES[g][0] : g);

/* ------------------------------------------------------------------ storage (per device) */
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode: ignore */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

/* ------------------------------------------------------------------ dates */
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fromIso = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const weekday = (d) => (d.getDay() + 6) % 7; // Monday = 0
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
function lastDrawDate(game, ref = today()) {
  const d = new Date(ref);
  while (weekday(d) !== GAMES[game][1]) d.setDate(d.getDate() - 1);
  return d;
}
function niceDate(s) {
  const d = fromIso(s);
  return `${DAYS[weekday(d)].slice(0, 3)} ${d.getDate()} ${d.toLocaleString("en-GB", { month: "short" })} ${d.getFullYear()}`;
}

/* ------------------------------------------------------------------ CSV (matches Python's csv module) */
function parseCsv(text) {
  const rows = []; let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; }
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const head = rows.shift() || [];
  return rows.filter((r) => r.some((x) => x !== "")).map((r) => {
    const o = {}; FIELDS.forEach((f) => { const i = head.indexOf(f); o[f] = i >= 0 ? (r[i] || "").trim() : ""; }); return o;
  });
}
function csvField(v) {
  const s = String(v ?? "").replace(/\n/g, " ");
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function writeCsv(rows) {
  const key = (r) => [r.date, GAMES[r.game] ? GAMES[r.game][2] : 9, r.game];
  const sorted = [...rows].sort((a, b) => {
    const ka = key(a), kb = key(b);
    for (let i = 0; i < 3; i++) { if (ka[i] < kb[i]) return -1; if (ka[i] > kb[i]) return 1; }
    return 0;
  });
  return [FIELDS.join(","), ...sorted.map((r) => FIELDS.map((f) => csvField(r[f])).join(","))].join("\n") + "\n";
}

/* ------------------------------------------------------------------ numbers */
function parseFive(values) {
  const nums = values.map((v) => String(v).trim()).filter((v) => v !== "").map(Number);
  if (nums.length !== 5) return { error: "Enter all 5 numbers." };
  if (nums.some((n) => !Number.isInteger(n) || n < 1 || n > 90)) return { error: "Each number must be between 1 and 90." };
  if (new Set(nums).size !== 5) return { error: "The same number is entered twice." };
  return { nums };
}
const sameSet = (a, b) => { const A = String(a).split("-").map(Number).sort((x, y) => x - y).join(); return A === String(b).split("-").map(Number).sort((x, y) => x - y).join(); };

/* ------------------------------------------------------------------ GitHub */
const b64decode = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
function b64encode(text) {
  const bytes = new TextEncoder().encode(text); let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
class GitHubError extends Error { constructor(status, msg) { super(msg); this.status = status; } }

async function gh(method, path, token, body, raw = false) {
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: raw ? "application/vnd.github.raw+json" : "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new GitHubError(0, "No internet connection. Nothing was saved.");
  }
  if (!res.ok) {
    const hints = {
      401: "GitHub did not accept the token. Check it in Settings (it may have expired).",
      403: "The token is not allowed to change lotto_ecosystem. In GitHub, give it Contents: Read and write.",
      404: "GitHub could not find lotto_ecosystem with this token. Check the token's repository access.",
    };
    throw new GitHubError(res.status, hints[res.status] || `GitHub error ${res.status}. Please try again.`);
  }
  return raw ? res.text() : res.json();
}
async function loadOnline(token) {
  const url = `/repos/${REPO}/contents/${CSV_PATH}?ref=${BRANCH}`;
  const meta = await gh("GET", url, token);
  const text = meta.content ? b64decode(meta.content) : await gh("GET", url, token, null, true);
  return { text, sha: meta.sha };
}
async function saveOnline(token, text, sha, message) {
  return gh("PUT", `/repos/${REPO}/contents/${CSV_PATH}`, token, { message, branch: BRANCH, sha, content: b64encode(text) });
}
/* Apply a change to the latest online copy; if someone else saved in between, reload and try again. */
async function commitChange(token, change, message) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const { text, sha } = await loadOnline(token);
    const rows = parseCsv(text);
    const next = change(rows);
    if (next === null) { state.rows = rows; store.set("fl_cache", text); return false; } // nothing to change
    const out = writeCsv(next);
    try {
      await saveOnline(token, out, sha, message);
      state.rows = next; state.loadedAt = new Date(); store.set("fl_cache", out);
      return true;
    } catch (e) {
      if (!(e instanceof GitHubError) || (e.status !== 409 && e.status !== 422) || attempt === 2) throw e;
    }
  }
}

/* ------------------------------------------------------------------ state */
const state = { token: store.get("fl_token") || "", rows: [], loadedAt: null, error: "", view: "today", resultsGame: "vag monday", form: null };
const cached = store.get("fl_cache");
if (cached) { try { state.rows = parseCsv(cached); } catch { /* ignore bad cache */ } }

async function refresh() {
  if (!state.token) return;
  setStatus("Loading results…");
  try {
    const { text } = await loadOnline(state.token);
    state.rows = parseCsv(text); state.loadedAt = new Date(); state.error = "";
    store.set("fl_cache", text);
    setStatus("");
  } catch (e) {
    state.error = e.message; setStatus("");
  }
  render();
}

/* ------------------------------------------------------------------ rendering helpers */
const $ = (sel, root = document) => root.querySelector(sel);
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function setStatus(msg) { const s = $("#status"); if (s) { s.textContent = msg; s.hidden = !msg; } }
const balls = (numbers, cls = "") => h("div", { class: `balls ${cls}` }, String(numbers).split("-").map((n) => h("span", { class: "ball" }, n)));
const drawFor = (g, d) => state.rows.find((r) => r.game === g && r.date === d);

function go(view, form) { state.view = view; if (form !== undefined) state.form = form; render(); window.scrollTo(0, 0); }

/* ------------------------------------------------------------------ views */
function viewToday() {
  const t = today(); const items = [];
  for (let back = 0; back < 7; back++) {
    const d = new Date(t); d.setDate(t.getDate() - back);
    const games = Object.keys(GAMES).filter((g) => GAMES[g][1] === weekday(d)).sort((a, b) => GAMES[a][2] - GAMES[b][2]);
    items.push(h("h3", { class: "day" }, back === 0 ? `Today · ${niceDate(iso(d))}` : back === 1 ? `Yesterday · ${niceDate(iso(d))}` : niceDate(iso(d))));
    for (const g of games) {
      const r = drawFor(g, iso(d));
      items.push(h("div", { class: "row" },
        h("div", { class: "row-main" }, h("div", { class: "game" }, gameName(g)), r ? balls(r.numbers, "small") : h("div", { class: "missing" }, "Not entered yet")),
        r ? h("span", { class: "tick", title: "Saved" }, "✓") :
          h("button", { class: "btn small", onclick: () => go("add", { game: g, date: iso(d) }) }, "Add")));
    }
  }
  return h("section", {},
    h("p", { class: "lead" }, "Draws from the last 7 days. Tap Add to enter a result."),
    ...items);
}

function viewAdd() {
  const f = state.form || { game: "vag monday", date: iso(lastDrawDate("vag monday")) };
  state.form = f;
  const msg = h("div", { class: "msg", hidden: true });
  f.n = f.n || ["", "", "", "", ""]; f.m = f.m || ["", "", "", "", ""];
  const gameSel = h("select", { id: "game", onchange: (e) => { f.game = e.target.value; f.date = iso(lastDrawDate(f.game)); f.confirmed = false; render(); } },
    DAYS.map((day, wd) => h("optgroup", { label: day },
      Object.keys(GAMES).filter((g) => GAMES[g][1] === wd).sort((a, b) => GAMES[a][2] - GAMES[b][2])
        .map((g) => h("option", { value: g, selected: g === f.game }, gameName(g))))));
  const dateIn = h("input", { type: "date", id: "date", value: f.date, max: iso(new Date(Date.now() + 86400000)), onchange: (e) => { f.date = e.target.value; f.confirmed = false; render(); } });
  const boxes = (prefix) => h("div", { class: "boxes" }, [0, 1, 2, 3, 4].map((i) =>
    h("input", {
      class: "box", id: `${prefix}${i}`, inputmode: "numeric", pattern: "[0-9]*", maxlength: "2", autocomplete: "off",
      "aria-label": `Number ${i + 1}`, value: f[prefix][i] || "",
      oninput: (e) => {
        e.target.value = e.target.value.replace(/\D/g, "").slice(0, 2);
        f[prefix][i] = e.target.value; f.confirmed = false;
        if (e.target.value.length === 2 && i < 4) $(`#${prefix}${i + 1}`).focus();
      },
    })));
  const existing = drawFor(f.game, f.date);
  const wrongDay = f.date && weekday(fromIso(f.date)) !== GAMES[f.game][1];

  const save = async () => {
    const read = (p) => [0, 1, 2, 3, 4].map((i) => $(`#${p}${i}`).value);
    const main = parseFive(read("n"));
    if (main.error) return show(main.error, "error");
    const mvals = read("m"); let machine = "";
    if (mvals.some((v) => v.trim())) {
      const m = parseFive(mvals);
      if (m.error) return show(`Machine numbers: ${m.error}`, "error");
      machine = m.nums.join("-");
    }
    if (!f.date) return show("Choose the draw date.", "error");
    if (!state.token) return show("Add your GitHub token in Settings first.", "error");
    const numbers = main.nums.join("-");
    const notes = [];
    if (wrongDay) notes.push(`date is a ${DAYS[weekday(fromIso(f.date))]}, not this game's draw day`);
    const twins = state.rows.filter((r) => r.date === f.date && r.game !== f.game && sameSet(r.numbers, numbers));
    if (twins.length) notes.push(`identical to ${twins.map((r) => gameName(r.game)).join(", ")} on the same day (probably copied by mistake)`);
    if ((wrongDay || twins.length) && !f.confirmed) {
      f.confirmed = true;
      return show(`Please check: ${notes.join("; ")}. If it is correct, tap Save again.`, "warn");
    }
    btn.disabled = true; btn.textContent = "Saving…";
    try {
      let clash = null;
      await commitChange(state.token, (rows) => {
        const hit = rows.find((r) => r.game === f.game && r.date === f.date);
        if (hit) { clash = hit; return null; }
        return [...rows, { game: f.game, date: f.date, numbers, machine, source: "app", added_at: new Date().toISOString().replace(/\.\d+Z$/, "+00:00"), note: notes.join("; ") }];
      }, `Add ${gameName(f.game)} ${f.date}: ${numbers}`);
      if (clash) {
        show(`${gameName(f.game)} on ${niceDate(f.date)} is already saved as ${clash.numbers}. Nothing was changed. To replace it, delete it on the Results page first.`, "error");
        btn.disabled = false; btn.textContent = "Save result"; return;
      }
      state.flash = `Saved ${gameName(f.game)}, ${niceDate(f.date)}: ${numbers}. Your PC adds it to MASTER_DATA at its next sync.`;
      state.form = null; go("today");
    } catch (e) {
      show(e.message, "error"); btn.disabled = false; btn.textContent = "Save result";
    }
  };
  function show(text, kind) { msg.textContent = text; msg.className = `msg ${kind}`; msg.hidden = false; }
  const btn = h("button", { class: "btn primary wide", onclick: save }, "Save result");

  return h("section", {},
    h("label", { for: "game" }, "Game"), gameSel,
    h("label", { for: "date" }, "Draw date"), dateIn,
    wrongDay ? h("div", { class: "msg warn" }, `${niceDate(f.date)} is not a ${DAYS[GAMES[f.game][1]]}. Check the date.`) : null,
    existing ? h("div", { class: "msg info" }, h("div", {}, `Already saved for this date:`), balls(existing.numbers, "small")) : null,
    h("label", {}, "Winning numbers"), boxes("n"),
    h("details", { class: "machine" }, h("summary", {}, "Machine numbers (optional)"), boxes("m")),
    msg, btn);
}

function viewResults() {
  const g = state.resultsGame;
  const sel = h("select", { onchange: (e) => { state.resultsGame = e.target.value; render(); } },
    DAYS.map((day, wd) => h("optgroup", { label: day },
      Object.keys(GAMES).filter((x) => GAMES[x][1] === wd).sort((a, b) => GAMES[a][2] - GAMES[b][2])
        .map((x) => h("option", { value: x, selected: x === g }, gameName(x))))));
  const rows = state.rows.filter((r) => r.game === g).sort((a, b) => (a.date < b.date ? 1 : -1));
  const list = rows.slice(0, 60).map((r) => h("div", { class: "row" },
    h("div", { class: "row-main" },
      h("div", { class: "game" }, niceDate(r.date), r.source === "app" ? h("span", { class: "tag" }, "app") : null),
      balls(r.numbers, "small"),
      r.machine ? h("div", { class: "sub" }, `Machine: ${r.machine.replace(/-/g, " · ")}`) : null,
      r.note ? h("div", { class: "note" }, `⚠ ${r.note}`) : null),
    r.source === "app" ? h("button", { class: "btn small ghost", onclick: () => removeDraw(r) }, "Delete") : null));
  return h("section", {}, h("label", {}, "Game"), sel,
    h("p", { class: "lead" }, `${rows.length} draws saved. Newest first${rows.length > 60 ? " (showing 60)" : ""}.`), ...list);
}

async function removeDraw(r) {
  if (!window.confirm(`Delete ${gameName(r.game)} on ${niceDate(r.date)} (${r.numbers})?\n\nIf your PC has already copied it into MASTER_DATA, delete it in the Word file too.`)) return;
  setStatus("Deleting…");
  try {
    await commitChange(state.token, (rows) => rows.filter((x) => !(x.game === r.game && x.date === r.date && x.source === "app")),
      `Delete ${gameName(r.game)} ${r.date}`);
    state.flash = "Deleted.";
  } catch (e) { state.error = e.message; }
  setStatus(""); render();
}

function viewSettings() {
  const input = h("input", { type: "password", id: "token", placeholder: "github_pat_…", value: state.token, autocomplete: "off" });
  const msg = h("div", { class: "msg", hidden: true });
  const show = (t, k) => { msg.textContent = t; msg.className = `msg ${k}`; msg.hidden = false; };
  const tokenUrl = "https://github.com/settings/personal-access-tokens/new?name=Folihen%20Lotto%20Center&description=Lets%20the%20Folihen%20Lotto%20Center%20app%20save%20results&target_name=FOLIHENWEB&expires_in=none&contents=write";
  return h("section", {},
    h("h3", {}, "Connect to GitHub"),
    h("p", { class: "lead" }, "The app saves results into your private lotto_ecosystem repository. It needs a GitHub token, entered once on each phone or computer. The token stays on this device only."),
    h("label", { for: "token" }, "GitHub token"), input,
    h("div", { class: "actions" },
      h("button", { class: "btn primary", onclick: async () => {
        const t = input.value.trim(); if (!t) return show("Paste the token first.", "error");
        show("Checking…", "info");
        try { const { text } = await loadOnline(t); state.token = t; store.set("fl_token", t); state.rows = parseCsv(text); store.set("fl_cache", text); state.loadedAt = new Date(); state.error = ""; show(`Connected. ${state.rows.length} draws found.`, "ok"); }
        catch (e) { show(e.message, "error"); }
      } }, "Save and test"),
      state.token ? h("button", { class: "btn ghost", onclick: () => { store.del("fl_token"); state.token = ""; render(); } }, "Remove from this device") : null),
    msg,
    h("details", { class: "help", open: !state.token }, h("summary", {}, "How to get a token"),
      h("ol", {},
        h("li", {}, "Open ", h("a", { href: tokenUrl, target: "_blank", rel: "noopener" }, "this GitHub page"), " and sign in if asked."),
        h("li", {}, "Under Repository access, choose ", h("b", {}, "Only select repositories"), " and pick ", h("b", {}, "lotto_ecosystem"), "."),
        h("li", {}, "Under Permissions, set ", h("b", {}, "Contents"), " to ", h("b", {}, "Read and write"), " (it may already be set)."),
        h("li", {}, "Click ", h("b", {}, "Generate token"), ", copy it, and paste it above."))),
    h("p", { class: "fine" }, state.loadedAt ? `Last loaded ${state.loadedAt.toLocaleTimeString()}. ${state.rows.length} draws.` : ""));
}

/* ------------------------------------------------------------------ shell */
function render() {
  const app = $("#app"); app.replaceChildren();
  const views = { today: viewToday, add: viewAdd, results: viewResults, settings: viewSettings };
  if (!state.token && state.view !== "settings") state.view = "settings";
  if (state.flash) { app.append(h("div", { class: "msg ok" }, state.flash)); state.flash = ""; }
  if (state.error) app.append(h("div", { class: "msg error" }, state.error, " ", h("button", { class: "btn small ghost", onclick: refresh }, "Try again")));
  app.append(views[state.view]());
  document.querySelectorAll("nav button").forEach((b) => b.setAttribute("aria-current", b.dataset.view === state.view ? "page" : "false"));
}

document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => {
  if (b.dataset.view === "add") state.form = null;
  go(b.dataset.view);
}));
$("#refresh").addEventListener("click", refresh);
render();
refresh();
