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
  if (raw) return res.text();
  const text = await res.text(); // some calls (e.g. starting a run) answer with an empty body
  return text ? JSON.parse(text) : null;
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
const state = { token: store.get("fl_token") || "", rows: [], loadedAt: null, error: "", view: "dashboard", resultsGame: "vag monday", form: null };
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
function weekItems() {
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
  return items;
}

const realRows = () => { const lim = iso(new Date(Date.now() + 86400000)); return state.rows.filter((r) => r.date <= lim); };
function coverage() {
  const by = {};
  for (const r of realRows()) { (by[r.game] = by[r.game] || []).push(r.date); }
  return Object.keys(GAMES).map((g) => {
    const ds = (by[g] || []).sort();
    return { g, n: ds.length, first: ds[0] || "", last: ds[ds.length - 1] || "" };
  });
}

function viewDashboard() {
  const t = today(); let missing = 0;
  for (let back = 0; back < 7; back++) {
    const d = new Date(t); d.setDate(t.getDate() - back);
    for (const g of Object.keys(GAMES)) if (GAMES[g][1] === weekday(d) && !drawFor(g, iso(d))) missing++;
  }
  const latest = realRows().reduce((m, r) => (r.date > m ? r.date : m), "");
  const earliest = realRows().reduce((m, r) => (!m || r.date < m ? r.date : m), "");
  const fromApp = state.rows.filter((r) => r.source === "app").length;
  const card = (k, v, s) => h("div", { class: "card" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v), s ? h("div", { class: "s" }, s) : null);
  const cov = coverage();
  return h("section", {},
    h("h2", {}, "Overview"),
    h("p", { class: "lead" }, "Your results for all 19 games, kept online and copied into MASTER_DATA on your PC."),
    h("div", { class: "cards" },
      card("Draws saved", state.rows.length.toLocaleString(), earliest ? `since ${niceDate(earliest)}` : ""),
      card("Games", "19", "Noon, main and VAG"),
      card("Latest draw", latest ? niceDate(latest) : "—", ""),
      card("Missing this week", String(missing), missing ? "tap Add below" : "all entered"),
      card("Added from the app", fromApp.toLocaleString(), "")),
    h("div", { class: "grid2" },
      h("div", { class: "panel" }, h("h3", { style: "margin-top:0" }, "This week"), ...weekItems()),
      h("div", { class: "panel" }, h("h3", { style: "margin-top:0" }, "Results per game"),
        h("div", { class: "table-wrap" }, h("table", { class: "cov" },
          h("thead", {}, h("tr", {}, h("th", {}, "Game"), h("th", {}, "From"), h("th", {}, "Latest"), h("th", { class: "num" }, "Draws"))),
          h("tbody", {}, cov.map((c) => h("tr", { style: "cursor:pointer", onclick: () => { state.resultsGame = c.g; go("masterdata"); } },
            h("td", {}, gameName(c.g)), h("td", {}, c.first ? c.first.slice(0, 7) : "—"), h("td", {}, c.last ? niceDate(c.last) : "—"), h("td", { class: "num" }, c.n.toLocaleString())))))))));
}

/* ------------------------------------------------------------------ engines (run in the cloud) */
const WORKFLOW = "run-engines.yml";
// Game numbers used by every engine and the Master Launcher.
const GAME_IDS = ["monday special", "wednesday midweek", "friday bonanza", "saturday national", "sunday aseda", "vag monday",
  "noon monday", "vag tuesday", "noon tuesday", "lucky tuesday", "vag wednesday", "noon wednesday", "vag thursday",
  "noon thursday", "fortune thursday", "vag friday", "noon friday", "vag saturday", "noon saturday"];
const eng = { game: null, run: null, picks: null, files: null, scoreboard: "", msg: "", timer: null, loading: false };

/* The next game to be drawn: today's earliest game with no result yet, else tomorrow's first. */
function nextGame() {
  const t = today();
  for (let add = 0; add < 8; add++) {
    const d = new Date(t); d.setDate(t.getDate() + add);
    const games = Object.keys(GAMES).filter((g) => GAMES[g][1] === weekday(d) && !drawFor(g, iso(d))).sort((a, b) => GAMES[a][2] - GAMES[b][2]);
    if (games.length) return games[0];
  }
  return "saturday national";
}
const twoDigits = (n) => String(n).padStart(2, "0");
const ballRow = (nums, cls = "") => h("div", { class: `balls ${cls}` }, nums.map((n) => h("span", { class: "ball" }, twoDigits(n))));

async function engLatestRun() {
  const r = await gh("GET", `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`, state.token);
  eng.run = r.workflow_runs && r.workflow_runs[0] ? r.workflow_runs[0] : null;
}
async function engLoadPicks() {
  eng.loading = true;
  try {
    let list = [];
    try { list = await gh("GET", `/repos/${REPO}/contents/predictions?ref=${BRANCH}`, state.token); } catch (e) { if (e.status !== 404) throw e; }
    eng.files = Array.isArray(list) ? list.filter((f) => f.name.endsWith(".json")) : [];
    const slug = eng.game.replace(/ /g, "-");
    const mine = eng.files.filter((f) => f.name.split("_")[1] === slug).sort((a, b) => (a.name.split("_")[2] < b.name.split("_")[2] ? 1 : -1));
    eng.picks = mine.length ? JSON.parse(await gh("GET", `/repos/${REPO}/contents/predictions/${mine[0].name}?ref=${BRANCH}`, state.token, null, true)) : null;
    try { eng.scoreboard = await gh("GET", `/repos/${REPO}/contents/predictions/scoreboard.txt?ref=${BRANCH}`, state.token, null, true); } catch { eng.scoreboard = ""; }
  } finally { eng.loading = false; }
}
async function engRefresh() {
  try { await Promise.all([engLatestRun(), engLoadPicks()]); eng.msg = eng.msg && eng.msg.startsWith("Could not") ? "" : eng.msg; }
  catch (e) { eng.msg = e.message; }
  if (state.view === "engines") render();
  clearTimeout(eng.timer);
  if (eng.run && eng.run.status !== "completed" && state.view === "engines") eng.timer = setTimeout(engRefresh, 20000);
}
async function engStart() {
  eng.msg = "Starting…"; render();
  try {
    await gh("POST", `/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, state.token,
      { ref: BRANCH, inputs: { game: String(GAME_IDS.indexOf(eng.game) + 1) } });
    eng.msg = `Started for ${gameName(eng.game)}. It takes about 5–15 minutes; this page updates by itself.`;
    setTimeout(engRefresh, 6000);
  } catch (e) {
    eng.msg = e.status === 403 || e.status === 404
      ? "This token can't start runs yet. On GitHub, edit the token and set Actions to \"Read and write\" (Repository permissions), then try again."
      : e.message;
  }
  render();
}
async function engDownloadReport() {
  if (!eng.picks || !eng.picks.report) return;
  try {
    const res = await fetch(`${API}/repos/${REPO}/contents/predictions/reports/${encodeURIComponent(eng.picks.report)}?ref=${BRANCH}`,
      { headers: { Authorization: `Bearer ${state.token}`, Accept: "application/vnd.github.raw+json" }, cache: "no-store" });
    if (!res.ok) throw new Error(`GitHub error ${res.status}`);
    const url = URL.createObjectURL(await res.blob());
    const a = h("a", { href: url, download: eng.picks.report }); document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (e) { eng.msg = `Could not download the report: ${e.message}`; render(); }
}

function runStatusPanel() {
  const r = eng.run;
  if (!r) return null;
  const started = new Date(r.created_at);
  const mins = Math.max(0, Math.round((Date.now() - started) / 60000));
  const label = r.status === "completed"
    ? (r.conclusion === "success" ? "Last run finished" : `Last run did not finish (${r.conclusion})`)
    : r.status === "queued" ? "Waiting to start…" : `Running… ${mins} min so far`;
  return h("div", { class: `msg ${r.status !== "completed" ? "info" : r.conclusion === "success" ? "ok" : "error"}` },
    `${label} · started ${started.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}`,
    r.status === "completed" && r.conclusion !== "success" ? h("a", { href: r.html_url, target: "_blank", rel: "noopener", style: "margin-left:8px" }, "details") : null);
}

function picksPanel() {
  const p = eng.picks;
  if (eng.loading && !p) return h("p", { class: "lead" }, "Loading picks…");
  if (!p) return h("div", { class: "panel" }, h("p", { style: "margin:0" }, `No cloud picks for ${gameName(eng.game)} yet. Press Run engines.`));
  const engines = Object.keys(p.picks).filter((e) => p.picks[e] && p.picks[e].length);
  const c10 = {}, c30 = {}, rs = {};
  for (const e of engines) p.picks[e].slice(0, 60).forEach((n, i) => { rs[n] = (rs[n] || 0) + i + 1; if (i < 10) c10[n] = (c10[n] || 0) + 1; if (i < 30) c30[n] = (c30[n] || 0) + 1; });
  const order = Array.from({ length: 90 }, (_, i) => i + 1).sort((a, b) => (c10[b] || 0) - (c10[a] || 0) || (c30[b] || 0) - (c30[a] || 0) || (rs[a] || 999) - (rs[b] || 999)).slice(0, 15);
  const result = drawFor(p.game, p.target_date);
  const won = result ? new Set(result.numbers.split("-").map(Number)) : null;
  const mark = (nums) => h("div", { class: "balls" }, nums.map((n) => h("span", { class: `ball${won && won.has(n) ? " hit" : ""}` }, twoDigits(n))));
  return h("div", {},
    h("div", { class: "panel" },
      h("h3", { style: "margin-top:0" }, `${gameName(p.game)} · draw of ${niceDate(p.target_date)}`),
      h("p", { class: "lead" }, `Picks made ${new Date(p.run_at).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}, before the draw.`),
      result ? h("div", {}, h("p", { style: "margin:4px 0" }, "Result:"), balls(result.numbers, "hit")) : null,
      h("h3", {}, "Numbers the engines agree on"),
      h("p", { class: "lead" }, "How many engines have each number in their Top 10 (a plain count, not yet weighted by track record)."),
      h("div", { class: "table-wrap" }, h("table", { class: "cov" },
        h("thead", {}, h("tr", {}, h("th", {}, "No."), h("th", { class: "num" }, "Top 10 of"), h("th", { class: "num" }, "Top 30 of"))),
        h("tbody", {}, order.map((n) => h("tr", { class: won && won.has(n) ? "hitrow" : "" },
          h("td", {}, twoDigits(n)), h("td", { class: "num" }, `${c10[n] || 0} / ${engines.length}`), h("td", { class: "num" }, `${c30[n] || 0} / ${engines.length}`)))))),
      p.report ? h("div", { class: "actions" }, h("button", { class: "btn", onclick: engDownloadReport }, "Download Word report")) : null),
    h("div", { class: "panel" }, h("h3", { style: "margin-top:0" }, "Each engine"),
      ...engines.map((e) => h("div", { class: "engine-pick" },
        h("div", { class: "engine-name" }, e.charAt(0).toUpperCase() + e.slice(1)),
        mark(p.picks[e].slice(0, 10)),
        h("details", {}, h("summary", {}, "Top 60"),
          ...[0, 10, 20, 30, 40, 50].filter((i) => i < p.picks[e].length).map((i) =>
            h("div", { class: "row60" }, h("span", { class: "pos" }, `${i + 1}–${Math.min(i + 10, p.picks[e].length)}`), mark(p.picks[e].slice(i, i + 10))))))),
      Object.keys(p.picks).filter((e) => !(p.picks[e] && p.picks[e].length)).length
        ? h("p", { class: "fine" }, `No picks from: ${Object.keys(p.picks).filter((e) => !(p.picks[e] && p.picks[e].length)).join(", ")}.`) : null),
    eng.scoreboard ? h("details", { class: "panel" }, h("summary", {}, "Scoreboard (all games)"), h("pre", { class: "scoreboard" }, eng.scoreboard)) : null);
}

function viewEngines() {
  if (!eng.game) { eng.game = nextGame(); engRefresh(); }
  const running = eng.run && eng.run.status !== "completed";
  const sel = h("select", { onchange: (ev) => { eng.game = ev.target.value; eng.picks = null; render(); engLoadPicks().then(render).catch((e) => { eng.msg = e.message; render(); }); } },
    GAME_IDS.map((g) => h("option", { value: g, selected: g === eng.game }, gameName(g))));
  return h("section", {},
    h("h2", {}, "Prediction Engines"),
    h("p", { class: "lead" }, "Run all the engines in the cloud. Your PC can be off. Picks are saved before the draw and scored afterwards."),
    h("div", { class: "panel form" },
      h("label", {}, "Game"), sel,
      h("div", { class: "actions" },
        h("button", { class: "btn primary", disabled: running, onclick: engStart }, running ? "Engines are running…" : "Run engines"),
        h("button", { class: "btn ghost", onclick: () => { eng.msg = ""; engRefresh(); } }, "Refresh")),
      h("p", { class: "fine", style: "margin-top:10px" }, "Add the latest results first: the engines use them. A run takes about 5–15 minutes.")),
    eng.msg ? h("div", { class: "msg info" }, eng.msg) : null,
    runStatusPanel(),
    picksPanel());
}

function viewAbout() {
  return h("section", {},
    h("h2", {}, "About"),
    h("div", { class: "panel" },
      h("p", {}, "Folihen Lotto Center keeps the results for all 19 NLA games in one place, from your phone or PC."),
      h("ul", { class: "plain" },
        h("li", {}, "Results are saved in the private lotto_ecosystem repository on GitHub (results/draws.csv)."),
        h("li", {}, "Your PC copies new results into the MASTER_DATA Word files every 30 minutes while it is on."),
        h("li", {}, "History comes from your MASTER_DATA, the GhanaYello archive and the printed Lotto paper, checked against each other."))));
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
      state.form = null; go("dashboard");
    } catch (e) {
      show(e.message, "error"); btn.disabled = false; btn.textContent = "Save result";
    }
  };
  function show(text, kind) { msg.textContent = text; msg.className = `msg ${kind}`; msg.hidden = false; }
  const btn = h("button", { class: "btn primary wide", onclick: save }, "Save result");

  return h("section", { class: "form" }, h("h2", {}, "Add result"),
    h("label", { for: "game" }, "Game"), gameSel,
    h("label", { for: "date" }, "Draw date"), dateIn,
    wrongDay ? h("div", { class: "msg warn" }, `${niceDate(f.date)} is not a ${DAYS[GAMES[f.game][1]]}. Check the date.`) : null,
    existing ? h("div", { class: "msg info" }, h("div", {}, `Already saved for this date:`), balls(existing.numbers, "small")) : null,
    h("label", {}, "Winning numbers"), boxes("n"),
    h("details", { class: "machine" }, h("summary", {}, "Machine numbers (optional)"), boxes("m")),
    msg, btn);
}

function viewMasterData() {
  const g = state.resultsGame;
  const sel = h("select", { onchange: (e) => { state.resultsGame = e.target.value; state.showAll = false; render(); } },
    DAYS.map((day, wd) => h("optgroup", { label: day },
      Object.keys(GAMES).filter((x) => GAMES[x][1] === wd).sort((a, b) => GAMES[a][2] - GAMES[b][2])
        .map((x) => h("option", { value: x, selected: x === g }, gameName(x))))));
  const rows = state.rows.filter((r) => r.game === g).sort((a, b) => (a.date < b.date ? 1 : -1));
  const list = (state.showAll ? rows : rows.slice(0, 60)).map((r) => h("div", { class: "row" },
    h("div", { class: "row-main" },
      h("div", { class: "game" }, niceDate(r.date), r.source === "app" ? h("span", { class: "tag" }, "app") : null),
      balls(r.numbers, "small"),
      r.machine ? h("div", { class: "sub" }, `Machine: ${r.machine.replace(/-/g, " · ")}`) : null,
      r.note ? h("div", { class: "note" }, `⚠ ${r.note}`) : null),
    r.source === "app" ? h("button", { class: "btn small ghost", onclick: () => removeDraw(r) }, "Delete") : null));
  const shown = state.showAll ? rows : rows.slice(0, 60);
  const list2 = list.slice(0, shown.length);
  return h("section", { class: "form-wide" }, h("h2", {}, "MASTER_DATA"),
    h("p", { class: "lead" }, "Every saved draw for one game, newest first."),
    h("label", {}, "Game"), sel,
    h("p", { class: "lead", style: "margin-top:12px" }, `${rows.length.toLocaleString()} draws${rows.length ? ` from ${niceDate(rows[rows.length - 1].date)} to ${niceDate(rows[0].date)}` : ""}.`),
    ...list2,
    rows.length > 60 ? h("button", { class: "btn", onclick: () => { state.showAll = !state.showAll; render(); } }, state.showAll ? "Show fewer" : `Show all ${rows.length}`) : null);
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
  const tokenUrl = "https://github.com/settings/personal-access-tokens/new?name=Folihen%20Lotto%20Center&description=Lets%20the%20Folihen%20Lotto%20Center%20app%20save%20results&target_name=FOLIHENWEB&expires_in=none&contents=write&actions=write";
  const dark = document.documentElement.getAttribute("data-theme") === "dark" || (!document.documentElement.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return h("section", { class: "form" }, h("h2", {}, "Settings"),
    h("h3", {}, "Appearance"),
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: toggleTheme }, dark ? "Switch to light mode" : "Switch to dark mode")),
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
        h("li", {}, "Under Permissions, set ", h("b", {}, "Contents"), " and ", h("b", {}, "Actions"), " to ", h("b", {}, "Read and write"), " (Actions lets the app start engine runs)."),
        h("li", {}, "Click ", h("b", {}, "Generate token"), ", copy it, and paste it above."))),
    h("p", { class: "fine" }, state.loadedAt ? `Last loaded ${state.loadedAt.toLocaleTimeString()}. ${state.rows.length} draws.` : ""));
}

/* ------------------------------------------------------------------ shell */
const TITLES = { dashboard: "Dashboard", add: "Add result", masterdata: "MASTER_DATA", engines: "Prediction Engines", settings: "Settings", about: "About" };
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme");
  const isDark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  const next = isDark ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next); store.set("fl_theme", next);
  setThemeIcon();
  if (state.view === "settings") render();
}
function setThemeIcon() {
  const cur = document.documentElement.getAttribute("data-theme");
  const isDark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  const sun = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const moon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  $("#theme").innerHTML = isDark ? sun : moon;
}
function setMenu(open) {
  $("#sidebar").classList.toggle("open", open);
  $("#overlay").hidden = !open;
}
function render() {
  const app = $("#app"); app.replaceChildren();
  const views = { dashboard: viewDashboard, add: viewAdd, masterdata: viewMasterData, engines: viewEngines, settings: viewSettings, about: viewAbout };
  if (!views[state.view]) state.view = "dashboard";
  if (!state.token && !["settings", "about"].includes(state.view)) {
    state.view = "settings";
    state.flash = state.flash || "This app on this screen is not connected yet. Paste your GitHub token below and tap Save and test. (A home-screen icon keeps its own settings, separate from the browser.)";
  }
  if (state.flash) { app.append(h("div", { class: "msg ok" }, state.flash)); state.flash = ""; }
  if (state.error) app.append(h("div", { class: "msg error" }, state.error, " ", h("button", { class: "btn small ghost", onclick: refresh }, "Try again")));
  app.append(views[state.view]());
  $("#page-title").textContent = TITLES[state.view];
  document.title = `${TITLES[state.view]} · Folihen Lotto Center`;
  document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-current", b.dataset.view === state.view ? "page" : "false"));
  const on = !!state.token && !state.error;
  $("#conn-dot").classList.toggle("on", on);
  $("#conn-text").textContent = !state.token ? "Not connected" : state.error ? "Connection problem" : "Connected to GitHub";
  $("#sb-draws").textContent = state.rows.length ? `${state.rows.length.toLocaleString()} draws · 19 games` : "No results loaded";
  $("#sb-loaded").textContent = state.loadedAt ? `Last loaded ${state.loadedAt.toLocaleTimeString()}` : "";
}

document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
  if (b.dataset.view === "add") state.form = null;
  setMenu(false);
  go(b.dataset.view);
}));
document.querySelectorAll("[data-menu]").forEach((b) => b.addEventListener("click", () => setMenu(true)));
$("#menu").addEventListener("click", () => setMenu(true));
$("#overlay").addEventListener("click", () => setMenu(false));
$("#theme").addEventListener("click", toggleTheme);
setThemeIcon();
$("#refresh").addEventListener("click", refresh);
render();
refresh();
