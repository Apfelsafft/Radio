/* Yapaia Beat web UI – works behind Home Assistant ingress (relative URLs only). */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let S = null; // last status
let stations = [];
let band = "";
let editId = null;

const fmtFreq = (f) => (f == null ? "" : `${Number(f).toFixed(f * 100 % 10 ? 2 : 1).replace(".", ",")} MHz`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, body, method) {
  const opts = { method: method || (body === undefined ? "GET" : "POST"), headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) { toast(data.error || `Fehler ${r.status}`); throw new Error(data.error); }
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 3500);
}

function sub(st) {
  if (!st) return "";
  if (st.band === "fm") {
    const extra = st.frequencies && st.frequencies.length > 1 ? ` (+${st.frequencies.length - 1})` : "";
    return `UKW ${fmtFreq(st.frequency)}${extra}`;
  }
  return `DAB+ ${st.channel || ""}${st.ensemble ? " · " + st.ensemble : ""}`;
}

/* ------------------------------------------------------------------ websocket */
function connect() {
  const url = new URL("api/ws", location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(url);
  ws.onopen = () => { $("#conn").textContent = "verbunden"; $("#conn").className = "chip ok"; };
  ws.onmessage = (e) => render(JSON.parse(e.data));
  ws.onclose = () => {
    $("#conn").textContent = "getrennt"; $("#conn").className = "chip warn";
    setTimeout(connect, 2000);
  };
}

/* ------------------------------------------------------------------ now playing */
let lastText = "", lastLogo = "", lastSlide = null, lastFavKey = "";
function render(s) {
  const prevCount = S ? S.station_count : null;
  S = s;
  // stand-alone page (no player in the Home Assistant window): follow stop /
  // start / station changes at once instead of playing out the buffer
  if (!HOST) localPlayer.sync(["playing", "tuning", "following"].includes(s.state), s.station && s.station.id);
  const st = s.station;
  const states = { idle: "Bereit", tuning: "Stimme ab …", playing: "Läuft", scanning: "Suchlauf", following: "Senderverfolgung", standby: "Standby", error: "Fehler" };
  $("#now-state").textContent = states[s.state] || s.state;
  $("#now-name").textContent = st ? st.name : "Kein Sender";
  const meta = [];
  if (s.band === "fm" && s.frequency) meta.push("UKW " + fmtFreq(s.frequency));
  if (s.band === "dab" && s.channel) meta.push("DAB+ Kanal " + s.channel);
  if (s.ensemble) meta.push(s.ensemble);
  if (s.rds && s.rds.pi) meta.push("PI " + s.rds.pi.replace("0x", "").toUpperCase());
  if (s.pty && s.pty !== "No PTY" && s.pty !== "None") meta.push(s.pty);
  if (!s.playing && st) meta.push(sub(st));
  $("#now-meta").textContent = meta.join(" · ");

  let text = s.error ? "⚠ " + s.error : s.radiotext || (s.rds && s.rds.ps) || (s.playing ? "" : "Wähle einen Sender aus deinen Favoriten oder starte einen Suchlauf.");
  if (s.state === "scanning") text = s.scan.message || "Suchlauf …";
  if (text !== lastText) {
    lastText = text;
    const span = $("#now-text");
    span.textContent = text || " ";
    span.classList.remove("scroll");
    requestAnimationFrame(() => {
      if (span.scrollWidth > span.parentElement.clientWidth) {
        span.style.setProperty("--dur", `${Math.max(8, text.length / 4)}s`);
        span.classList.add("scroll");
      }
    });
  }
  $("#now-song").textContent = s.title ? (s.artist ? `${s.artist} – ${s.title}` : s.title) : "";

  const logo = st ? st.logo_url : "api/logo/current";
  if (logo !== lastLogo) { $("#now-logo").src = logo; lastLogo = logo; }
  if (s.band === "dab" && s.slide_version) {
    if (s.slide_version !== lastSlide) { lastSlide = s.slide_version; $("#now-slide").src = `api/slide?v=${s.slide_version}`; }
    $("#now-slide").hidden = false;
  } else { $("#now-slide").hidden = true; lastSlide = null; }
  $("#now-slide").onerror = () => ($("#now-slide").hidden = true);
  if (!$("#zoom").hidden && lastSlide) $("#zoom img").src = $("#now-slide").src;

  const sig = s.playing && s.signal != null ? s.signal : null;
  $$("#bars i").forEach((b, i) => b.classList.toggle("on", sig != null && sig > i * 20 + 5));
  $("#bars").classList.toggle("weak", sig != null && sig < 35);
  $("#signal-text").textContent = sig == null ? "–" : `${Math.round(sig)} %${s.snr != null ? ` · ${Number(s.snr).toFixed(0)} dB` : ""}`;
  $("#stereo").hidden = !(s.playing && s.stereo);
  $("#tp").hidden = !(s.rds && s.rds.tp);
  $("#follow-msg").textContent = s.follow && s.follow.message ? s.follow.message : "";

  $("#play-icon").innerHTML = s.playing ? '<path d="M6 6h12v12H6z"/>' : '<path d="M8 5v14l11-7z"/>';
  $("#btn-fav").classList.toggle("active", !!(st && st.favorite));
  $$(".fm-only").forEach((b) => (b.hidden = s.band === "dab"));
  renderOutput();
  updateMediaSession();
  $("#mute-path").setAttribute("d", s.muted
    ? "M16.5 12A4.5 4.5 0 0 0 14 8v2.2l2.5 2.5V12zM19 12a7 7 0 0 1-.6 2.8l1.5 1.5A8.9 8.9 0 0 0 21 12a9 9 0 0 0-7-8.8v2.1A7 7 0 0 1 19 12zM4.3 3 3 4.3 7.7 9H3v6h4l5 5v-6.7l4.3 4.3a7 7 0 0 1-2.3 1.2v2.1a9 9 0 0 0 3.7-1.8l2 2L21 19.7l-9-9zM12 4 9.9 6.1 12 8.2V4z"
    : "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4z");
  $("#follow").checked = s.auto_follow;

  // scan tab
  $("#scan-bar").style.width = `${s.scan.running || s.scan.message ? s.scan.progress : 0}%`;
  $("#scan-msg").textContent = s.scan.message || "";
  $("#scan-cancel").hidden = !s.scan.running;
  $$("[data-scan]").forEach((b) => (b.disabled = s.scan.running));
  $("#stream-info").innerHTML = `Lokale Wiedergabe über Home Assistant Audio: <b>${s.local_audio ? "aktiv" : "aus"}</b> · MP3-Stream: <code>/stream.mp3</code> (${s.stream_clients} Hörer)`;

  const favKey = JSON.stringify(s.favorites.map((f) => [f.id, f.name, f.logo_url])) + (s.active_favorite || "");
  if (favKey !== lastFavKey) { lastFavKey = favKey; renderFavorites(); }
  if (prevCount !== null && prevCount !== s.station_count) loadStations();
  else markPlaying();
}

/* Favourites are split into pages that fit the free space below the player
 * (no page scrolling); swipe horizontally or tap the dots to switch pages. */
let favPage = 0;
function favLayout() {
  const box = $("#fav-grid");
  const width = box.clientWidth || 600;
  const top = box.getBoundingClientRect().top + window.scrollY;
  const avail = Math.max(170, window.innerHeight - top - 56); // leave room for dots
  const gap = 12;
  const minTile = width < 500 ? 104 : 132;
  const cols = Math.max(1, Math.floor((width + gap) / (minTile + gap)));
  const colW = (width - gap * (cols - 1)) / cols;
  const text = 58; // name + band + padding
  const rows = Math.max(1, Math.floor((avail + gap) / (Math.min(colW, 150) + text + gap)));
  const rowH = (avail - gap * (rows - 1)) / rows;
  const img = Math.max(56, Math.min(colW - 24, rowH - text, 150));
  return { cols, rows, img, per: cols * rows };
}

function renderFavorites() {
  const box = $("#fav-grid");
  const favs = S.favorites;
  $("#fav-empty").hidden = favs.length > 0;
  if (!favs.length) { box.innerHTML = ""; $("#fav-dots").innerHTML = ""; return; }
  const L = favLayout();
  const pages = [];
  for (let i = 0; i < favs.length; i += L.per) pages.push(favs.slice(i, i + L.per));
  favPage = Math.min(favPage, pages.length - 1);
  box.innerHTML = pages.map((page, p) => `
    <div class="page" style="grid-template-columns: repeat(${L.cols}, 1fr); --img: ${L.img}px">
      ${page.map((f, j) => {
        const i = p * L.per + j;
        return `
        <div class="tile ${S.active_favorite === f.id ? "playing" : ""}" data-id="${esc(f.id)}">
          ${i > 0 ? `<button class="move l" data-move="-1" title="nach vorne">‹</button>` : ""}
          ${i < favs.length - 1 ? `<button class="move r" data-move="1" title="nach hinten">›</button>` : ""}
          <img src="${esc(f.logo_url)}" alt="" loading="lazy" onerror="this.onerror=null;this.src='api/logo/${esc(f.id)}?placeholder=1'">
          <div class="name">${esc(f.name)}</div>
          <div class="band">${esc(sub(f))}</div>
        </div>`;
      }).join("")}
    </div>`).join("");
  $("#fav-dots").innerHTML = pages.length > 1
    ? pages.map((_, p) => `<button data-page="${p}" class="${p === favPage ? "active" : ""}" aria-label="Seite ${p + 1}"></button>`).join("")
    : "";
  box.scrollLeft = favPage * box.clientWidth;
}

$("#fav-grid").addEventListener("scroll", () => {
  const box = $("#fav-grid");
  const p = Math.round(box.scrollLeft / Math.max(1, box.clientWidth));
  if (p !== favPage) {
    favPage = p;
    $$("#fav-dots button").forEach((d, i) => d.classList.toggle("active", i === p));
  }
}, { passive: true });
$("#fav-dots").addEventListener("click", (e) => {
  const d = e.target.closest("[data-page]");
  if (!d) return;
  favPage = Number(d.dataset.page);
  $("#fav-grid").scrollTo({ left: favPage * $("#fav-grid").clientWidth, behavior: "smooth" });
});
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => S && renderFavorites(), 150); });

$("#fav-grid").addEventListener("click", async (e) => {
  const tile = e.target.closest(".tile");
  if (!tile) return;
  const move = e.target.closest("[data-move]");
  if (move) {
    e.stopPropagation();
    const ids = S.favorites.map((f) => f.id);
    const i = ids.indexOf(tile.dataset.id), j = i + Number(move.dataset.move);
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await api("api/favorites", { order: ids });
    return;
  }
  // immediate feedback while the receiver retunes
  $$("#fav-grid .tile").forEach((t) => t.classList.toggle("pending", t === tile));
  try { await api("api/play", { id: tile.dataset.id }); } finally { tile.classList.remove("pending"); }
});

/* ------------------------------------------------------------------ stations list */
async function loadStations() {
  const q = $("#search").value.trim();
  const params = new URLSearchParams({ q, band });
  stations = await fetch(`api/stations?${params}`).then((r) => r.json());
  const list = $("#station-list");
  list.innerHTML = stations.map((st) => `
    <li data-id="${esc(st.id)}" class="${st.available ? "" : "unavailable"}">
      <img src="${esc(st.logo_url)}" alt="" loading="lazy">
      <div class="txt" data-play><b>${esc(st.name)}</b><small>${esc(sub(st))}${st.pty ? " · " + esc(st.pty) : ""}${st.available ? "" : " · zuletzt nicht empfangen"}</small></div>
      <button class="star ${st.favorite ? "on" : ""}" data-fav title="Favorit">${st.favorite ? "★" : "☆"}</button>
      <button class="edit" data-edit title="Bearbeiten">✎</button>
    </li>`).join("");
  $("#stations-empty").hidden = stations.length > 0;
  const f = parseFloat(q.replace(",", "."));
  const direct = $("#direct-tune");
  if (band !== "dab" && f >= 87.5 && f <= 108) {
    direct.hidden = false;
    direct.innerHTML = `<button class="primary" id="tune-direct">▶ ${fmtFreq(f)} direkt einstellen</button>`;
    $("#tune-direct").onclick = () => api("api/play", { frequency: f });
  } else direct.hidden = true;
  markPlaying();
}

function markPlaying() {
  const cur = S && S.station ? S.station.id : null;
  $$("#station-list li").forEach((li) => li.classList.toggle("playing", li.dataset.id === cur));
}

$("#station-list").addEventListener("click", async (e) => {
  const li = e.target.closest("li");
  if (!li) return;
  const st = stations.find((s) => s.id === li.dataset.id);
  if (e.target.closest("[data-fav]")) {
    await api("api/favorites", { id: st.id, favorite: !st.favorite });
    loadStations();
  } else if (e.target.closest("[data-edit]")) openEdit(st);
  else if (e.target.closest("[data-play]")) await api("api/play", { id: st.id });
});

let searchTimer;
$("#search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadStations, 200); });
$$("#band-filter button").forEach((b) => b.addEventListener("click", () => {
  $$("#band-filter button").forEach((x) => x.classList.toggle("active", x === b));
  band = b.dataset.band; loadStations();
}));

/* ------------------------------------------------------------------ edit dialog */
function openEdit(st) {
  editId = st.id;
  $("#edit-name").value = st.name;
  $("#edit-logo").src = st.logo_url;
  $("#edit-info").textContent = [sub(st), st.pi && "PI " + st.pi, st.sid && "SId " + st.sid, st.original_name && `Original: ${st.original_name}`].filter(Boolean).join(" · ");
  $("#edit").showModal();
}
async function refreshEdit() {
  await loadStations();
  const st = stations.find((s) => s.id === editId);
  if (st) $("#edit-logo").src = st.logo_url + "&t=" + Date.now();
}
$("#edit-save").addEventListener("click", async () => { await api(`api/stations/${editId}`, { name: $("#edit-name").value }); loadStations(); });
$("#edit-file").addEventListener("change", async (e) => {
  const fd = new FormData(); fd.append("file", e.target.files[0]);
  await api(`api/stations/${editId}/logo`, fd); e.target.value = ""; refreshEdit(); toast("Logo gespeichert");
});
$("#edit-refresh").addEventListener("click", async () => {
  const r = await api(`api/stations/${editId}/logo/refresh`, {}); toast(r.found ? "Logo gefunden" : "Kein Logo gefunden"); refreshEdit();
});
$("#edit-reset").addEventListener("click", async () => { await api(`api/stations/${editId}/logo`, undefined, "DELETE"); refreshEdit(); });
$("#edit-delete").addEventListener("click", async () => {
  if (!confirm("Sender wirklich löschen?")) return;
  await api(`api/stations/${editId}`, undefined, "DELETE"); $("#edit").close(); loadStations();
});

/* ------------------------------------------------------------------ controls */
$("#btn-play").onclick = () => {
  if (!(S && S.playing) && player.wanted) player.start(); // keep it inside the user gesture (iOS)
  api(S && S.playing ? "api/stop" : "api/play", {});
};
$("#btn-next").onclick = () => api("api/next", {});
$("#btn-prev").onclick = () => api("api/previous", {});
$("#btn-seek-up").onclick = () => api("api/seek", { direction: "up" });
$("#btn-seek-down").onclick = () => api("api/seek", { direction: "down" });
$("#btn-fav").onclick = () => S && S.station && api("api/favorites", { id: S.station.id, favorite: !S.station.favorite }).then(loadStations);
$("#btn-mute").onclick = () => api("api/volume", { muted: !(S && S.muted) });
$("#volume").addEventListener("input", (e) => { $("#volume-text").textContent = e.target.value; });
$("#volume").addEventListener("change", (e) => {
  if (browserOnly()) { player.setVolume(Number(e.target.value)); renderOutput(); }
  else api("api/volume", { volume: Number(e.target.value) });
});
$("#follow").addEventListener("change", (e) => api("api/settings", { auto_follow: e.target.checked }));
$$("[data-scan]").forEach((b) => (b.onclick = () => api("api/scan", { band: b.dataset.scan })));
$("#scan-cancel").onclick = () => api("api/scan/cancel", {});
$$(".tabs button").forEach((b) => b.addEventListener("click", () => {
  $$(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$(".tab").forEach((t) => (t.hidden = t.id !== `tab-${b.dataset.tab}`));
  if (b.dataset.tab === "stations") loadStations();
  if (b.dataset.tab === "favorites" && S) renderFavorites();
}));

/* ------------------------------------------------------------------ browser playback
 * The browser plays the add-on's MP3 stream (through HA ingress, so no extra
 * port is needed).  The choice is stored per device. */
const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const store = {
  get: (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
const localPlayer = {
  audio: null,
  wanted: store.get("yapaia.browserAudio", false),
  blocked: false,
  volume: store.get("yapaia.browserVolume", 80),
  _retry: null,
  _eigen: 0, // when we started/stopped the <audio> ourselves
  _ruhe: false, // the radio is stopped – no sound wanted right now
  _lage: null, // last seen { aktiv, station } of the radio
  _ansage: 0,
  el() {
    if (!this.audio) {
      const a = (this.audio = new Audio());
      a.preload = "none";
      const again = () => {
        if (!this.wanted) return;
        clearTimeout(this._retry);
        this._retry = setTimeout(() => this.start(), 2000);
      };
      a.addEventListener("error", again);
      a.addEventListener("ended", again);
      // iPad/iPhone pause our <audio> when another app or tab speaks (e.g.
      // Yapaia Go's voice) and do not resume it.  Bring the sound back –
      // unless we paused it ourselves.
      a.addEventListener("pause", () => {
        if (!this.wanted || this._ruhe || !a.src || Date.now() - this._eigen < 1500 || this._spricht()) return;
        clearTimeout(this._retry);
        this._retry = setTimeout(() => { if (this.wanted && !this._ruhe && a.paused && !this._spricht()) this.start(); }, 1000);
      });
      a.addEventListener("playing", () => { this.blocked = false; renderOutput(); });
    }
    return this.audio;
  },
  start() {
    const a = this.el();
    this._eigen = Date.now();
    this._ruhe = false;
    a.src = `stream.mp3?t=${Date.now()}`;
    a.volume = this.volume / 100;
    const p = a.play();
    if (p && p.catch) p.catch(() => { this.blocked = true; renderOutput(); });
  },
  stop() {
    clearTimeout(this._retry);
    this._eigen = Date.now();
    if (this.audio) { this.audio.pause(); this.audio.removeAttribute("src"); this.audio.load(); }
  },
  /* The radio itself was stopped / started / switched (seen in its state).
   * The browser keeps several seconds of the stream in its buffer – without
   * this, "stop" played on for ~5 s and a new station began only after the
   * old buffer had run out.  So: stop at once, and (re)connect at the live
   * edge when the radio starts or the station changes. */
  _spricht() { return this._ansage > 0 && Date.now() - this._ansage < 30000; },
  sync(aktiv, station) {
    if (!this.wanted) { this._lage = null; return; }
    const vorher = this._lage;
    this._lage = { aktiv, station };
    if (!vorher) return;
    if (vorher.aktiv && !aktiv) { this.stop(); this._ruhe = true; return; }
    if (aktiv && (!vorher.aktiv || (station && station !== vorher.station))) this.start();
  },
  setWanted(on) {
    this.wanted = on; store.set("yapaia.browserAudio", on);
    if (on) this.start(); else { this.blocked = false; this.stop(); }
  },
  setVolume(v) {
    this.volume = v; store.set("yapaia.browserVolume", v);
    if (this.audio) this.audio.volume = v / 100;
  },
  get playing() { return !!(this.audio && !this.audio.paused && this.audio.src); },
};

/* Inside Home Assistant this page is an iframe that is thrown away when you
 * open another dashboard – and the sound with it.  The Yapaia Beat
 * integration loads a player into the main Home Assistant window (the same
 * one the radio card uses); if it is there, we let it play, so the radio keeps
 * running on every dashboard. */
function findHost() {
  try {
    if (window.parent !== window && window.parent.YapaiaBeatPlayer) return window.parent.YapaiaBeatPlayer;
  } catch (e) { /* not Home Assistant (other origin) */ }
  return null;
}
let HOST = findHost();
function connectHost() {
  HOST.ensure(); // sign the stream URL now so a tap can start it right away
  const onHost = () => renderOutput();
  HOST._listeners.add(onHost);
  window.addEventListener("pagehide", () => HOST._listeners.delete(onHost));
}
if (HOST) connectHost();
else {
  // The integration loads the player into every dashboard.  If it is missing
  // in this Home Assistant window (e.g. the page was loaded before the
  // integration), load it ourselves – otherwise the sound would stop as soon
  // as you leave this page.
  try {
    const doc = window.parent !== window ? window.parent.document : null;
    if (doc && !doc.querySelector("script[data-yapaia-beat-player]")) {
      const sc = doc.createElement("script");
      sc.type = "module";
      sc.src = "/yapaia_beat/yapaia-beat-card.js";
      sc.dataset.yapaiaBeatPlayer = "1";
      sc.onload = () => {
        const h = findHost();
        if (!h) return;
        const lief = localPlayer.wanted && localPlayer.playing;
        if (localPlayer.wanted) { localPlayer.stop(); localPlayer.wanted = false; }
        HOST = h;
        connectHost();
        if (lief) HOST.setWanted(true); // may need a tap (browser rules) – the hint says so
        renderOutput();
      };
      doc.head.appendChild(sc);
    }
  } catch (e) { /* other origin: stand-alone page */ }
}
const player = {
  get wanted() { return HOST ? HOST.wanted : localPlayer.wanted; },
  get blocked() { return HOST ? HOST.blocked : localPlayer.blocked; },
  get volume() { return HOST ? HOST.volume : localPlayer.volume; },
  get playing() { return HOST ? HOST.playing : localPlayer.playing; },
  get audio() { return HOST ? HOST.audio : localPlayer.audio; },
  start() { if (HOST) HOST.start(); else localPlayer.start(); },
  stop() { if (HOST) HOST.stop(); else localPlayer.stop(); },
  setWanted(on) {
    if (!HOST) { localPlayer.setWanted(on); return; }
    if (on && HOST.wanted && HOST.playing) return; // already playing, no gap
    HOST.setWanted(on);
  },
  setVolume(v) { if (HOST) HOST.setVolume(v); else localPlayer.setVolume(v); },
};

function browserOnly() { return player.wanted && !(S && (S.speaker || (S.local_output && S.local_audio))); }

/* Output picker (like "Connect to a device" in Spotify): Mini-PC speakers,
 * this browser, both – or any media player Home Assistant knows (Sonos,
 * Chromecast, Music Assistant …); the integration sends the stream there. */
function outputMode() {
  if (!S) return "local";
  if (S.speaker) return "speaker:" + S.speaker;
  const local = S.local_audio && S.local_output;
  return local && player.wanted ? "both" : player.wanted ? "browser" : local ? "local" : "none";
}

function speakerName(id) {
  const p = (S.players || []).find((x) => x.entity_id === id);
  return p ? p.name : id;
}

function renderOutput() {
  if (!S) return;
  const mode = outputMode();
  const labels = {
    local: ["🖥", "Mini-PC"], browser: ["📱", "Dieses Gerät"], both: ["🖥", "Mini-PC + dieses Gerät"], none: ["🔇", "Keine Ausgabe"],
  };
  const [icon, label] = mode.startsWith("speaker:") ? ["🔊", speakerName(S.speaker) + (player.wanted ? " + dieses Gerät" : "")] : labels[mode];
  $("#out-icon").textContent = icon;
  $("#out-label").textContent = label;
  $("#out-btn").classList.toggle("casting", !!S.speaker && !S.speaker_error);
  if (!$("#out-menu").hidden) renderOutMenu();
  $("#browser-unlock").hidden = !(player.wanted && player.blocked);
  let hint = "", err = false;
  if (S.speaker_error) { hint = "⚠ " + S.speaker_error; err = true; }
  else if (player.wanted && player.blocked) hint = "Der Browser startet den Ton erst nach einem Tippen – einfach irgendwo tippen";
  else if (!S.local_audio && mode === "none") hint = "Mini-PC-Ausgabe nicht verfügbar (Audio im Add-on prüfen)";
  else if (player.wanted && !HOST && window.parent !== window) hint = "Ton läuft nur auf dieser Seite – beim Wechsel zu einem anderen Dashboard hört er auf. Home Assistant einmal neu laden.";
  else if (player.wanted && IS_IOS) hint = (HOST ? "Ton läuft auch auf anderen Dashboards weiter · " : "") + "Lautstärke am iPad/iPhone mit den Tasten regeln";
  else if (player.wanted) hint = HOST ? "Ton läuft im Home-Assistant-Fenster weiter, auch auf anderen Dashboards (ca. 2–4 s verzögert)" : "Wiedergabe ca. 2–4 s verzögert";
  $("#out-hint").textContent = hint;
  $("#out-hint").classList.toggle("err", err);
  const vol = browserOnly() ? player.volume : S.volume;
  if (document.activeElement !== $("#volume")) $("#volume").value = vol;
  $("#volume-text").textContent = !browserOnly() && S.muted ? "stumm" : vol;
}

function renderOutMenu() {
  const mode = outputMode();
  const item = (value, icon, label, opts = {}) => `
    <button role="option" data-out="${esc(value)}" class="${mode === value ? "active" : ""}" ${opts.disabled ? "disabled" : ""}>
      <span class="ico">${icon}</span><span class="lbl">${esc(label)}${opts.small ? `<br><small>${esc(opts.small)}</small>` : ""}</span>
    </button>`;
  const noLocal = !S.local_audio;
  const players = S.players || [];
  $("#out-menu").innerHTML = `
    <div class="grp">Hier &amp; am Mini-PC</div>
    ${item("browser", "📱", "Dieses Gerät", { small: "Browser, iPad, Autoradio …" })}
    ${item("local", "🖥", "Mini-PC", { disabled: noLocal, small: noLocal ? "Audio im Add-on nicht verfügbar" : "Lautsprecher am Home-Assistant-Rechner" })}
    ${item("both", "🖥", "Mini-PC + dieses Gerät", { disabled: noLocal })}
    <div class="grp">Home Assistant Lautsprecher</div>
    ${players.length
      ? players.map((p) => item("speaker:" + p.entity_id, "🔊", p.name, { small: p.entity_id })).join("")
      : `<div class="none">Keine weiteren Media Player gefunden. Sie erscheinen hier, sobald die Yapaia-Beat-Integration in Home Assistant eingerichtet ist.</div>`}
    ${S.local_audio ? "" : item("none", "🔇", "Keine Ausgabe")}`;
}

$("#out-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  const menu = $("#out-menu");
  menu.hidden = !menu.hidden;
  if (!menu.hidden) renderOutMenu();
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".out-pick")) $("#out-menu").hidden = true;
});
$("#out-menu").addEventListener("click", (e) => {
  const b = e.target.closest("[data-out]");
  if (!b || b.disabled) return;
  const out = b.dataset.out;
  const speaker = out.startsWith("speaker:") ? out.slice(8) : null;
  // the browser starts playing right here, inside the tap (needed on iOS)
  player.setWanted(out === "browser" || out === "both");
  api("api/settings", { local_output: out === "local" || out === "both", speaker });
  $("#out-menu").hidden = true;
  renderOutput();
});
$("#browser-unlock").onclick = () => player.start();

/* DAB+ slideshow: tap to enlarge, tap again (or Esc) to close */
$("#now-slide").addEventListener("click", () => { $("#zoom img").src = $("#now-slide").src; $("#zoom").hidden = false; });
$("#zoom").addEventListener("click", () => ($("#zoom").hidden = true));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#zoom").hidden = true; });

/* Browsers only allow sound after the user touched the page.  When the
 * page was opened with "this device" selected, the first tap anywhere
 * starts the sound – no extra button needed. */
const unlock = () => { if (player.wanted && player.blocked) player.start(); };
["click", "touchend", "keydown"].forEach((ev) => document.addEventListener(ev, unlock, { capture: true, passive: true }));

/* lock screen / car display: station, logo and buttons via the Media Session API */
function updateMediaSession() {
  if (HOST || !("mediaSession" in navigator) || !S || !player.wanted) return; // HOST does it itself
  const st = S.station;
  const title = S.title ? (S.artist ? `${S.artist} – ${S.title}` : S.title) : (S.radiotext || (st && st.name) || "Yapaia Beat");
  const key = [title, st && st.id, st && st.logo_url].join("|");
  if (key === updateMediaSession.key) return;
  updateMediaSession.key = key;
  navigator.mediaSession.metadata = new MediaMetadata({
    title,
    artist: st ? st.name : "Yapaia Beat",
    album: "Yapaia Beat",
    artwork: st ? [{ src: new URL(st.logo_url, location.href).href, sizes: "256x256" }] : [],
  });
}
if (!HOST && "mediaSession" in navigator) {
  const ms = navigator.mediaSession;
  const safe = (fn) => { try { fn(); } catch (e) { /* unsupported action */ } };
  safe(() => ms.setActionHandler("play", () => { player.start(); api("api/play", {}); }));
  safe(() => ms.setActionHandler("pause", () => api("api/stop", {})));
  safe(() => ms.setActionHandler("stop", () => api("api/stop", {})));
  safe(() => ms.setActionHandler("nexttrack", () => api("api/next", {})));
  safe(() => ms.setActionHandler("previoustrack", () => api("api/previous", {})));
}

if (player.wanted && !player.playing) player.start(); // may be blocked until the first tap anywhere

connect();
loadStations();
