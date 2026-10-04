/*
 * Yapaia Beat card – a radio style Lovelace card for the Yapaia Beat add-on.
 *
 *   type: custom:yapaia-beat-card
 *   entity: media_player.yapaia_beat
 *   follow_entity: switch.yapaia_beat_auto_follow   # optional
 *   style: retro | modern                            # optional, default retro
 *   max_presets: 12                                  # optional, 0 hides presets
 *   show_slide: true                                 # optional, DAB+ slideshow
 *   show_output: true                                # optional, output picker (Mini-PC / this device / HA speakers)
 */

const CARD_VERSION = "1.10.1";
const STREAM_PATH = "/api/yapaia_beat/stream";
const SENDSPIN_URL = "/yapaia_beat/sendspin.js";

const ICONS = {
  speaker: "M17 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm-5 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm0 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm0-6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  device: "M17 1H7a2 2 0 0 0-2 2v18a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2zm0 18H7V5h10v14zm-7-6.5 5-3.5-5-3.5v7z",
  prev: "M6 6h2v12H6zm3.5 6 8.5 6V6z",
  next: "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
  play: "M8 5v14l11-7z",
  stop: "M6 6h12v12H6z",
  volDown: "M5 9v6h4l5 5V4L9 9H5zm13.5 3A4.5 4.5 0 0 0 16 8v8a4.5 4.5 0 0 0 2.5-4z",
  mute: "M16.5 12A4.5 4.5 0 0 0 14 8v2.2l2.5 2.5V12zM19 12a7 7 0 0 1-.6 2.8l1.5 1.5A8.9 8.9 0 0 0 21 12a9 9 0 0 0-7-8.8v2.1A7 7 0 0 1 19 12zM4.3 3 3 4.3 7.7 9H3v6h4l5 5v-6.7l4.3 4.3a7 7 0 0 1-2.3 1.2v2.1a9 9 0 0 0 3.7-1.8l2 2L21 19.7l-9-9zM12 4 9.9 6.1 12 8.2V4z",
  follow: "M18 15c-1.3 0-2.4.8-2.8 2H9.5a2.5 2.5 0 0 1 0-5h5a4.5 4.5 0 0 0 0-9H8.8A3 3 0 1 0 6 7c1.3 0 2.4-.8 2.8-2h5.7a2.5 2.5 0 0 1 0 5h-5a4.5 4.5 0 0 0 0 9h5.7A3 3 0 1 0 18 15z",
  star: "m12 17.3 6.2 3.7-1.6-7L22 9.2l-7.2-.6L12 2 9.2 8.6 2 9.2 7.5 14l-1.7 7z",
  starOff: "m22 9.2-7.2-.6L12 2 9.2 8.6 2 9.2 7.5 14l-1.7 7 6.2-3.7 6.2 3.7-1.6-7L22 9.2zM12 15.4l-3.8 2.3 1-4.3-3.3-2.9 4.4-.4L12 6.1l1.7 4 4.4.4-3.3 2.9 1 4.3L12 15.4z",
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const svg = (d) => `<svg viewBox="0 0 24 24"><path d="${d}"/></svg>`;

/*
 * Plays the radio in this browser: the integration proxies the add-on's MP3
 * stream at /api/yapaia_beat/stream; <audio> can't send auth headers, so we
 * use a signed URL.  One player per browser tab, shared by all cards and by
 * the add-on page in the side bar (which runs in an iframe and would lose its
 * sound when you switch to another dashboard); the choice is remembered per
 * device.
 */
const BrowserPlayer = {
  audio: null,
  url: null,
  signedAt: 0,
  wanted: (() => { try { return localStorage.getItem("yapaia-beat.browser") === "1"; } catch (e) { return false; } })(),
  volume: (() => { try { return Number(localStorage.getItem("yapaia-beat.volume") || 80); } catch (e) { return 80; } })(),
  blocked: false,
  _retry: null,
  _eigen: 0, // when we started/stopped the <audio> ourselves
  _ruhigBis: 0, // no catching up before this (after a stall)
  _ruhe: false, // the radio is stopped – no sound wanted right now
  _lage: null, // last seen { aktiv, station } of the radio
  _ansage: 0, // another Yapaia module speaks in this browser since …
  _signing: false,
  _listeners: new Set(),

  async prepare(hass, path) {
    // refresh the signed URL well before it expires (24 h)
    if (!path || this._signing || (this.url && Date.now() - this.signedAt < 6 * 3600 * 1000)) return;
    this._signing = true;
    try {
      const res = await hass.callWS({ type: "auth/sign_path", path, expires: 24 * 3600 });
      this.url = res.path;
      this.signedAt = Date.now();
      if (this.wanted && !this.playing) this.start();
    } catch (err) {
      console.warn("Yapaia Beat: could not sign stream URL", err);
    } finally {
      this._signing = false;
    }
  },
  _hassEl() {
    const el = document.querySelector("home-assistant");
    return el && el.hass;
  },
  /* get a signed stream URL without a card on the screen (add-on page) */
  ensure() {
    const hass = this._hassEl() || this._hass;
    if (hass) this.prepare(hass, STREAM_PATH);
  },
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
      // a stall: stop catching up – if it happened while speeding, for a minute
      const stockt = () => {
        this._ruhigBis = Date.now() + (a.playbackRate !== 1 ? 60000 : 10000);
        a.playbackRate = 1;
      };
      a.addEventListener("waiting", stockt);
      a.addEventListener("stalled", stockt);
      a.addEventListener("ended", again);
      // iPad/iPhone pause our <audio> when another app or tab speaks (e.g.
      // Yapaia Go's voice) and do not resume it.  Bring the sound back –
      // unless we paused it ourselves.
      a.addEventListener("pause", () => {
        if (!this.wanted || this._ruhe || !a.src || Date.now() - this._eigen < 1500 || this._spricht()) return;
        clearTimeout(this._retry);
        this._retry = setTimeout(() => { if (this.wanted && !this._ruhe && a.paused && !this._spricht()) this.start(); }, 1000);
      });
      a.addEventListener("playing", () => { this.blocked = false; this._notify(); });
    }
    return this.audio;
  },
  start() {
    if (!this.url) { this.ensure(); return; } // starts once the URL is signed
    const a = this.el();
    this._eigen = Date.now();
    this._ruhe = false;
    // no cache buster: extra query parameters would invalidate the signature
    a.removeAttribute("src");
    a.load();
    a.src = this.url;
    a.volume = this.volume / 100;
    const p = a.play();
    if (p && p.catch) p.catch(() => { this.blocked = true; this._notify(); });
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
  /* Another Yapaia module (Yapaia Go) speaks in this browser.  iPad/iPhone
   * pause our sound for that – don't fight it, and resume exactly when it
   * is done (Yapaia Go calls ansageEndet when its utterance ends). */
  ansageBeginnt() { this._ansage = Date.now(); },
  ansageEndet() {
    this._ansage = 0;
    if (this.wanted && !this._ruhe && this.audio && this.audio.paused) {
      clearTimeout(this._retry);
      this._retry = setTimeout(() => this.start(), 300);
    }
  },
  /* Live radio: the browser keeps several seconds of the stream in stock,
   * and every announcement mixed in by Beat came that much later (~6 s).
   * Catch up gently: never seek (1.6.3 did – the stock ran dry and the sound
   * broke up), only play 5 % faster (pitch kept) while more than 2 s are in
   * stock, back to normal below 1 s.  Hands off while starting, after any
   * stall, and for a minute if a stall happened while speeding. */
  _aufholen() {
    const a = this.audio;
    if (!a || !a.buffered || !a.buffered.length) return;
    const jetzt = Date.now();
    const normal = () => { if (a.playbackRate !== 1) a.playbackRate = 1; };
    if (a.paused || a.readyState < 3 || jetzt - this._eigen < 8000 || jetzt < this._ruhigBis) { normal(); return; }
    const lag = a.buffered.end(a.buffered.length - 1) - a.currentTime;
    if (lag > 2 && a.playbackRate === 1) { a.preservesPitch = true; a.playbackRate = 1.05; }
    else if (lag < 1) normal();
  },
  _spricht() { return this._ansage > 0 && Date.now() - this._ansage < 30000; },
  _syncState(st) {
    this.sync(st.state === "playing" || st.state === "buffering", st.attributes.station_id || st.attributes.station_name);
  },
  sync(aktiv, station) {
    if (!this.wanted) { this._lage = null; return; }
    const vorher = this._lage;
    this._lage = { aktiv, station };
    if (!vorher) return;
    if (vorher.aktiv && !aktiv) { this.stop(); this._ruhe = true; return; }
    if (aktiv && (!vorher.aktiv || (station && station !== vorher.station))) this.start();
  },
  setWanted(on) {
    this.wanted = on;
    try { localStorage.setItem("yapaia-beat.browser", on ? "1" : "0"); } catch (e) { /* ignore */ }
    if (on) { this._watch(); if (!this.playing) this.start(); } else { this.blocked = false; this.stop(); }
  },
  /* keep the lock screen / car display up to date on every dashboard */
  _watch() {
    if (this._watchTimer) return;
    this._watchTimer = setInterval(() => {
      const hass = this._hassEl();
      if (!this.wanted) return;
      this._aufholen();
      if (!hass) return;
      const id = this._entity || Object.keys(hass.states).find((e) => e.startsWith("media_player.yapaia_beat"));
      const st = id && hass.states[id];
      if (st) { this._entity = id; this.updateSession(st.attributes, hass); this._syncState(st); }
    }, 1000);
  },
  setVolume(v) {
    this.volume = v;
    try { localStorage.setItem("yapaia-beat.volume", String(v)); } catch (e) { /* ignore */ }
    if (this.audio) this.audio.volume = v / 100;
  },
  get playing() { return !!(this.audio && !this.audio.paused && this.audio.src); },
  _notify() {
    // listeners of a closed add-on page may be dead – drop them
    this._listeners.forEach((fn) => { try { fn(); } catch (e) { this._listeners.delete(fn); } });
  },
  updateSession(a, hass) {
    // station + logo on the lock screen / car display (Android, iOS)
    if (!("mediaSession" in navigator) || !this.wanted) return;
    const title = a.media_title || a.station_name || "Yapaia Beat";
    const key = [title, a.station_name, a.logo].join("|");
    if (key === this._sessionKey) return;
    this._sessionKey = key;
    this._hass = hass;
    navigator.mediaSession.metadata = new MediaMetadata({
      title,
      artist: a.media_artist || a.station_name || "",
      album: "Yapaia Beat",
      artwork: a.logo ? [{ src: new URL(a.logo, location.origin).href, sizes: "256x256" }] : [],
    });
    if (!this._handlers) {
      this._handlers = true;
      const call = (service) => this._hass && this._hass.callService("media_player", service, { entity_id: this._entity });
      const set = (action, fn) => { try { navigator.mediaSession.setActionHandler(action, fn); } catch (e) { /* unsupported */ } };
      set("play", () => { this.start(); call("media_play"); });
      set("pause", () => call("media_stop"));
      set("stop", () => call("media_stop"));
      set("nexttrack", () => call("media_next_track"));
      set("previoustrack", () => call("media_previous_track"));
    }
  },
};
window.YapaiaBeatPlayer = BrowserPlayer;
if (BrowserPlayer.wanted) BrowserPlayer._watch();

/* This browser as a player of Music Assistant ("Sendspin").
 *
 * Music Assistant's own web player lives in its page and falls silent as
 * soon as you switch to another dashboard.  This one lives in the Home
 * Assistant window itself (like BrowserPlayer) and keeps playing on every
 * dashboard.  It connects through Music Assistant's ingress (no extra port,
 * no extra login: the ingress session authenticates it, exactly like Music
 * Assistant's own page) and shows up there as "Yapaia (iPad)" – a player
 * like any speaker: Yapaia Beat can play on it, and Music Assistant mixes
 * Yapaia Go's announcements in without the delay of the browser stream.
 *
 * It tells Music Assistant honestly that it is Yapaia Beat (not Music
 * Assistant's web player), so Music Assistant asks once to allow it. */
const MA_SLUGS = ["d5369777_music_assistant", "d5369777_music_assistant_beta"];
const lies = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } };
const schreib = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } };
// own keys: Music Assistant's page runs on the same origin and must keep its own identity
const SS_STORAGE = {
  getItem: (k) => lies("yapaia-beat.ss." + k, null),
  setItem: (k, v) => schreib("yapaia-beat.ss." + k, v),
};

const MaPlayer = {
  wanted: lies("yapaia-beat.ma", "0") === "1",
  // "Yapaia Browser" – it is not always an iPad (a name chosen earlier stays)
  name: lies("yapaia-beat.ma-name", "") || "Yapaia Browser",
  status: "aus", // aus | sucht | verbindet | wartet | bereit | spielt | fehler
  error: "",
  needsTap: false,
  player: null,
  _session: null,
  _secure: location.protocol === "https:",
  _timer: null,
  _starting: false,
  _listeners: new Set(),

  _hass() { const el = document.querySelector("home-assistant"); return el && el.hass; },
  async _sup(endpoint, method, data) {
    const hass = this._hass();
    if (!hass) throw new Error("Home Assistant ist noch nicht bereit.");
    const msg = { type: "supervisor/api", endpoint, method };
    if (data) msg.data = data;
    return hass.callWS(msg);
  },
  _set(status, error = "") {
    if (status === this.status && error === this.error) return;
    this.status = status;
    this.error = error;
    this._listeners.forEach((fn) => { try { fn(); } catch (e) { this._listeners.delete(fn); } });
  },
  /* Music Assistant's add-on and its ingress path */
  async _findMa() {
    let slugs = MA_SLUGS;
    try {
      // admins see all add-ons – also a Music Assistant from another repository
      const all = await this._sup("/addons", "get");
      const found = (all && all.addons || []).filter((a) => /music_assistant/.test(a.slug)).map((a) => a.slug);
      if (found.length) slugs = [...new Set([...found, ...MA_SLUGS])];
    } catch (e) { /* not an admin: try the known slugs */ }
    let stopped = null;
    for (const slug of slugs) {
      let info;
      try { info = await this._sup(`/addons/${slug}/info`, "get"); } catch (e) { continue; }
      if (info && info.ingress_url) return info.ingress_url.replace(/\/$/, "");
      if (info) stopped = info.state;
    }
    throw new Error(stopped ? `Music Assistant ist nicht gestartet (${stopped}).` : "Music Assistant (Add-on) wurde nicht gefunden.");
  },
  async _newSession() {
    const r = await this._sup("/ingress/session", "post");
    if (!r || !r.session) throw new Error("Home Assistant hat keine Ingress-Sitzung geliefert.");
    this._session = r.session;
    this._cookie();
  },
  _cookie() {
    if (this._session) document.cookie = `ingress_session=${this._session};path=/api/hassio_ingress/;SameSite=Strict${this._secure ? ";Secure" : ""}`;
  },
  /* Keep our ingress session alive.  The cookie is shared by every add-on
   * page in Home Assistant (Music Assistant's own included), so it is only
   * written when we create a session – never on every check (1.10 rewrote it
   * on every reconnect and broke Music Assistant's page with it). */
  async _keepSession() {
    if (!this._session) return;
    try { await this._sup("/ingress/validate_session", "post", { session: this._session }); }
    catch (e) { try { await this._newSession(); } catch (e2) { /* next round */ } }
  },
  /* Music Assistant turned the connection down (it closes at once, so the
   * library retries every second).  The usual cause: our ingress session was
   * created while Home Assistant was still starting, without a user – Music
   * Assistant needs one.  So: a fresh session every third try; after ten,
   * stop for five minutes instead of knocking every second. */
  _abgelehnt() {
    this._fehlversuche = (this._fehlversuche || 0) + 1;
    if (this._fehlversuche >= 10) {
      this._fehlversuche = 0;
      this._teardown();
      this._set("fehler", "Music Assistant nimmt die Anmeldung nicht an. Neuer Versuch in 5 Minuten (oder Schalter aus und wieder ein).");
      clearTimeout(this._retry);
      this._retry = setTimeout(() => { if (this.wanted) this.start(); }, 5 * 60000);
      return;
    }
    if (this._fehlversuche % 3 === 0) this._newSession().catch(() => {});
  },
  async start() {
    if (this.player || this._starting) return;
    this._starting = true;
    try {
      this._set("sucht");
      const base = await this._findMa();
      await this._newSession();
      this._set("verbindet");
      const { SendspinPlayer } = await import(`${SENDSPIN_URL}?v=${CARD_VERSION}`);
      if (!this.wanted) return;
      this.player = new SendspinPlayer({
        baseUrl: location.origin + base,
        clientName: this.name,
        productName: "Yapaia Beat",
        storage: SS_STORAGE,
        correctionMode: "quality-local", // one device, best sound
        requiredLeadTimeMs: 250,
        minBufferMs: 500,
        reconnect: {
          baseDelayMs: 2000,
          maxDelayMs: 30000,
          onReconnecting: () => this._abgelehnt(),
        },
        onStateChange: () => this._check(),
      });
      await this.player.connect();
      this._timer = setInterval(() => { this._check(); }, 1000);
      this._sessionTimer = setInterval(() => this._keepSession(), 60000);
      this._check();
    } catch (err) {
      this._set("fehler", (err && err.message) || "Keine Verbindung zu Music Assistant.");
      this._teardown();
      // try again later – Music Assistant may just be starting
      clearTimeout(this._retry);
      this._retry = setTimeout(() => { if (this.wanted) this.start(); }, 30000);
    } finally {
      this._starting = false;
    }
  },
  _check() {
    const p = this.player;
    if (!p) return;
    if (!p.isConnected) { this._seit = 0; this._set("verbindet"); return; }
    let roles = null;
    try { roles = p.core.protocolHandler.activeRoles; } catch (e) { /* internals changed */ }
    // connected for a while: the session is fine
    if (!this._seit) this._seit = Date.now();
    else if (Date.now() - this._seit > 10000) this._fehlversuche = 0;
    if (roles && roles.size === 0) { this._set("wartet"); return; } // not yet allowed in Music Assistant
    this._wache();
    this._set(p.isPlaying ? "spielt" : "bereit");
  },
  _teardown() {
    clearInterval(this._timer);
    clearInterval(this._sessionTimer);
    this._timer = this._sessionTimer = null;
    if (this.player) { try { this.player.disconnect("user_request"); } catch (e) { /* ignore */ } }
    this.player = null;
  },
  /* Sound needs a tap once per page load (iPad/iPhone, Chrome).  Only an
   * unlock inside a tap counts; one without may or may not work. */
  unlock(tap) {
    if (!this.player) return;
    try {
      const p = this.player.unlock();
      if (tap) this.needsTap = false;
      if (p && p.catch) p.catch(() => { if (tap) this.needsTap = true; });
    } catch (e) { /* ignore */ }
    // On iPad/iPhone sendspin plays through an <audio> element.  Another
    // sound (Beat's own browser stream, "this device") pauses it, and the
    // library's unlock only resumes the AudioContext – start it again here.
    this._weiter();
    this._wache();
    this._listeners.forEach((fn) => { try { fn(); } catch (e) { this._listeners.delete(fn); } });
  },
  _el() { try { return this.player && this.player.scheduler && this.player.scheduler.audioElement; } catch (e) { return null; } },
  _weiter() {
    const el = this._el();
    if (el && el.paused && el.srcObject) { const p = el.play(); if (p && p.catch) p.catch(() => { this.needsTap = true; }); }
  },
  /* resume after iOS paused us – unless Beat's own browser stream plays now */
  _wache() {
    const el = this._el();
    if (!el || el.__yapaiaWache) return;
    el.__yapaiaWache = true;
    el.addEventListener("pause", () => {
      // only while Music Assistant is playing to us (a stop pauses it on purpose)
      setTimeout(() => { if (this.wanted && this.player && this.player.isPlaying && !BrowserPlayer.playing) this._weiter(); }, 1000);
    });
  },
  setWanted(on) {
    this.wanted = on;
    schreib("yapaia-beat.ma", on ? "1" : "0");
    clearTimeout(this._retry);
    if (on) { this.needsTap = true; this.start().then(() => this.unlock(false)); }
    else { this._teardown(); this._set("aus"); }
  },
  /* Plays the radio here right now?  Then announcements are mixed in here. */
  hoertHier() {
    return !!(this.wanted && this.player && this.player.isConnected && this.player.isPlaying);
  },
  /* Mix an announcement (an audio file of Home Assistant's TTS) into what
   * this player plays: music down, announcement on top, music up again.
   * Right here in the browser – without Music Assistant's stock of the radio
   * stream, which delayed announcements mixed in by Beat by several seconds.
   * One at a time; resolves true once it has been played. */
  sprich(url, pegel = 0.3) {
    const lauf = (this._ansagen || Promise.resolve()).then(() => this._sprich(url, pegel));
    this._ansagen = lauf.catch(() => false);
    return lauf;
  },
  async _sprich(url, pegel) {
    const s = this.player && this.player.scheduler;
    const ctx = s && s.audioContext;
    const g = s && s.gainNode;
    if (!ctx || !g) return false;
    try {
      if (ctx.state === "suspended") await ctx.resume();
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) return false;
      const audio = await ctx.decodeAudioData(await res.arrayBuffer());
      const src = ctx.createBufferSource();
      src.buffer = audio;
      const voll = g.gain.value;
      // as loud as the music at the player's volume (the player's own gain
      // is the one turned down); muted → still audible
      const laut = ctx.createGain();
      laut.gain.value = voll > 0.05 ? voll : 1;
      // the same output as the music (on iPad/iPhone: its <audio> element),
      // so iOS does not pause one for the other
      src.connect(laut).connect(s.streamDestination || ctx.destination);
      const t = ctx.currentTime;
      g.gain.cancelScheduledValues(t);
      g.gain.setValueAtTime(voll, t);
      g.gain.linearRampToValueAtTime(voll * pegel, t + 0.25);
      const fertig = new Promise((r) => { src.onended = r; });
      src.start(t + 0.25);
      this._weiter();
      await fertig;
      const t2 = ctx.currentTime;
      g.gain.cancelScheduledValues(t2);
      g.gain.setValueAtTime(g.gain.value, t2);
      g.gain.linearRampToValueAtTime(voll, t2 + 0.5);
      return true;
    } catch (e) {
      console.warn("Yapaia Beat: announcement in the browser failed", e);
      return false;
    }
  },
  setName(name) {
    const n = String(name || "").trim().slice(0, 40);
    if (!n || n === this.name) return;
    this.name = n;
    schreib("yapaia-beat.ma-name", n);
    if (this.player) { this._teardown(); this.start(); }
  },
};
window.YapaiaBeatMa = MaPlayer;
if (MaPlayer.wanted) {
  MaPlayer.needsTap = true;
  // wait until Home Assistant's frontend is ready
  // … and until Home Assistant has fully started: a session created before
  // that carries no user, and Music Assistant turns it down
  const los = () => {
    const h = MaPlayer._hass();
    return h && (!h.config || !h.config.state || h.config.state === "RUNNING") ? MaPlayer.start() : setTimeout(los, 1000);
  };
  setTimeout(los, 500);
}

/* DAB+ slideshow in full size (tap again or Esc to close). Lives on
 * document.body so no dashboard layout can clip it. */
function showZoom(src) {
  if (!src) return;
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;inset:0;z-index:10000;background:#000d;display:flex;align-items:center;justify-content:center;cursor:zoom-out;padding:16px;box-sizing:border-box";
  const img = document.createElement("img");
  img.src = src;
  img.style.cssText = "max-width:100%;max-height:100%;width:min(100%,960px);object-fit:contain;border-radius:12px;box-shadow:0 10px 40px #000";
  box.appendChild(img);
  const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  box.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.appendChild(box);
}

// Browsers only allow sound after a tap: if "this device" was chosen
// earlier, the first tap anywhere on the dashboard starts it.
if (!window.__yapaiaUnlock) {
  window.__yapaiaUnlock = true;
  const unlock = () => {
    if (BrowserPlayer.wanted && BrowserPlayer.blocked) BrowserPlayer.start();
    if (MaPlayer.wanted && MaPlayer.needsTap) MaPlayer.unlock(true);
  };
  ["click", "touchend", "keydown"].forEach((ev) => document.addEventListener(ev, unlock, { capture: true, passive: true }));
}

class YapaiaBeatCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find((e) => e.startsWith("media_player.yapaia_beat")) || "media_player.yapaia_beat";
    return { entity, style: "retro" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "media_player" } } },
        { name: "follow_entity", selector: { entity: { domain: "switch" } } },
        {
          name: "style",
          selector: { select: { mode: "dropdown", options: [{ value: "retro", label: "Retro (Holz & LCD)" }, { value: "modern", label: "Modern" }] } },
        },
        { name: "max_presets", selector: { number: { min: 0, max: 30, mode: "box" } } },
        { name: "show_slide", selector: { boolean: {} } },
        { name: "show_output", selector: { boolean: {} } },
      ],
      computeLabel: (s) => ({
        entity: "Yapaia Beat Media Player",
        follow_entity: "Schalter Senderverfolgung",
        style: "Design",
        max_presets: "Anzahl Favoriten-Tasten",
        show_slide: "DAB+ Slideshow anzeigen",
        show_output: "Ausgabe-Auswahl (Mini-PC / dieses Gerät / Lautsprecher)",
      }[s.name]),
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("entity muss gesetzt sein (media_player.yapaia_beat)");
    this._config = { style: "retro", max_presets: 12, show_slide: true, show_output: true, ...config };
    if (!this._config.follow_entity) {
      this._config.follow_entity = config.entity.replace("media_player.", "switch.") + "_auto_follow";
    }
    this._built = false;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const s = hass.states[this._config && this._config.entity];
    if (s) { BrowserPlayer.prepare(hass, s.attributes.stream_path); BrowserPlayer._syncState(s); }
    this._render();
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _browserOnly() {
    const a = this._stateObj ? this._stateObj.attributes : {};
    return BrowserPlayer.wanted && !a.speaker && !(a.local_audio && a.local_output !== false);
  }

  _call(domain, service, data = {}) {
    return this._hass.callService(domain, service, { entity_id: this._config.entity, ...data });
  }

  _build() {
    this.innerHTML = "";
    const card = document.createElement("ha-card");
    card.innerHTML = `
      <style>${YapaiaBeatCard.styles}</style>
      <div class="yb ${this._config.style === "modern" ? "modern" : "retro"}">
        <div class="cabinet">
          <div class="brand"><span class="dot"></span>YAPAIA BEAT<span class="band"></span></div>
          <div class="display">
            <div class="logo-wrap"><img class="logo" alt=""></div>
            <div class="lcd">
              <div class="row1"><span class="name"></span><span class="sig"><i></i><i></i><i></i><i></i><i></i></span></div>
              <div class="row2"><span class="loc"></span><span class="st">ST</span><span class="fo">AF</span></div>
              <div class="row3"><div class="marquee"><span class="text"></span></div></div>
              <div class="row4 song"></div>
            </div>
            <img class="slide" alt="">
          </div>
          <div class="presets"></div>
          <div class="panel">
            <button class="b prev" title="Vorheriger Favorit">${svg(ICONS.prev)}</button>
            <button class="b play big" title="Play/Stop"></button>
            <button class="b next" title="Nächster Favorit">${svg(ICONS.next)}</button>
            <button class="b fav" title="Favorit"></button>
            <div class="vol">
              <button class="b mute small" title="Stumm"></button>
              <input type="range" min="0" max="100" step="1" class="volume">
            </div>
            <button class="b follow small" title="Automatische Senderverfolgung">${svg(ICONS.follow)}</button>
            <button class="b out small" title="Ausgabe wählen">${svg(ICONS.speaker)}</button>
          </div>
          <div class="outmenu" hidden></div>
          <div class="msg"></div>
        </div>
      </div>`;
    this.appendChild(card);
    const q = (s) => card.querySelector(s);
    this._el = {
      root: q(".yb"), band: q(".band"), logo: q(".logo"), name: q(".name"), loc: q(".loc"), text: q(".text"),
      song: q(".song"), bars: [...card.querySelectorAll(".sig i")], st: q(".st"), fo: q(".fo"), slide: q(".slide"),
      presets: q(".presets"), play: q(".play"), fav: q(".fav"), mute: q(".mute"), volume: q(".volume"),
      follow: q(".follow"), msg: q(".msg"), marquee: q(".marquee"),
      out: q(".out"), outMenu: q(".outmenu"),
    };
    q(".prev").onclick = () => this._call("media_player", "media_previous_track");
    q(".next").onclick = () => this._call("media_player", "media_next_track");
    this._el.play.onclick = () => {
      if (!this._playing && BrowserPlayer.wanted) BrowserPlayer.start(); // inside the tap (iOS)
      this._call("media_player", this._playing ? "media_stop" : "media_play");
    };
    this._el.out.onclick = () => {
      if (BrowserPlayer.blocked) { BrowserPlayer.start(); return; }
      this._el.outMenu.hidden = !this._el.outMenu.hidden;
      this._renderOutMenu();
    };
    this._el.outMenu.onclick = (ev) => {
      const b = ev.target.closest("[data-out]");
      if (!b || b.disabled) return;
      const out = b.dataset.out;
      // start the browser inside the tap (iOS)
      BrowserPlayer.setWanted(out === "browser" || out === "both");
      const output = out.startsWith("speaker:") ? out.slice(8) : out === "local" || out === "both" ? "local" : "none";
      this._hass.callService("yapaia_beat", "set_output", { output });
      this._el.outMenu.hidden = true;
      this._render();
    };
    this._el.mute.onclick = () => this._call("media_player", "volume_mute", { is_volume_muted: !this._muted });
    this._el.volume.oninput = (e) => e.target.style.setProperty("--f", String(Number(e.target.value) / 100));
    this._el.volume.onchange = (e) => {
      if (this._browserOnly()) { BrowserPlayer.setVolume(Number(e.target.value)); this._render(); }
      else this._call("media_player", "volume_set", { volume_level: Number(e.target.value) / 100 });
    };
    this._el.follow.onclick = () => {
      const s = this._hass.states[this._config.follow_entity];
      if (s) this._hass.callService("switch", s.state === "on" ? "turn_off" : "turn_on", { entity_id: this._config.follow_entity });
    };
    this._el.fav.onclick = () => {
      const a = this._stateObj && this._stateObj.attributes;
      if (a && a.station_id) this._hass.callService("yapaia_beat", "set_favorite", { station_id: a.station_id, favorite: !a.favorite });
    };
    this._el.presets.onclick = (e) => {
      const b = e.target.closest("[data-id]");
      if (b) this._hass.callService("yapaia_beat", "play", { station_id: b.dataset.id });
    };
    this._el.logo.onerror = () => { this._el.logo.style.visibility = "hidden"; };
    this._el.logo.onload = () => { this._el.logo.style.visibility = "visible"; };
    this._el.slide.onerror = () => { this._el.slide.hidden = true; };
    this._el.slide.onclick = () => showZoom(this._el.slide.src);
    this._el.slide.title = "Vergrößern";
    this._built = true;
    BrowserPlayer._entity = this._config.entity;
    if (!this._onPlayer) {
      this._onPlayer = () => this._render();
      BrowserPlayer._listeners.add(this._onPlayer);
    }
  }

  disconnectedCallback() {
    if (this._onPlayer) BrowserPlayer._listeners.delete(this._onPlayer);
    this._onPlayer = null;
  }

  connectedCallback() {
    if (this._built && !this._onPlayer) {
      this._onPlayer = () => this._render();
      BrowserPlayer._listeners.add(this._onPlayer);
    }
  }

  _outMode(a) {
    if (a.speaker) return "speaker:" + a.speaker;
    const local = a.local_audio && a.local_output !== false;
    return local && BrowserPlayer.wanted ? "both" : BrowserPlayer.wanted ? "browser" : local ? "local" : "none";
  }

  _outLabel(a) {
    const mode = this._outMode(a);
    if (mode.startsWith("speaker:")) {
      const p = (a.players || []).find((x) => x.entity_id === a.speaker);
      return p ? p.name : a.speaker;
    }
    return { local: "Mini-PC", browser: "Dieses Gerät", both: "Mini-PC + dieses Gerät", none: "keine" }[mode];
  }

  _renderOutMenu() {
    const a = this._stateObj ? this._stateObj.attributes : {};
    const mode = this._outMode(a);
    const item = (value, label, disabled) =>
      `<button data-out="${esc(value)}" class="${mode === value ? "active" : ""}" ${disabled ? "disabled" : ""}>${esc(label)}</button>`;
    const players = a.players || [];
    this._el.outMenu.innerHTML =
      item("browser", "📱 Dieses Gerät", !a.stream_path) +
      item("local", "🖥 Mini-PC", !a.local_audio) +
      item("both", "🖥 Mini-PC + 📱 dieses Gerät", !a.local_audio || !a.stream_path) +
      players.map((p) => item("speaker:" + p.entity_id, "🔊 " + p.name)).join("") +
      (a.local_audio ? "" : item("none", "🔇 Keine Ausgabe"));
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this._built) this._build();
    const e = this._el;
    const s = (this._stateObj = this._hass.states[this._config.entity]);
    if (!s) {
      e.name.textContent = "Entität nicht gefunden";
      e.loc.textContent = this._config.entity;
      return;
    }
    const a = s.attributes;
    const playing = (this._playing = ["playing", "buffering"].includes(s.state));
    this._muted = !!a.is_volume_muted;
    e.root.classList.toggle("on", playing);
    e.name.textContent = a.station_name || "Yapaia Beat";
    e.loc.textContent = a.radio_state === "scanning" ? "Suchlauf …" : a.location || "";
    e.band.textContent = a.band === "dab" ? "DAB+" : a.band === "fm" ? "UKW" : "";

    const text = a.radio_state === "scanning" ? a.media_title : (playing ? a.radiotext || a.station_name : "— bereit —") || "";
    if (text !== this._lastText) {
      this._lastText = text;
      e.text.textContent = text;
      e.text.classList.remove("scroll");
      requestAnimationFrame(() => {
        if (e.text.scrollWidth > e.marquee.clientWidth) {
          e.text.style.setProperty("--dur", `${Math.max(8, text.length / 4)}s`);
          e.text.classList.add("scroll");
        }
      });
    }
    const song = playing && a.media_artist && a.media_title && a.media_title !== a.radiotext && a.media_artist !== a.station_name
      ? `♪ ${a.media_artist} – ${a.media_title}` : "";
    e.song.textContent = song;

    if (a.logo && a.logo !== this._lastLogo) { this._lastLogo = a.logo; e.logo.src = a.logo; }
    const sig = playing && a.signal != null ? a.signal : null;
    e.bars.forEach((b, i) => b.classList.toggle("on", sig != null && sig > i * 20 + 5));
    e.root.classList.toggle("weak", sig != null && sig < 35);
    e.st.classList.toggle("lit", playing && !!a.stereo);

    const follow = this._hass.states[this._config.follow_entity];
    const followOn = follow ? follow.state === "on" : !!a.auto_follow;
    e.fo.classList.toggle("lit", followOn);
    e.follow.classList.toggle("active", followOn);
    e.follow.hidden = !follow;

    const slide = this._config.show_slide && playing && a.band === "dab" && a.slide;
    if (slide && slide !== this._lastSlide) { this._lastSlide = slide; e.slide.hidden = false; e.slide.src = slide; }
    if (!slide) { e.slide.hidden = true; this._lastSlide = null; }

    e.play.innerHTML = svg(playing ? ICONS.stop : ICONS.play);
    e.fav.innerHTML = svg(a.favorite ? ICONS.star : ICONS.starOff);
    e.fav.classList.toggle("active", !!a.favorite);
    e.mute.innerHTML = svg(this._muted ? ICONS.mute : ICONS.volDown);
    const vol = this._browserOnly() ? BrowserPlayer.volume : Math.round((a.volume_level || 0) * 100);
    if (!e.volume.matches(":active")) e.volume.value = vol;
    e.volume.style.setProperty("--f", String(Number(e.volume.value) / 100));
    e.out.hidden = !this._config.show_output;
    e.out.classList.toggle("active", !!a.speaker || BrowserPlayer.wanted);
    e.out.classList.toggle("blink", BrowserPlayer.wanted && BrowserPlayer.blocked);
    e.out.title = BrowserPlayer.blocked ? "Tippen, um den Ton auf diesem Gerät zu starten" : `Ausgabe: ${this._outLabel(a)}`;
    if (!e.outMenu.hidden) this._renderOutMenu();
    BrowserPlayer.updateSession(a, this._hass);
    e.msg.textContent = a.speaker_error ? `⚠ ${a.speaker_error}` : a.follow_message || "";

    const favs = (a.favorites || []).slice(0, this._config.max_presets);
    const key = JSON.stringify(favs.map((f) => [f.id, f.name, f.logo])) + (a.active_favorite || a.station_id);
    if (key !== this._lastPresets) {
      this._lastPresets = key;
      e.presets.hidden = favs.length === 0 || this._config.max_presets === 0;
      e.presets.innerHTML = favs.map((f, i) => `
        <button class="preset ${f.id === (a.active_favorite || a.station_id) ? "active" : ""}" data-id="${esc(f.id)}" title="${esc(f.name)}">
          <span class="num">${i + 1}</span>
          <img src="${esc(f.logo)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
          <span class="pname">${esc(f.name)}</span>
        </button>`).join("");
    }
  }
}

YapaiaBeatCard.styles = `
  ha-card { overflow: hidden; }
  .yb { --lcd-bg: #1b2a12; --lcd-fg: #c6ff8a; --lcd-glow: #9dff5a66; --accent: #ff8a3d; padding: 14px; }
  .yb.retro .cabinet {
    background: linear-gradient(180deg, #6b3d20, #4a2814 60%, #3a1f10);
    border-radius: 18px; padding: 14px 16px 12px; box-shadow: inset 0 2px 0 #ffffff22, inset 0 -3px 8px #0006, 0 4px 14px #0005;
    background-image: repeating-linear-gradient(95deg, #ffffff06 0 2px, transparent 2px 9px), linear-gradient(180deg, #6b3d20, #4a2814 60%, #3a1f10);
  }
  .yb.modern { --lcd-bg: #0c1030; --lcd-fg: #eef0ff; --lcd-glow: transparent; --accent: #ff6b35; }
  .yb.modern .cabinet { background: linear-gradient(160deg, #262b5e, #120f2b); border-radius: 18px; padding: 14px 16px 12px; }
  .brand { display: flex; align-items: center; gap: 8px; color: #f3d9b5; font: 700 11px/1 sans-serif; letter-spacing: 4px; margin-bottom: 10px; }
  .modern .brand { color: #9aa0c8; }
  .brand .dot { width: 8px; height: 8px; border-radius: 50%; background: #551; box-shadow: none; transition: .3s; }
  .on .brand .dot { background: #ff4d3d; box-shadow: 0 0 8px #ff4d3d; }
  .brand .band { margin-left: auto; letter-spacing: 2px; color: var(--accent); }
  .display { display: flex; gap: 12px; align-items: stretch; background: #0008; border-radius: 12px; padding: 10px; box-shadow: inset 0 0 10px #000c; }
  .logo-wrap { flex: 0 0 auto; width: 92px; height: 92px; border-radius: 10px; background: #fff1; display: grid; place-items: center; overflow: hidden; }
  .logo { width: 100%; height: 100%; object-fit: contain; }
  .slide { flex: 0 0 auto; width: 92px; height: 92px; object-fit: cover; border-radius: 10px; cursor: zoom-in; }
  .lcd { flex: 1; min-width: 0; background: var(--lcd-bg); border-radius: 8px; padding: 8px 10px; color: var(--lcd-fg);
         font-family: "DejaVu Sans Mono", "Courier New", monospace; text-shadow: 0 0 6px var(--lcd-glow); display: flex; flex-direction: column; justify-content: center; gap: 3px; }
  .yb:not(.on) .lcd { opacity: .6; }
  .row1 { display: flex; align-items: center; gap: 8px; }
  .name { flex: 1; font-size: 20px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sig { display: flex; align-items: flex-end; gap: 2px; height: 14px; }
  .sig i { width: 4px; background: #ffffff22; border-radius: 1px; }
  .sig i:nth-child(1) { height: 20%; } .sig i:nth-child(2) { height: 40%; } .sig i:nth-child(3) { height: 60%; } .sig i:nth-child(4) { height: 80%; } .sig i:nth-child(5) { height: 100%; }
  .sig i.on { background: var(--lcd-fg); }
  .weak .sig i.on { background: #ffb13d; }
  .row2 { display: flex; gap: 8px; align-items: center; font-size: 12px; opacity: .85; }
  .row2 .loc { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .st, .fo { font-size: 9px; font-weight: 700; padding: 0 4px; border: 1px solid currentColor; border-radius: 3px; opacity: .25; }
  .st.lit, .fo.lit { opacity: 1; }
  .marquee { overflow: hidden; white-space: nowrap; font-size: 13px; }
  .text { display: inline-block; }
  .text.scroll { padding-left: 100%; animation: yb-marquee var(--dur, 14s) linear infinite; }
  @keyframes yb-marquee { from { transform: translateX(0); } to { transform: translateX(-100%); } }
  .song { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-height: 14px; }
  .presets { display: grid; grid-template-columns: repeat(auto-fill, minmax(74px, 1fr)); gap: 8px; margin-top: 12px; }
  .preset { position: relative; display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 6px 4px 5px; border: 0; border-radius: 10px; cursor: pointer;
            background: linear-gradient(180deg, #f4efe6, #d8cfc0); color: #3a2a1a; box-shadow: 0 3px 0 #0007, inset 0 1px 0 #fff; transition: transform .08s; font: inherit; }
  .modern .preset { background: #ffffff12; color: #eef0ff; box-shadow: none; border: 1px solid #ffffff1a; }
  .preset:active { transform: translateY(2px); box-shadow: 0 1px 0 #0007; }
  .preset.active { background: linear-gradient(180deg, #ffd9a0, #ff9f55); }
  .modern .preset.active { background: #ff6b3533; border-color: var(--accent); }
  .preset img { width: 40px; height: 40px; object-fit: contain; border-radius: 8px; }
  .preset .num { position: absolute; top: 3px; left: 6px; font-size: 9px; font-weight: 700; opacity: .6; }
  .preset .pname { font-size: 10px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .panel { display: flex; align-items: center; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .b { width: 42px; height: 42px; border-radius: 50%; border: 0; display: grid; place-items: center; cursor: pointer; padding: 0;
       background: radial-gradient(circle at 35% 30%, #5a5a5a, #1d1d1d); color: #eee; box-shadow: 0 2px 4px #0008, inset 0 1px 0 #ffffff33; }
  .modern .b { background: #ffffff14; box-shadow: none; }
  .b svg { width: 22px; height: 22px; fill: currentColor; }
  .b.big { width: 52px; height: 52px; background: radial-gradient(circle at 35% 30%, #ffb070, #e0551c); color: #fff; }
  .modern .b.big { background: var(--accent); }
  .b.small { width: 34px; height: 34px; }
  .b.small svg { width: 18px; height: 18px; }
  .b.active { color: #ffcf5a; }
  .b.blink { animation: yb-blink 1s ease-in-out infinite; }
  @keyframes yb-blink { 50% { color: #ff6b35; box-shadow: 0 0 10px #ff6b35; } }
  .b[hidden] { display: none; }
  .vol { flex: 1; display: flex; align-items: center; gap: 6px; min-width: 120px; }
  /* own slider: the native one on iPad/iPhone filled ahead of its thumb */
  .volume { flex: 1; -webkit-appearance: none; appearance: none; height: 26px; background: transparent; --f: 0.5; margin: 0; }
  .volume::-webkit-slider-runnable-track { height: 6px; border-radius: 3px; background: linear-gradient(to right, var(--accent) 0 calc(10px + (100% - 20px) * var(--f)), #ffffff2a 0); }
  .volume::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; margin-top: -7px; border-radius: 50%; background: #fff; border: 0; box-shadow: 0 1px 4px #0008; }
  .volume::-moz-range-track { height: 6px; border-radius: 3px; background: #ffffff2a; }
  .volume::-moz-range-progress { height: 6px; border-radius: 3px; background: var(--accent); }
  .volume::-moz-range-thumb { width: 20px; height: 20px; border-radius: 50%; background: #fff; border: 0; }
  .outmenu { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .outmenu[hidden] { display: none; }
  .outmenu button { border: 1px solid #ffffff2a; background: #0005; color: #f3e6d4; border-radius: 16px; padding: 6px 12px; font: inherit; font-size: 13px; cursor: pointer; }
  .outmenu button.active { border-color: var(--accent); color: #fff; background: #ff8a3d55; }
  .outmenu button:disabled { opacity: .35; cursor: not-allowed; }
  .msg { color: #ffd9a8; font-size: 12px; min-height: 0; margin-top: 6px; }
  .msg:empty { display: none; }
  @media (max-width: 420px) { .slide { display: none; } .logo-wrap { width: 72px; height: 72px; } .name { font-size: 17px; } }
`;

// The HA frontend may swap its custom element registry while extra modules
// load; make sure the card stays registered (re-check for a while).
const defineCard = () => {
  if (!customElements.get("yapaia-beat-card")) {
    try { customElements.define("yapaia-beat-card", YapaiaBeatCard); } catch (e) { /* already defined */ }
  }
};
defineCard();
let defineChecks = 0;
const defineTimer = setInterval(() => { defineCard(); if (++defineChecks > 60) clearInterval(defineTimer); }, 500);
window.addEventListener("load", defineCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "yapaia-beat-card",
  name: "Yapaia Beat",
  description: "Radio-Karte für Yapaia Beat (FM & DAB+) mit Logo, RDS/DLS, Favoriten-Tasten und Lautstärke.",
  preview: true,
  documentationURL: "https://github.com/apfelsafft/radio",
});
console.info(`%c YAPAIA-BEAT-CARD %c ${CARD_VERSION} `, "color:#fff;background:#ff6b35;font-weight:700", "color:#ff6b35;background:#1b1f3b");
