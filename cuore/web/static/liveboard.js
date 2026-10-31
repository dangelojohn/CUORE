/* Liveboard -- the passenger-seat live gauge board (/v/{vin}/liveboard).
 *
 * Vanilla JS, no CDN, same module shape as cuore/web/static/live/dashboard.js
 * (an IIFE exposing one global, a thin `api()` wrapper over fetch, plain
 * prototypes rather than a framework). Three jobs:
 *
 *   1. Load the channel/band contract from GET /api/liveboard/{vin} -- or,
 *      if that 404s/errors (the data API may not have landed yet), fall
 *      back to FIXTURE_GROUPS below so the page still works end to end.
 *   2. Drive values onto the page from one of two sources -- the real
 *      /api/live session+stream engine ("Start"), or a client-side demo
 *      generator ("Demo", also auto-started on ?demo=1 / ?autostart=demo)
 *      -- computing each channel's ok/moderate/excessive/unknown level
 *      from its band *in the browser*, every sample, with no round trip.
 *   3. On Snapshot, save the current values to /api/live/snapshots, ask
 *      /api/liveboard/evaluate for recommendation text, and (best-effort,
 *      tolerating a 404 if that route hasn't landed yet either) file the
 *      snapshot onto the open Job via /api/liveboard/{vin}/snapshot-to-job.
 */

(function (global) {
  "use strict";

  var STALE_MS = 10000;

  // -----------------------------------------------------------------------
  // Fixture contract -- same shape GET /api/liveboard/{vin} promises
  // ({groups: [{id, label, channels: [{id, name, unit, rate_hz, band, system}]}],
  // all_channel_ids, rates, notice}). Used only when that endpoint isn't
  // reachable; channel ids match live/dashboard.js's own demo profile ids
  // below so the client demo generator produces plausible numbers for them
  // whether the groups came from the real contract or this fixture.
  // -----------------------------------------------------------------------

  // ``normal``/``alarm`` are both ``[lo, hi]`` pairs (either side nullable)
  // -- the same shape ``cuore.services.liveboard_bridge.board()`` sends:
  // for a one-sided row ("above"/"below") only the relevant side of
  // ``alarm`` is set, for a "both" row either side can be.
  function band(normal, alarm, direction, confidence, source) {
    return { normal: normal, warn: null, alarm: alarm, direction: direction,
             confidence: confidence, source: source };
  }

  var FIXTURE_GROUPS = [
    { id: "engine", label: "Engine", channels: [
      { id: "engine_rpm", name: "Engine speed", unit: "rpm", rate_hz: 2, band: null, system: "engine" },
      { id: "engine_coolant_temp", name: "Coolant temperature", unit: "C", rate_hz: 1,
        band: band([88, 105], [null, 130], "above", "SINGLE-SOURCE", "stelvioforum.com"), system: "engine" },
      { id: "engine_oil_temp", name: "Oil temperature", unit: "C", rate_hz: 1,
        band: band([70, 110], [null, 130], "above", "SINGLE-SOURCE", null), system: "engine" },
      { id: "intake_air_temp", name: "Intake air temperature", unit: "°C", rate_hz: 1, band: null, system: "engine" },
      { id: "engine_load", name: "Calculated load", unit: "%", rate_hz: 1, band: null, system: "engine" },
    ] },
    { id: "fuel_air", label: "Fuel & air", channels: [
      { id: "throttle_position", name: "Throttle position", unit: "%", rate_hz: 1, band: null, system: "fuel" },
      { id: "intake_map", name: "Manifold pressure", unit: "kPa", rate_hz: 1, band: null, system: "fuel" },
      { id: "barometric_pressure", name: "Barometric pressure", unit: "kPa", rate_hz: 0.2, band: null, system: "fuel" },
      { id: "boost", name: "Boost", unit: "kPa", rate_hz: 1, band: null, system: "fuel" },
      { id: "fuel_level", name: "Fuel level", unit: "%", rate_hz: 0.2, band: null, system: "fuel" },
    ] },
    { id: "electrical", label: "Electrical", channels: [
      { id: "battery_voltage", name: "Battery voltage", unit: "V", rate_hz: 1,
        band: band([13.2, 14.8], [11.8, null], "below", "CORROBORATED", null), system: "electrical" },
    ] },
    { id: "drivetrain", label: "Drivetrain", channels: [
      { id: "vehicle_speed", name: "Vehicle speed", unit: "km/h", rate_hz: 1, band: null, system: "chassis" },
      { id: "tcm_04fe", name: "Transmission fluid temperature", unit: "C", rate_hz: 1,
        band: band([60, 100], [null, 120], "above", "SINGLE-SOURCE", null), system: "drivetrain" },
    ] },
    { id: "ambient", label: "Ambient", channels: [
      { id: "ambient_air_temp", name: "Ambient air temperature", unit: "C", rate_hz: 0.2, band: null, system: "engine" },
    ] },
  ];

  var FIXTURE_NOTICE = "Fixture data — the live channel/band list hasn't connected yet; showing the built-in set.";

  // -----------------------------------------------------------------------
  // Level computation -- the SAME rules the data agent's /evaluate uses,
  // run here client-side so colour updates every sample with no round
  // trip: inside `normal` -> ok; between `normal` and `alarm` -> moderate;
  // beyond `alarm` -> excessive; `direction` says which side of `normal`
  // the alarm sits on. No band at all, or a non-numeric value -> unknown.
  // -----------------------------------------------------------------------

  // Mirrors ``cuore.services.liveboard_bridge._grade`` exactly: ``normal``
  // and ``alarm`` are both ``[lo, hi]`` pairs (either side may be null).
  // No ``normal`` at all -> unknown (no sourced reference). Inside
  // ``normal`` -> ok. Outside it but not past the far edge of ``alarm`` on
  // the violated side -> moderate. Past that edge -> excessive. ``warn``
  // is carried in the band for the note only -- the real grader never
  // consults it either.
  function computeLevel(b, value) {
    if (!b || typeof value !== "number" || isNaN(value)) return "unknown";
    var normal = b.normal;
    if (!Array.isArray(normal) || normal.length < 2) return "unknown";
    var lo = normal[0], hi = normal[1];
    var alarm = Array.isArray(b.alarm) ? b.alarm : [null, null];
    var aLo = alarm[0], aHi = alarm[1];
    var dir = b.direction || "both";
    if (dir === "above") {
      if (value <= hi) return "ok";
      return (aHi != null && value > aHi) ? "excessive" : "moderate";
    }
    if (dir === "below") {
      if (value >= lo) return "ok";
      return (aLo != null && value < aLo) ? "excessive" : "moderate";
    }
    // "both": either side of the normal envelope grades the same way
    if (value >= lo && value <= hi) return "ok";
    if (value < lo) return (aLo != null && value < aLo) ? "excessive" : "moderate";
    return (aHi != null && value > aHi) ? "excessive" : "moderate";
  }

  function fmtNum(n) {
    if (typeof n !== "number") return String(n);
    return (Math.round(n * 100) / 100).toString();
  }

  // A short, sourced-looking note under the channel name, e.g.
  // "88-105 C normal, >130 alarm (SINGLE-SOURCE)" -- the ">130"/"<11.8"
  // edge shown is whichever side of ``alarm`` actually drives the
  // excessive cutoff for this band's ``direction`` (see computeLevel).
  var UNIT_MAP = { c: "°C", degc: "°C", "°c": "°C", celsius: "°C", f: "°F", kpa: "kPa",
    v: "V", pct: "%", percent: "%", kph: "km/h", kmh: "km/h" };
  // Same table as liveboard_view.fmt_unit: "C" always reads "°C".
  function fmtUnit(u) {
    var k = String(u == null ? "" : u).trim();
    return Object.prototype.hasOwnProperty.call(UNIT_MAP, k.toLowerCase()) ? UNIT_MAP[k.toLowerCase()] : k;
  }

  function bandNote(b, unit) {
    if (!b) return "";
    var parts = [];
    if (Array.isArray(b.normal) && b.normal[0] != null && b.normal[1] != null) {
      parts.push(fmtNum(b.normal[0]) + "-" + fmtNum(b.normal[1]) + " " + fmtUnit(unit) + " normal");
    }
    var alarm = Array.isArray(b.alarm) ? b.alarm : [null, null];
    var aLo = alarm[0], aHi = alarm[1];
    var dir = b.direction || "both";
    var alarmBits = [];
    if ((dir === "below" || dir === "both") && aLo != null) alarmBits.push("<" + fmtNum(aLo));
    if ((dir === "above" || dir === "both") && aHi != null) alarmBits.push(">" + fmtNum(aHi));
    if (alarmBits.length) parts.push(alarmBits.join(" or ") + " alarm");
    var note = parts.join(", ").trim();
    // How sure the numbers are is a plain-words chip on the row (shown only while a value is live), not here.
    return note;
  }

  function levelRank(l) { return { excessive: 3, moderate: 2, ok: 1, unknown: 0 }[l] || 0; }

  // -----------------------------------------------------------------------
  // Demo simulator -- same drive-cycle idea as live/dashboard.js's
  // DemoSource/demoValue, reused verbatim for the ids it already knows.
  // -----------------------------------------------------------------------

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function round2(v) { return Math.round(v * 100) / 100; }
  function hashSeed(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 1000;
    return (h / 1000) * 6.28;
  }

  function demoDriveInputs(t) {
    var throttle = clamp(0.12 + 0.5 * (0.5 + 0.5 * Math.sin(t / 14)) +
      0.18 * Math.sin(t / 3.1) + 0.05 * Math.sin(t * 2.7), 0, 1);
    return { throttle: throttle };
  }

  var DEMO_PROFILES = {
    engine_rpm: function (t, d) { return 780 + d.throttle * 4600 + 60 * Math.sin(t * 3); },
    vehicle_speed: function (t, d) { return clamp(8 + d.throttle * 150 + 10 * Math.sin(t / 9), 0, 220); },
    throttle_position: function (t, d) { return d.throttle * 100; },
    engine_load: function (t, d) { return clamp(d.throttle * 90 + 5, 0, 100); },
    intake_map: function (t, d) { return 30 + d.throttle * 130; },
    barometric_pressure: function () { return 99.5; },
    boost: function (t, d) { return Math.max(0, d.throttle - 0.55) * 20; },
    intake_air_temp: function (t) { return 24 + 2 * Math.sin(t / 60); },
    ambient_air_temp: function (t) { return 21 + Math.sin(t / 120); },
    engine_coolant_temp: function (t) { return Math.min(92, 20 + t * 0.35) + Math.sin(t / 20); },
    engine_oil_temp: function (t) { return Math.min(105, 22 + t * 0.3) + Math.sin(t / 17); },
    battery_voltage: function (t, d) { return 14.1 + 0.15 * Math.sin(t / 5) - d.throttle * 0.05; },
    fuel_level: function (t) { return clamp(78 - t / 240, 0, 100); },
    tcm_04fe: function (t) { return Math.min(88, 20 + t * 0.28); },
  };

  function demoValue(id, t, d, meta) {
    var fn = DEMO_PROFILES[id];
    if (fn) return { value: round2(fn(t, d)), unit: meta ? meta.unit : "" };
    if (/pressure/.test(id)) return { value: round2(30 + 5 * Math.sin(t / 6 + hashSeed(id))), unit: meta ? meta.unit : "kPa" };
    if (/temp/.test(id)) return { value: round2(40 + 10 * Math.sin(t / 25 + hashSeed(id))), unit: meta ? meta.unit : "C" };
    var lo = (meta && typeof meta.min === "number") ? meta.min : 0;
    var hi = (meta && typeof meta.max === "number") ? meta.max : 100;
    var mid = (lo + hi) / 2, amp = (hi - lo) / 2 || 10;
    return { value: round2(mid + amp * 0.6 * Math.sin(t / 8 + hashSeed(id))), unit: meta ? meta.unit : "" };
  }

  function fmtValue(v) {
    if (Math.abs(v) >= 1000) return String(Math.round(v));
    return String(Math.round(v * 10) / 10);
  }

  // -----------------------------------------------------------------------
  // Main app
  // -----------------------------------------------------------------------

  function LiveboardApp(opts) {
    opts = opts || {};
    this.fetchFn = opts.fetch || (global.fetch ? global.fetch.bind(global) : null);
    this.ESClass = opts.EventSource || global.EventSource;
    this.doc = opts.document || document;
    this.now = opts.now || function () { return Date.now() / 1000; };
    this.root = opts.root || this.doc.getElementById("lb-app");
    this.vin = opts.vin || (this.root && this.root.getAttribute("data-vin")) || "";
    this.token = opts.token || this._tokenFromLocation();

    this.groups = [];
    this.channelsById = {};
    this.allChannelIds = [];
    this.rates = {};
    this.notice = "";
    this.values = {};        // id -> {value, unit, level, t}
    this.sourceKind = null;  // "live" | "demo" | null
    this.sessionActive = false;
    this.es = null;
    this._demoTimer = null;
    this._demoT0 = 0;
    this._staleTimer = null;
    this._statusTimer = null;
    this._lastSampleAt = null;
    this.sessionInfo = null;  // last GET /api/live/session payload
    this.hist = {};          // id -> [[t, value], ...] for the graph
    this.tags = [];          // [{t, key, label}] one-tap event marks
    this.recording = false;
  }

  LiveboardApp.prototype._tokenFromLocation = function () {
    try {
      var q = new URLSearchParams(global.location.search);
      return q.get("token") || "";
    } catch (e) { return ""; }
  };

  LiveboardApp.prototype.apiUrl = function (path) {
    if (!this.token) return path;
    return path + (path.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(this.token);
  };

  LiveboardApp.prototype.api = function (path, options) {
    var self = this;
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (!this.fetchFn) return Promise.reject(new Error("no fetch available"));
    return this.fetchFn(this.apiUrl(path), Object.assign({}, options, { headers: headers }))
      .then(function (resp) {
        return resp.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (e) { body = text; }
          if (!resp.ok) {
            var err = new Error((body && body.detail) || resp.statusText || ("HTTP " + resp.status));
            err.status = resp.status; err.body = body;
            throw err;
          }
          return body;
        });
      });
  };

  LiveboardApp.prototype.init = function () {
    var self = this;
    this._wireControls();
    this._wirePicker();
    this._wireGraphTagsRecord();
    return this.loadContract().then(function () {
      self._renderGroups();
      self._syncUi();
      self._startStaleTicker();
      self._pollSessionStatus();
      self._statusTimer = global.setInterval(function () { self._pollSessionStatus(); }, 4000);
      var demoParam = false;
      try {
        var params = new URLSearchParams(global.location.search);
        demoParam = params.get("demo") === "1" || params.get("autostart") === "demo";
      } catch (e) { /* no location in a non-browser test harness */ }
      if (demoParam) self.startDemo();
    });
  };

  LiveboardApp.prototype.loadContract = function () {
    var self = this;
    if (!this.vin) { this._useFixture(); return Promise.resolve(); }
    return this.api("/api/liveboard/" + encodeURIComponent(this.vin))
      .then(function (data) { self._useContract(data); })
      .catch(function () { self._useFixture(); });
  };

  LiveboardApp.prototype._flattenIds = function () {
    var ids = [];
    this.groups.forEach(function (g) { (g.channels || []).forEach(function (c) { ids.push(c.id); }); });
    return ids;
  };

  LiveboardApp.prototype._indexChannels = function () {
    var self = this;
    this.channelsById = {};
    this.groups.forEach(function (g) {
      (g.channels || []).forEach(function (c) { self.channelsById[c.id] = c; });
    });
  };

  LiveboardApp.prototype._useContract = function (data) {
    this.groups = (data && data.groups) || [];
    this.allChannelIds = (data && data.all_channel_ids) || this._flattenIds();
    this.rates = (data && data.rates) || {};
    this.notice = (data && data.notice) || "";
    this._indexChannels();
    this._renderNotice(false);
  };

  LiveboardApp.prototype._useFixture = function () {
    this.groups = JSON.parse(JSON.stringify(FIXTURE_GROUPS));
    this.allChannelIds = this._flattenIds();
    this.rates = {};
    this.groups.forEach(function (g) {
      (g.channels || []).forEach(function (c) { this.rates[c.id] = c.rate_hz || 1; }, this);
    }, this);
    this.notice = FIXTURE_NOTICE;
    this._indexChannels();
    this._renderNotice(true);
  };

  LiveboardApp.prototype._renderNotice = function (isFixture) {
    var el = this.doc.getElementById("lb-notice");
    if (!el) return;
    if (this.notice) {
      el.textContent = this.notice;
      el.hidden = false;
      el.classList.toggle("is-demo", !!isFixture);
    } else {
      el.hidden = true;
    }
  };

  LiveboardApp.prototype._renderNoticeError = function (msg) {
    var el = this.doc.getElementById("lb-notice");
    if (!el) return;
    el.hidden = false;
    el.textContent = msg;
    el.classList.add("is-demo");
  };

  // ---- controls ----------------------------------------------------------

  LiveboardApp.prototype._wireControls = function () {
    var self = this;
    var startBtn = this.doc.getElementById("lb-start");
    var stopBtn = this.doc.getElementById("lb-stop");
    var snapBtn = this.doc.getElementById("lb-snapshot");
    var demoBtn = this.doc.getElementById("lb-demo");
    if (startBtn) startBtn.addEventListener("click", function () { self.startLive(); });
    if (stopBtn) stopBtn.addEventListener("click", function () { self.stop(); });
    if (snapBtn) snapBtn.addEventListener("click", function () { self.snapshot(); });
    if (demoBtn) demoBtn.addEventListener("click", function () { self.startDemo(); });
  };

  LiveboardApp.prototype._setButtons = function () {
    var startBtn = this.doc.getElementById("lb-start");
    var stopBtn = this.doc.getElementById("lb-stop");
    if (startBtn) startBtn.hidden = !!this.sourceKind;
    if (stopBtn) stopBtn.hidden = !this.sourceKind;
    this._syncUi();
  };

  // True while a session is feeding the board: one started here (live or demo) or one already running.
  LiveboardApp.prototype._running = function () {
    return !!(this.sourceKind || (this.sessionInfo && this.sessionInfo.active));
  };

  // Everything that depends on "is a session running": Snapshot, Record, the one-line call, the
  // "No reading" message, and (once, on start) opening the groups.
  LiveboardApp.prototype._syncUi = function () {
    var running = this._running();
    var snap = this.doc.getElementById("lb-snapshot");
    if (snap) {
      // Readings still held on the page after Stop can be snapshotted; before any session there is nothing to save.
      var held = Object.keys(this.values).length > 0;
      snap.disabled = !(running || held);
      snap.title = (running || held) ? "" : "Start a session first";
    }
    var rec = this.doc.getElementById("lb-record-form");
    if (rec) rec.hidden = !(this.sourceKind === "live" || (this.sessionInfo && this.sessionInfo.active && this.sourceKind !== "demo"));
    var line = this.doc.getElementById("lb-call-line");
    var call = this.doc.getElementById("lb-call");
    if (line && call) {
      line.textContent = (running ? call.getAttribute("data-on") : call.getAttribute("data-off")) || line.textContent;
      var cable = this.doc.getElementById("lb-call-cable");
      if (cable) cable.hidden = running;
    }
    var none = this.doc.getElementById("lb-noread");
    if (none) none.hidden = running || Object.keys(this.values).length > 0;
    if (running && !this._groupsOpened) {
      this._groupsOpened = true;
      var ds = this.doc.querySelectorAll ? this.doc.querySelectorAll("details.lb-group") : [];
      for (var i = 0; i < ds.length; i++) {
        if (!ds[i].classList.contains("lb-raw")) ds[i].open = true;
      }
    }
    if (!running) this._groupsOpened = false;
  };

  LiveboardApp.prototype.startLive = function () {
    var self = this;
    var p = this.sourceKind ? this.stop() : Promise.resolve();
    return p.then(function () {
      var body = { channels: self.allChannelIds, rates: self.rates };
      var pk = self._pickState();
      if (pk.off.length) body.channels = self.allChannelIds.filter(function (id) { return pk.off.indexOf(id) < 0; });
      // A value group is open: read just that set, so the whole group refreshes in one short cycle.
      var gc = self.root && self.root.getAttribute && self.root.getAttribute("data-group-channels");
      if (gc) {
        var want = gc.split(",");
        var only = body.channels.filter(function (id) { return want.indexOf(id) >= 0; });
        if (only.length) body.channels = only;
      }
      body.priorities = {};
      body.channels.forEach(function (id) { body.priorities[id] = pk.pri[id] || 1; });
      var cw = self.doc.getElementById("lb-codewatch");
      if (cw && cw.checked) { body.code_watch = true; body.code_watch_interval_s = 10; body.vin = self.vin || ""; }
      return self.api("/api/live/session/start", { method: "POST", body: JSON.stringify(body) });
    }).then(function (session) {
      self.sourceKind = "live";
      self.sessionActive = true;
      self.session = session;
      if (self.ESClass) {
        self.es = new self.ESClass(self.apiUrl("/api/live/stream"));
        self.es.onmessage = function (ev) { self._onStreamMessage(ev); };
      }
      self._setButtons();
    }).catch(function (err) {
      self._renderNoticeError("Could not start the live session: " + (err && err.message ? err.message : err));
    });
  };

  LiveboardApp.prototype._onStreamMessage = function (ev) {
    var msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.channel === undefined) return;
    this.onSample(msg.channel, msg.value, msg.unit);
  };

  LiveboardApp.prototype.startDemo = function () {
    var self = this;
    var p = this.sourceKind ? this.stop() : Promise.resolve();
    return p.then(function () {
      self.sourceKind = "demo";
      self.sessionActive = true;
      self._demoT0 = self.now();
      self._demoTimer = global.setInterval(function () { self._demoTick(); }, 400);
      self._demoTick();
      self._setButtons();
    });
  };

  LiveboardApp.prototype._demoTick = function () {
    var t = this.now() - this._demoT0;
    var d = demoDriveInputs(t);
    for (var i = 0; i < this.allChannelIds.length; i++) {
      var id = this.allChannelIds[i];
      var meta = this.channelsById[id];
      var r = demoValue(id, t, d, meta);
      this.onSample(id, r.value, r.unit || (meta && meta.unit) || "");
    }
  };

  LiveboardApp.prototype.stop = function () {
    if (this.es) { try { this.es.close(); } catch (e) {} this.es = null; }
    if (this._demoTimer) { global.clearInterval(this._demoTimer); this._demoTimer = null; }
    var wasLive = this.sourceKind === "live";
    this.sourceKind = null;
    this.sessionActive = false;
    this._setButtons();
    if (wasLive) return this.api("/api/live/session/stop", { method: "POST" }).catch(function () {});
    return Promise.resolve();
  };

  // A hook a test drives directly (``window.CuoreLiveboard.app.injectSample(...)``
  // via CDP Runtime.evaluate) to feed one specific sample without a real
  // adapter or the demo generator running.
  LiveboardApp.prototype.injectSample = function (id, value, unit) {
    var meta = this.channelsById[id];
    this.onSample(id, value, unit || (meta && meta.unit) || "");
  };

  // ---- samples / rendering ------------------------------------------------

  LiveboardApp.prototype.onSample = function (id, value, unit) {
    var meta = this.channelsById[id];
    var level = computeLevel(meta && meta.band, value);
    this.values[id] = { value: value, unit: unit || (meta && meta.unit) || "", level: level, t: this.now() };
    this._lastSampleAt = this.now();
    if (typeof value === "number" && !isNaN(value)) {
      var h = this.hist[id] || (this.hist[id] = []);
      h.push([this.now(), value]);
      if (h.length > 600) h.splice(0, h.length - 600);
    }
    this._renderChannel(id);
    this._renderProblems();
    this._syncUi();
  };

  LiveboardApp.prototype._renderGroups = function () {
    var root = this.doc.getElementById("lb-groups");
    if (!root) return;
    // The server already rendered the rows (one per quantity, search matches first); only values are ours.
    if (root.getAttribute("data-server") === "1") return;
    root.innerHTML = "";
    var self = this;
    this.groups.forEach(function (g) {
      var sec = self.doc.createElement("div");
      sec.className = "lb-group";
      sec.setAttribute("data-group", g.id || "");
      var head = self.doc.createElement("div");
      head.className = "lb-group-head";
      head.textContent = g.label || g.id || "Group";
      sec.appendChild(head);
      (g.channels || []).forEach(function (c) {
        var row = self.doc.createElement("div");
        row.className = "lb-chan level-unknown";
        row.id = "lb-chan-" + c.id;
        row.setAttribute("data-channel", c.id);
        var left = self.doc.createElement("div");
        left.className = "lb-chan-left";
        var name = self.doc.createElement("div");
        name.className = "lb-chan-name";
        name.textContent = c.name || c.id;
        var noteEl = self.doc.createElement("div");
        noteEl.className = "lb-chan-band";
        noteEl.textContent = bandNote(c.band, c.unit);
        left.appendChild(name);
        left.appendChild(noteEl);
        var right = self.doc.createElement("div");
        right.className = "lb-chan-right";
        var val = self.doc.createElement("span");
        val.className = "lb-chan-value";
        val.id = "lb-val-" + c.id;
        val.textContent = "—";
        var unitEl = self.doc.createElement("span");
        unitEl.className = "lb-chan-unit";
        unitEl.id = "lb-unit-" + c.id;
        unitEl.textContent = fmtUnit(c.unit);
        var stateEl = self.doc.createElement("span");
        stateEl.className = "lb-chan-state";
        stateEl.id = "lb-state-" + c.id;
        right.appendChild(stateEl);
        right.appendChild(val);
        right.appendChild(unitEl);
        row.appendChild(left);
        row.appendChild(right);
        sec.appendChild(row);
      });
      root.appendChild(sec);
    });
  };

  LiveboardApp.prototype._renderChannel = function (id) {
    var row = this.doc.getElementById("lb-chan-" + id);
    var valEl = this.doc.getElementById("lb-val-" + id);
    var unitEl = this.doc.getElementById("lb-unit-" + id);
    if (!row || !valEl) return;
    var v = this.values[id];
    row.className = "lb-chan level-" + (v ? v.level : "unknown") + (v ? " has-value" : "");
    valEl.textContent = (v && typeof v.value === "number" && !isNaN(v.value)) ? fmtValue(v.value) : (v ? "—" : "");
    if (unitEl && v && v.unit) unitEl.textContent = fmtUnit(v.unit);
    this._renderState(id);
  };

  // ---- empty-tile state: "waiting" (not polled yet) vs "no answer" -------

  LiveboardApp.prototype._txt = function (key, fallback) {
    var v = this.root && this.root.getAttribute && this.root.getAttribute("data-txt-" + key);
    return v || fallback;
  };

  // Seconds for one pass over every channel, from the session's own
  // attempt counts (answered or not); null until a few reads have happened.
  LiveboardApp.prototype._cycleSeconds = function () {
    var s = this.sessionInfo;
    if (!s || !s.active || !s.elapsed_s || !s.poll_attempts) return null;
    var total = 0;
    Object.keys(s.poll_attempts).forEach(function (k) { total += s.poll_attempts[k] || 0; });
    var n = (s.channels || []).length;
    if (!total || !n) return null;
    return s.elapsed_s * n / total;
  };

  LiveboardApp.prototype._renderState = function (id) {
    var row = this.doc.getElementById("lb-chan-" + id);
    var el = this.doc.getElementById("lb-state-" + id);
    if (!row || !el) return;
    var text = "", noanswer = false;
    var hasValue = !!this.values[id];
    var s = this.sessionInfo;
    // Only a real live session knows polling state; a demo feeds every
    // channel on its own, so there is nothing to wait for.
    if (!hasValue && this.sourceKind !== "demo" && s && s.active) {
      var err = s.last_error && s.last_error[id];
      var tries = s.poll_attempts && s.poll_attempts[id];
      if (err) {
        text = this._txt("noanswer", "no answer"); noanswer = true;
      } else if (!tries) {
        var ach = s.achieved_hz && s.achieved_hz[id];
        var secs = ach > 0 ? 1 / ach : this._cycleSeconds();
        text = this._txt("waiting", "waiting") + (secs ? " · ~" + Math.round(secs) + "s" : "");
      }
    }
    el.textContent = text;
    row.classList.toggle("is-noanswer", noanswer);
  };

  LiveboardApp.prototype._renderStates = function () {
    var self = this;
    this.allChannelIds.forEach(function (id) { self._renderState(id); });
    this._renderCycleLine();
  };

  LiveboardApp.prototype._renderCycleLine = function () {
    var el = this.doc.getElementById("lb-cycle");
    if (!el) return;
    var s = this.sessionInfo;
    if (!s || !s.active || this.sourceKind === "demo") { el.hidden = true; return; }
    var n = (s.channels || []).length;
    var cyc = this._cycleSeconds();
    var multi = s.multi_pid_supported;
    var parts = [
      n + " channels",
      "1 adapter",
      "multi-PID " + (multi === false ? "no" : multi === true ? "yes" : "?"),
      "full cycle ≈ " + (cyc ? Math.round(cyc) + "s" : "…")
    ];
    var bad = Object.keys(s.last_error || {}).length;
    var rpm = this.values.engine_rpm;
    var off = rpm && typeof rpm.value === "number" && rpm.value <= 0;
    parts.push((off ? "engine off: " : "") + bad + " channel" + (bad === 1 ? "" : "s") + " not answering");
    el.textContent = parts.join(" · ");
    el.hidden = false;
  };

  LiveboardApp.prototype._renderProblems = function () {
    var wrap = this.doc.getElementById("lb-problems");
    var list = this.doc.getElementById("lb-problems-list");
    if (!wrap || !list) return;
    var self = this;
    var rows = [];
    Object.keys(this.values).forEach(function (id) {
      var v = self.values[id];
      if (v.level === "excessive") rows.push({ id: id, meta: self.channelsById[id], v: v });
    });
    list.innerHTML = "";
    if (!rows.length) { wrap.hidden = true; return; }
    wrap.hidden = false;
    rows.forEach(function (r) {
      var row = self.doc.createElement("div");
      row.className = "lb-problem-row";
      row.setAttribute("data-channel", r.id);
      var name = self.doc.createElement("span");
      name.className = "lb-problem-name";
      name.textContent = (r.meta && r.meta.name) || r.id;
      var text = self.doc.createElement("span");
      text.className = "lb-problem-text";
      var note = bandNote(r.meta && r.meta.band, r.v.unit);
      text.textContent = fmtValue(r.v.value) + " " + fmtUnit(r.v.unit) + (note ? " — " + note : "");
      row.appendChild(name);
      row.appendChild(text);
      list.appendChild(row);
    });
  };

  // ---- staleness / status line -------------------------------------------

  LiveboardApp.prototype._startStaleTicker = function () {
    var self = this;
    this._staleTimer = global.setInterval(function () {
      self._tickStale();
      self._tickUpdatedLabel();
    }, 1000);
  };

  LiveboardApp.prototype._tickStale = function () {
    var self = this;
    var now = this.now();
    Object.keys(this.values).forEach(function (id) {
      var v = self.values[id];
      var row = self.doc.getElementById("lb-chan-" + id);
      if (!row) return;
      row.classList.toggle("is-stale", self._offline() || (now - v.t) * 1000 > STALE_MS);
    });
    this._renderOffline();
    this.allChannelIds.forEach(function (id) { self._renderStatus(id); });
    this._renderGraph();
  };

  // ---- live or not: old values must never look live ----------------------

  // true when readings are held on the page but nothing is feeding them from the car
  LiveboardApp.prototype._offline = function () {
    if (this.sourceKind === "demo") return false;
    if (!Object.keys(this.values).length) return false;
    return !(this.sourceKind === "live" || (this.sessionInfo && this.sessionInfo.active));
  };

  LiveboardApp.prototype._renderOffline = function () {
    var el = this.doc.getElementById("lb-offline");
    if (!el) return;
    var text = "";
    if (this.sourceKind === "demo") text = "DEMO: made-up numbers, not from the car.";
    else if (this._offline()) text = "NOT CONNECTED to the car. The values shown are the last ones received, not live.";
    el.textContent = text;
    el.hidden = !text;
    el.className = "lb-notice lb-offline" + (this.sourceKind === "demo" ? " is-demo" : " is-offline");
  };

  // One plain word per row: No reading / Confirmed / Unconfirmed, and where the band comes from.
  LiveboardApp.prototype._renderStatus = function (id) {
    var row = this.doc.getElementById("lb-chan-" + id);
    if (!row) return;
    var left = row.querySelector(".lb-chan-left");
    if (!left) return;
    var el = row.querySelector(".lb-vstat");
    if (!el) { el = this.doc.createElement("div"); el.className = "lb-vstat"; left.appendChild(el); }
    var v = this.values[id], meta = this.channelsById[id], b = meta && meta.band;
    var active = this.sourceKind || (this.sessionInfo && this.sessionInfo.active);
    var st = "", text = "";
    var stale = v && (this._offline() || (this.now() - v.t) * 1000 > STALE_MS);
    if (!active && !v) { el.textContent = ""; el.removeAttribute("data-status"); return; }
    if (!v || stale || typeof v.value !== "number" || isNaN(v.value)) {
      st = "none"; text = "No reading" + (stale ? " (last value " + Math.round(this.now() - v.t) + " s old)" : "");
    } else {
      var conf = String((b && b.confidence) || "").toUpperCase().replace(/_/g, "-");
      var src = b && b.source ? " Band source: " + b.source + "." : (b ? " Band source: not named." : " No band on file.");
      if (conf === "CORROBORATED") { st = "confirmed"; text = "Confirmed (2+ sources)." + src; }
      else { st = "unconfirmed"; text = "Unconfirmed" + (conf === "SINGLE-SOURCE" ? " (one source)." : ".") + src; }
    }
    el.setAttribute("data-status", st);
    el.textContent = text;
  };

  // ---- graph several values against time ---------------------------------

  LiveboardApp.prototype._graphKey = function () { return "cuore.lb.graph." + (this.vin || "demo"); };
  LiveboardApp.prototype._graphIds = function () {
    try { return JSON.parse(global.localStorage.getItem(this._graphKey()) || "[]") || []; } catch (e) { return this._graphSel || []; }
  };
  LiveboardApp.prototype._graphSave = function (ids) {
    this._graphSel = ids;
    try { global.localStorage.setItem(this._graphKey(), JSON.stringify(ids)); } catch (e) { /* ignore */ }
  };

  LiveboardApp.prototype._renderGraph = function () {
    var box = this.doc.getElementById("lb-graph");
    if (!box) return;
    var ids = this._graphIds(), self = this, W = 600, H = 70, SPAN = 60, t1 = this.now(), t0 = t1 - SPAN;
    box.hidden = !ids.length;
    if (!ids.length) { box.innerHTML = ""; return; }
    var html = ["<div class=\"lb-graph-head\">Graph, last " + SPAN + " s, one strip per value (each has its own scale)</div>"];
    ids.forEach(function (id) {
      var meta = self.channelsById[id] || {}, pts = (self.hist[id] || []).filter(function (p) { return p[0] >= t0; });
      var name = meta.name || id, unit = fmtUnit(meta.unit || "");
      if (!pts.length) { html.push("<div class=\"lb-gstrip\"><b>" + name + "</b>: No reading in the last " + SPAN + " s</div>"); return; }
      var lo = Math.min.apply(null, pts.map(function (p) { return p[1]; })), hi = Math.max.apply(null, pts.map(function (p) { return p[1]; }));
      if (hi === lo) { hi += 1; lo -= 1; }
      var d = pts.map(function (p) { return (((p[0] - t0) / SPAN) * W).toFixed(1) + "," + (H - 6 - ((p[1] - lo) / (hi - lo)) * (H - 12)).toFixed(1); }).join(" ");
      var marks = self.tags.filter(function (t) { return t.t >= t0; }).map(function (t) {
        var x = (((t.t - t0) / SPAN) * W).toFixed(1);
        return "<line class=\"lb-gtag\" x1=\"" + x + "\" x2=\"" + x + "\" y1=\"0\" y2=\"" + H + "\"></line>";
      }).join("");
      html.push("<div class=\"lb-gstrip\"><b>" + name + "</b> " + fmtNum(lo) + " to " + fmtNum(hi) + " " + unit +
        "<svg viewBox=\"0 0 " + W + " " + H + "\" role=\"img\" aria-label=\"" + name + " against time\"><polyline class=\"lb-gline\" points=\"" + d + "\"></polyline>" + marks + "</svg></div>");
    });
    if (this.tags.length) html.push("<div class=\"lb-gnote\">Tags: " + this.tags.slice(-6).map(function (t) { return t.label; }).join(", ") + "</div>");
    box.innerHTML = html.join("");
  };

  // ---- record, one-tap tags, graph picks ----------------------------------

  LiveboardApp.prototype._setRecording = function (on) {
    this.recording = on;
    var tags = this.doc.getElementById("lb-tags"), stop = this.doc.getElementById("lb-record-stop"),
        rec = this.doc.getElementById("lb-record");
    if (tags) tags.hidden = !on;
    if (stop) stop.hidden = !on;
    if (rec) rec.hidden = on;
  };

  LiveboardApp.prototype._say = function (text) {
    var n = this.doc.getElementById("lb-notice");
    if (n) { n.textContent = text; n.hidden = !text; }
  };

  LiveboardApp.prototype._postForm = function (url, fields) {
    var body = new URLSearchParams(fields || {}).toString();
    return this.fetchFn(this.apiUrl(url), { method: "POST", body: body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" } }).then(function (r) {
      var m = /[?&]msg=([^&]*)/.exec(r.url || ""); return m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : (r.ok ? "done" : "failed");
    });
  };

  LiveboardApp.prototype._wireGraphTagsRecord = function () {
    var self = this, d = this.doc;
    function all(sel) { return Array.prototype.slice.call(d.querySelectorAll(sel)); }
    var sel = this._graphIds();
    all(".lb-graph-box").forEach(function (b) { b.checked = sel.indexOf(b.getAttribute("data-graph")) >= 0; });
    d.addEventListener("change", function (ev) {
      var t = ev.target;
      if (!t.classList || !t.classList.contains("lb-graph-box")) return;
      var id = t.getAttribute("data-graph"), ids = self._graphIds().filter(function (x) { return x !== id; });
      if (t.checked) ids.push(id);
      if (ids.length > 6) { ids = ids.slice(-6); self._say("Graph shows at most 6 values; the oldest pick was dropped."); }
      all(".lb-graph-box").forEach(function (b) { b.checked = ids.indexOf(b.getAttribute("data-graph")) >= 0; });
      self._graphSave(ids);
      self._renderGraph();
    });
    var form = d.getElementById("lb-record-form");
    if (form) form.addEventListener("submit", function (ev) {
      if (!self.fetchFn) return;
      ev.preventDefault();
      self._postForm(form.getAttribute("action"), { label: "" }).then(function (msg) {
        self._say(msg); self._setRecording(/^Recording .* started/.test(msg));
      }).catch(function () { self._say("Could not start the recording."); });
    });
    var stop = d.getElementById("lb-record-stop");
    if (stop) stop.addEventListener("click", function () {
      self._postForm("/v/" + encodeURIComponent(self.vin) + "/recordings/stop", {}).then(function (msg) {
        self._say(msg + " Replay it from Recordings."); self._setRecording(false);
      }).catch(function () { self._say("Could not stop the recording."); });
    });
    var tagBox = d.getElementById("lb-tags");
    if (tagBox && this.vin && this.fetchFn) this.api("/api/live/record/tag-labels?vin=" + encodeURIComponent(this.vin)).then(function (r) {
      var holder = tagBox.querySelector(".lb-tag-btns");
      holder.innerHTML = "";
      Object.keys(r.labels || {}).sort().forEach(function (k) {
        var label = r.labels[k]; if (!label) return;
        var b = d.createElement("button"); b.type = "button"; b.className = "lb-btn lb-tag"; b.setAttribute("data-tag", k);
        b.textContent = label; holder.appendChild(b);
      });
    }).catch(function () { /* labels stay empty: no tag buttons */ });
    if (tagBox) tagBox.addEventListener("click", function (ev) {
      var b = ev.target.closest && ev.target.closest("[data-tag]"); if (!b) return;
      self.api("/api/live/record/tag", { method: "POST", body: JSON.stringify({ key: b.getAttribute("data-tag"), vin: self.vin }) })
        .then(function () { self.tags.push({ t: self.now(), key: b.getAttribute("data-tag"), label: b.textContent }); self._say("Tagged: " + b.textContent); self._renderGraph(); })
        .catch(function (e) { self._say(e && e.status === 409 ? "Not recording: press Record this drive first." : "Tag failed."); });
    });
  };

  LiveboardApp.prototype._tickUpdatedLabel = function () {
    var el = this.doc.getElementById("lb-status-updated");
    if (!el) return;
    if (!this._lastSampleAt) { el.textContent = "no readings yet"; return; }
    var secs = Math.max(0, Math.round(this.now() - this._lastSampleAt));
    el.textContent = "updated " + secs + "s ago";
  };

  LiveboardApp.prototype._pollSessionStatus = function () {
    var self = this;
    this.api("/api/live/status").then(function (s) { self._renderAdapterChip(s); })
      .catch(function () { self._renderAdapterChip(null); });
    this.api("/api/live/session").then(function (s) { self.sessionInfo = s; self._renderPickRates(s); self._renderSessionChip(s); self._renderStates(); self._syncUi(); })
      .catch(function () { self.sessionInfo = null; self._renderSessionChip(null); self._renderStates(); });
  };

  // ---- recording picker: per-channel tick + priority 1-5, Select all/none --
  // Saved in localStorage per VIN as {off: [unticked ids], pri: {id: n}}; new channels default to ticked.
  LiveboardApp.prototype._pickKey = function () { return "cuore.lb.pick." + (this.vin || "demo"); };

  LiveboardApp.prototype._pickState = function () {
    var st = { off: [], pri: {} };
    try {
      var raw = global.localStorage && global.localStorage.getItem(this._pickKey());
      var v = raw ? JSON.parse(raw) : null;
      if (v && v.off) st.off = v.off;
      if (v && v.pri) st.pri = v.pri;
    } catch (e) { /* storage blocked: defaults */ }
    return st;
  };

  LiveboardApp.prototype._pickSave = function () {
    var st = { off: [], pri: {} };
    var d = this.doc;
    Array.prototype.forEach.call(d.querySelectorAll(".lb-pick-box"), function (b) {
      var id = b.getAttribute("data-pick");
      if (!b.checked && st.off.indexOf(id) < 0) st.off.push(id);
    });
    Array.prototype.forEach.call(d.querySelectorAll(".lb-pick-sel"), function (s) {
      if (s.value !== "1") st.pri[s.getAttribute("data-pri")] = parseInt(s.value, 10);
    });
    try { global.localStorage.setItem(this._pickKey(), JSON.stringify(st)); } catch (e) { /* ignore */ }
  };

  LiveboardApp.prototype._wirePicker = function () {
    var self = this, d = this.doc, st = this._pickState();
    function all(sel, root) { return Array.prototype.slice.call((root || d).querySelectorAll(sel)); }
    all(".lb-pick, .lb-selbar, .lb-pick-help").forEach(function (el) { el.hidden = false; });
    all(".lb-pick-box").forEach(function (b) { b.checked = st.off.indexOf(b.getAttribute("data-pick")) < 0; });
    all(".lb-pick-sel").forEach(function (s) { s.value = String(st.pri[s.getAttribute("data-pri")] || 1); });
    d.addEventListener("change", function (ev) {
      var t = ev.target;
      if (!t.classList) return;
      var isBox = t.classList.contains("lb-pick-box");
      if (!isBox && !t.classList.contains("lb-pick-sel")) return;
      var id = t.getAttribute(isBox ? "data-pick" : "data-pri");
      // the same channel can appear twice (matches + group): keep copies in step
      all((isBox ? ".lb-pick-box[data-pick=\"" : ".lb-pick-sel[data-pri=\"") + id + "\"]").forEach(function (o) {
        if (isBox) o.checked = t.checked; else o.value = t.value;
      });
      self._pickSave();
    });
    d.addEventListener("click", function (ev) {
      var b = ev.target.closest && ev.target.closest("[data-select]");
      if (!b) return;
      var on = b.getAttribute("data-select") === "all";
      var scope = b.getAttribute("data-scope") === "group" ? b.closest("details") : d;
      all(".lb-pick-box", scope).forEach(function (x) {
        all(".lb-pick-box[data-pick=\"" + x.getAttribute("data-pick") + "\"]").forEach(function (o) { o.checked = on; });
      });
      self._pickSave();
    });
  };

  LiveboardApp.prototype._renderPickRates = function (s) {
    var cr = (s && s.channel_rates) || {};
    Array.prototype.forEach.call(this.doc.querySelectorAll(".lb-pick-rate"), function (el) {
      var r = cr[el.getAttribute("data-rate")];
      el.textContent = r ? ("configured " + (r.configured_hz == null ? "-" : Number(r.configured_hz).toFixed(1)) +
        " Hz, achieved " + (r.achieved_hz == null ? "-" : Number(r.achieved_hz).toFixed(1)) + " Hz") : "";
    });
  };

  LiveboardApp.prototype._renderAdapterChip = function (s) {
    var el = this.doc.getElementById("lb-status-adapter");
    if (!el) return;
    if (!s || s.error) { el.textContent = "adapter: not found"; el.className = "lb-status-chip"; return; }
    var mesState = (s.mes && s.mes.state) || "unknown";
    // MES holding the adapter blocks CUORE; any other MES state is fine.
    el.textContent = mesState === "connected" ? "MultiEcuScan has the adapter - close it first"
      : mesState === "unknown" ? "adapter: state unknown" : "adapter: free";
    el.className = "lb-status-chip " + (mesState === "connected" ? "is-warn" : "is-ok");
  };

  LiveboardApp.prototype._renderSessionChip = function (s) {
    var el = this.doc.getElementById("lb-status-session");
    if (!el) return;
    var active = !!(s && s.active);
    if (this.sourceKind === "demo") { el.textContent = "demo (made-up numbers)"; el.className = "lb-status-chip is-ok"; return; }
    el.textContent = active ? "session running" : "no session";
    el.className = "lb-status-chip " + (active ? "is-ok" : "");
  };

  // ---- snapshot ------------------------------------------------------------

  // ``POST /api/live/snapshots`` wants ``{id: {value, unit}}``; the two
  // ``/api/liveboard/*`` routes want ``{id: number}`` -- both built from
  // the same ``this.values`` in one pass so they can never disagree.
  LiveboardApp.prototype.snapshot = function () {
    var self = this;
    // F3 (MECHANIC_REVIEW_3): mirror systems_map.js's takeSnapshot guard --
    // refuse honestly on zero live channels instead of POSTing an empty
    // "success" with no channel count and no recommendations.
    if (!Object.keys(this.values).length) {
      var el = this.doc.getElementById("lb-snapshot-result");
      if (el) {
        el.hidden = false;
        el.textContent = "No live readings to snapshot yet.";
      }
      return Promise.resolve();
    }
    var liveValues = {}, flatValues = {};
    Object.keys(this.values).forEach(function (id) {
      var v = self.values[id];
      liveValues[id] = { value: v.value, unit: v.unit || "" };
      flatValues[id] = v.value;
    });
    var body = {
      layout: "liveboard", page: "liveboard",
      source: this.sourceKind === "demo" ? "demo" : "live",
      values: liveValues, note: "",
    };
    return this.api("/api/live/snapshots", { method: "POST", body: JSON.stringify(body) })
      .then(function (saved) {
        return self.api("/api/liveboard/evaluate", { method: "POST", body: JSON.stringify({ values: flatValues }) })
          .catch(function () { return null; })
          .then(function (resp) {
            var recs = (resp && resp.recommendations) || [];
            self._renderSnapshotResult(saved, recs);
            return self._afterSnapshot(saved, flatValues);
          });
      })
      .catch(function (err) { self._renderSnapshotError(err); });
  };

  LiveboardApp.prototype._afterSnapshot = function (saved, flatValues) {
    var self = this;
    var snapId = saved && saved.id;
    return this.api("/api/liveboard/" + encodeURIComponent(this.vin) + "/snapshot-to-job", {
      method: "POST", body: JSON.stringify({ snapshot_id: snapId, values: flatValues }),
    }).then(function (result) { self._renderJobLine(result); })
      .catch(function () { /* tolerate 404/400 -- no open job, or the route hasn't landed */ });
  };

  LiveboardApp.prototype._renderSnapshotResult = function (saved, recs) {
    var el = this.doc.getElementById("lb-snapshot-result");
    if (!el) return;
    el.hidden = false;
    el.innerHTML = "";
    var h = this.doc.createElement("h3");
    h.textContent = "Snapshot saved";
    var idEl = this.doc.createElement("div");
    idEl.className = "lb-snapshot-id";
    idEl.id = "lb-snapshot-id";
    idEl.textContent = (saved && saved.id) || "";
    el.appendChild(h);
    el.appendChild(idEl);
    var sorted = (recs || []).slice().sort(function (a, b) { return levelRank(b.level) - levelRank(a.level); });
    var self = this;
    sorted.forEach(function (r) {
      var row = self.doc.createElement("div");
      row.className = "lb-rec-row";
      var lvl = self.doc.createElement("span");
      lvl.className = "lb-rec-level level-" + (r.level || "unknown");
      lvl.textContent = r.level || "unknown";
      var txt = self.doc.createElement("span");
      txt.className = "lb-rec-text";
      txt.textContent = (r.name || r.id || "") + ": " + (r.text || "");
      row.appendChild(lvl);
      row.appendChild(txt);
      el.appendChild(row);
    });
  };

  // ``result`` is ``cuore.services.liveboard_bridge.attach_snapshot_to_job``'s
  // return: ``{job_id, out_of_range, attached: [{hyp_id, ref}], new_hypotheses:
  // [{id, text, ...}]}``. ``attached.length`` is "N evidence items"; the
  // hypothesis names are read off ``new_hypotheses`` (the only place a name
  // travels back for a hypothesis this pass just seeded) with the bare id
  // as a fallback for one that already existed and is only named by id here.
  LiveboardApp.prototype._renderJobLine = function (result) {
    var el = this.doc.getElementById("lb-snapshot-result");
    if (!el || !result) return;
    var attached = result.attached || [];
    if (!attached.length) return;
    var byId = {};
    (result.new_hypotheses || []).forEach(function (h) { byId[h.id] = h.text || h.id; });
    var seen = {}, names = [];
    attached.forEach(function (a) {
      var hid = a.hyp_id;
      if (!hid || seen[hid]) return;
      seen[hid] = true;
      names.push(byId[hid] || hid);
    });
    var n = attached.length;
    var line = this.doc.createElement("div");
    line.className = "lb-job-line";
    line.id = "lb-job-line";
    var text = "Added to the Job: " + n + " evidence item" + (n === 1 ? "" : "s");
    if (names.length) text += " on " + names.join(", ");
    var a = this.doc.createElement("a");
    a.href = "/v/" + encodeURIComponent(this.vin) + "/job?step=7";
    a.textContent = text;
    line.appendChild(a);
    el.appendChild(line);
  };

  LiveboardApp.prototype._renderSnapshotError = function (err) {
    var el = this.doc.getElementById("lb-snapshot-result");
    if (!el) return;
    el.hidden = false;
    el.textContent = "Snapshot failed: " + (err && err.message ? err.message : err);
  };

  // -----------------------------------------------------------------------

  var app = null;

  function init(opts) {
    app = new LiveboardApp(opts);
    global.CuoreLiveboard.app = app;
    return app.init();
  }

  global.CuoreLiveboard = global.CuoreLiveboard || {};
  global.CuoreLiveboard.init = init;
  global.CuoreLiveboard.LiveboardApp = LiveboardApp;
  global.CuoreLiveboard.computeLevel = computeLevel;
  global.CuoreLiveboard.bandNote = bandNote;
  global.CuoreLiveboard.FIXTURE_GROUPS = FIXTURE_GROUPS;

})(typeof window !== "undefined" ? window : globalThis);

/* ---------------------------------------------------------------------------
 * Freeze frame panel -- Start/Stop a server-side capture (Mode 03 stored
 * codes, then every supported PID's freeze frame + a Mode 01 snapshot, plus
 * readiness; cuore/services/liveboard_bridge.py's freeze_capture_* group),
 * show it unsaved on the page, Save it into the CUORE log.
 *
 * Deliberately its own small IIFE/global (CuoreFreezeFrame), independent of
 * CuoreLiveboard above: the panel doesn't need the channel/band contract or
 * the live-session plumbing, just its own four endpoints under
 * /api/liveboard/{vin}/freeze/*. Start/Stop/polling need JS; Save is a real
 * <form> (#ff-save-form) so it still works with JS off -- this module only
 * intercepts that submit for a nicer inline result when JS *is* available.
 * ---------------------------------------------------------------------------
 */
(function (global) {
  "use strict";

  var POLL_MS = 600;

  function FreezeFramePanel(opts) {
    opts = opts || {};
    this.fetchFn = opts.fetch || (global.fetch ? global.fetch.bind(global) : null);
    this.doc = opts.document || document;
    this.root = opts.root || this.doc.getElementById("ff-panel");
    this.vin = opts.vin || (this.root && this.root.getAttribute("data-vin")) || "";
    this.token = opts.token || this._tokenFromLocation();
    this.captureId = null;
    this._pollTimer = null;
  }

  FreezeFramePanel.prototype._tokenFromLocation = function () {
    try {
      var q = new URLSearchParams(global.location.search);
      return q.get("token") || "";
    } catch (e) { return ""; }
  };

  FreezeFramePanel.prototype.apiUrl = function (path) {
    if (!this.token) return path;
    return path + (path.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(this.token);
  };

  FreezeFramePanel.prototype.api = function (path, options) {
    var self = this;
    options = options || {};
    if (!this.fetchFn) return Promise.reject(new Error("no fetch available"));
    return this.fetchFn(this.apiUrl(path), options).then(function (resp) {
      return resp.text().then(function (text) {
        var body = null;
        try { body = text ? JSON.parse(text) : null; } catch (e) { body = text; }
        if (!resp.ok) {
          var err = new Error((body && body.detail) || resp.statusText || ("HTTP " + resp.status));
          err.status = resp.status; err.body = body;
          throw err;
        }
        return body;
      });
    });
  };

  FreezeFramePanel.prototype._el = function (id) { return this.doc.getElementById(id); };

  FreezeFramePanel.prototype.init = function () {
    var self = this;
    var startBtn = this._el("ff-start");
    var stopBtn = this._el("ff-stop");
    var discardBtn = this._el("ff-discard");
    var saveForm = this._el("ff-save-form");
    if (startBtn) startBtn.addEventListener("click", function () { self.start(); });
    if (stopBtn) stopBtn.addEventListener("click", function () { self.stop(); });
    if (discardBtn) discardBtn.addEventListener("click", function () { self.discard(); });
    if (saveForm) saveForm.addEventListener("submit", function (ev) { self._onSaveSubmit(ev); });
  };

  // ---- Start / poll / Stop ------------------------------------------------

  FreezeFramePanel.prototype.start = function () {
    var self = this;
    var startBtn = this._el("ff-start");
    if (startBtn) { startBtn.disabled = true; startBtn.textContent = "Capturing…"; }
    this._clearResult();
    this._setStatus("Capturing…", false);
    return this.api("/api/liveboard/" + encodeURIComponent(this.vin) + "/freeze/capture",
      { method: "POST" })
      .then(function (cap) {
        self.captureId = cap.id;
        self._render(cap);
        if (cap.status === "running") {
          self._showStop(true);
          self._poll();
        } else {
          self._onCaptureSettled(cap);
        }
      })
      .catch(function (err) {
        if (startBtn) { startBtn.disabled = false; startBtn.textContent = "Start"; }
        self._setStatus("Could not start the capture: " + (err && err.message ? err.message : err), true);
      });
  };

  FreezeFramePanel.prototype._poll = function () {
    var self = this;
    this._pollTimer = global.setTimeout(function () {
      if (!self.captureId) return;
      self.api("/api/liveboard/" + encodeURIComponent(self.vin) + "/freeze/status" +
               "?capture_id=" + encodeURIComponent(self.captureId))
        .then(function (cap) {
          self._render(cap);
          if (cap.status === "running") {
            self._poll();
          } else {
            self._onCaptureSettled(cap);
          }
        })
        .catch(function (err) {
          self._setStatus("Lost the capture: " + (err && err.message ? err.message : err), true);
        });
    }, POLL_MS);
  };

  FreezeFramePanel.prototype.stop = function () {
    if (!this.captureId) return Promise.resolve();
    var self = this;
    var stopBtn = this._el("ff-stop");
    if (stopBtn) stopBtn.disabled = true;
    return this.api("/api/liveboard/" + encodeURIComponent(this.vin) + "/freeze/stop",
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capture_id: this.captureId }) })
      .catch(function () { /* the next poll tick will show the real state either way */ });
  };

  FreezeFramePanel.prototype._onCaptureSettled = function (cap) {
    var startBtn = this._el("ff-start");
    var stopBtn = this._el("ff-stop");
    if (startBtn) { startBtn.disabled = false; startBtn.textContent = "Start"; }
    this._showStop(false);
    if (cap.error) {
      this._setStatus("Capture error: " + cap.error, true);
      return;
    }
    if (!cap.codes || !cap.codes.length) {
      this._setStatus(cap.note || "No stored codes right now; nothing captured.", false);
      return;
    }
    var label = cap.partial
      ? "Capture stopped early (partial) — Not saved yet."
      : "Capture complete — Not saved yet.";
    this._setStatus(label, false, true);
    this._el("ff-discard").hidden = false;
    var saveBtn = this._el("ff-save");
    if (saveBtn) {
      saveBtn.hidden = false;
      this._el("ff-save-capture-id").value = cap.id;
    }
  };

  // ---- Discard -------------------------------------------------------------

  FreezeFramePanel.prototype.discard = function () {
    if (!this.captureId) return Promise.resolve();
    var self = this;
    return this.api("/api/liveboard/" + encodeURIComponent(this.vin) + "/freeze/discard",
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capture_id: this.captureId }) })
      .catch(function () { /* discarding a capture that already expired is fine too */ })
      .then(function () { self._reset(); });
  };

  FreezeFramePanel.prototype._reset = function () {
    this.captureId = null;
    if (this._pollTimer) { global.clearTimeout(this._pollTimer); this._pollTimer = null; }
    this._showStop(false);
    this._el("ff-discard").hidden = true;
    var saveBtn = this._el("ff-save");
    if (saveBtn) saveBtn.hidden = true;
    this._el("ff-save-capture-id").value = "";
    var tables = this._el("ff-tables");
    if (tables) { tables.hidden = true; tables.innerHTML = ""; }
    var status = this._el("ff-status");
    if (status) status.hidden = true;
    this._clearResult();
  };

  // ---- Save (works with JS off too -- this just makes it inline) ----------

  FreezeFramePanel.prototype._onSaveSubmit = function (ev) {
    if (!this.fetchFn || !global.FormData) return; // let the native form post happen
    ev.preventDefault();
    var self = this;
    var form = this._el("ff-save-form");
    var saveBtn = this._el("ff-save");
    if (saveBtn) saveBtn.disabled = true;
    this.fetchFn(form.action, { method: "POST", body: new FormData(form) })
      .then(function (resp) {
        return resp.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (e) { body = text; }
          if (!resp.ok) {
            var err = new Error((body && body.detail) || resp.statusText);
            err.body = body; throw err;
          }
          return body;
        });
      })
      .then(function (saved) { self._renderSaved(saved); })
      .catch(function (err) {
        if (saveBtn) saveBtn.disabled = false;
        self._renderSaveError(err);
      });
  };

  FreezeFramePanel.prototype._renderSaved = function (saved) {
    var saveBtn = this._el("ff-save");
    var discardBtn = this._el("ff-discard");
    if (saveBtn) saveBtn.hidden = true;
    if (discardBtn) discardBtn.hidden = true;
    this._setStatus("Saved to the CUORE log.", false);
    var el = this._el("ff-result");
    if (!el) return;
    el.hidden = false;
    el.classList.remove("is-error");
    el.innerHTML = "";
    el.appendChild(this.doc.createTextNode(
      "Saved to the CUORE log — " + (saved && saved.scan_id || "")));
    var a = this.doc.createElement("a");
    a.href = (saved && saved.scans_url) || ("/v/" + encodeURIComponent(this.vin) + "/scans/" +
      encodeURIComponent((saved && saved.scan_id) || ""));
    a.textContent = "open in Scans";
    el.appendChild(this.doc.createTextNode(" · "));
    el.appendChild(a);
  };

  FreezeFramePanel.prototype._renderSaveError = function (err) {
    var el = this._el("ff-result");
    if (!el) return;
    el.hidden = false;
    el.classList.add("is-error");
    el.textContent = "Save failed: " + (err && err.message ? err.message : err);
  };

  // ---- rendering -----------------------------------------------------------

  FreezeFramePanel.prototype._showStop = function (show) {
    var stopBtn = this._el("ff-stop");
    if (!stopBtn) return;
    stopBtn.hidden = !show;
    stopBtn.disabled = false;
  };

  FreezeFramePanel.prototype._setStatus = function (text, isError, isUnsaved) {
    var el = this._el("ff-status");
    if (!el) return;
    el.hidden = false;
    el.textContent = text;
    el.classList.toggle("is-error", !!isError);
    el.classList.toggle("is-unsaved", !!isUnsaved);
  };

  FreezeFramePanel.prototype._clearResult = function () {
    var el = this._el("ff-result");
    if (el) { el.hidden = true; el.textContent = ""; el.classList.remove("is-error"); }
  };

  function fmtVal(v) {
    if (typeof v === "number") return (Math.round(v * 100) / 100).toString();
    return v === null || v === undefined ? "—" : String(v);
  }

  // One table per {code, ecu} -- PID, name, value, unit -- captioned with
  // the capture time and the "read from the car" label the owner asked for
  // explicitly (this is live-adapter data, never a replay/demo value).
  FreezeFramePanel.prototype._render = function (cap) {
    var wrap = this._el("ff-tables");
    if (!wrap) return;
    var rowsAny = (cap.frame_tables || []).some(function (t) { return (t.rows || []).length; });
    if (!rowsAny) { wrap.hidden = true; wrap.innerHTML = ""; return; }
    wrap.hidden = false;
    wrap.innerHTML = "";
    var self = this;
    (cap.frame_tables || []).forEach(function (t) {
      if (!t.rows || !t.rows.length) return;
      var box = self.doc.createElement("div");
      box.className = "ff-frame-table";
      var head = self.doc.createElement("div");
      head.className = "ff-frame-head";
      var codeLabel = t.code ? ("Freeze frame — " + t.code) : "Freeze frame";
      head.appendChild(self.doc.createTextNode(codeLabel + (t.ecu ? " (" + t.ecu + ")" : "") + " "));
      var meta = self.doc.createElement("span");
      meta.className = "ff-frame-meta";
      meta.textContent = "captured " + (cap.started_at || "") + " — read from the car";
      head.appendChild(meta);
      box.appendChild(head);
      var table = self.doc.createElement("table");
      table.className = "ff-table";
      var thead = self.doc.createElement("tr");
      ["PID", "Name", "Value", "Unit"].forEach(function (h) {
        var th = self.doc.createElement("th");
        th.textContent = h;
        thead.appendChild(th);
      });
      table.appendChild(thead);
      t.rows.forEach(function (r) {
        var tr = self.doc.createElement("tr");
        var tdPid = self.doc.createElement("td"); tdPid.textContent = r.pid || "";
        var tdName = self.doc.createElement("td"); tdName.textContent = r.name || "";
        var tdVal = self.doc.createElement("td"); tdVal.className = "ff-val";
        tdVal.textContent = fmtVal(r.value);
        var tdUnit = self.doc.createElement("td"); tdUnit.textContent = r.unit || "";
        tr.appendChild(tdPid); tr.appendChild(tdName); tr.appendChild(tdVal); tr.appendChild(tdUnit);
        table.appendChild(tr);
      });
      box.appendChild(table);
      wrap.appendChild(box);
    });
  };

  var panel = null;

  function init(opts) {
    panel = new FreezeFramePanel(opts);
    global.CuoreFreezeFrame.panel = panel;
    return panel.init();
  }

  global.CuoreFreezeFrame = global.CuoreFreezeFrame || {};
  global.CuoreFreezeFrame.init = init;
  global.CuoreFreezeFrame.FreezeFramePanel = FreezeFramePanel;

})(typeof window !== "undefined" ? window : globalThis);


// ===========================================================================
// ADDITIVE: Cable header + Bus capture panel + per-bus presets
// (cuore/api/buscapture.py -- cable declaration, passive bus capture,
// learn-a-signal and per-bus presets). New section, does not touch
// anything above this line.
// ===========================================================================

(function (global) {
  "use strict";

  function api(method, path, body) {
    var opts = { method: method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
    });
  }

  // ---------------------------------------------------------------------
  // Cable header
  // ---------------------------------------------------------------------

  function CableHeader(doc) {
    this.doc = doc || document;
  }

  CableHeader.prototype._el = function (id) { return this.doc.getElementById(id); };

  CableHeader.prototype.init = function () {
    var self = this;
    var change = this._el("bc-cable-change");
    if (change) change.addEventListener("click", function () { self._changeCable(); });
    return this.refresh();
  };

  CableHeader.prototype.refresh = function () {
    var self = this;
    return api("GET", "/api/buscapture/cable").then(function (res) {
      if (res.ok) self._render(res.body);
    });
  };

  CableHeader.prototype._render = function (state) {
    var header = this._el("bc-cable-header");
    if (!header) return;
    header.hidden = false;
    var bar = this._el("bc-cable-bar");
    if (bar) bar.className = "bc-cable-bar cable-" + state.cable;
    var label = this._el("bc-cable-label");
    if (label) label.textContent = "cable: " + state.cable;
    var buses = this._el("bc-cable-buses");
    if (buses) {
      buses.innerHTML = "";
      var self2 = this;
      (state.buses || []).forEach(function (b) {
        var chip = self2.doc.createElement("span");
        chip.className = "bc-bus-chip" + (b.reachable_with_cable ? " is-reachable" : "");
        chip.textContent = b.bus;
        buses.appendChild(chip);
      });
    }
  };

  CableHeader.prototype._changeCable = function () {
    var self = this;
    api("GET", "/api/buscapture/cable").then(function (res) {
      if (!res.ok) return;
      var options = ["none", "blue_a5", "grey_a6"];
      var enabled = (res.body.presets || []).map(function (p) {
        return p.preset + " needs " + p.cable_required;
      }).join("; ");
      var next = global.prompt(
        "Declare the fitted cable (none, blue_a5, grey_a6).\n" + enabled,
        res.body.cable || "none");
      if (!next || options.indexOf(next) === -1) return;
      api("POST", "/api/buscapture/cable", { cable: next }).then(function (res2) {
        if (res2.ok) self._render(res2.body);
      });
    });
  };

  global.CuoreCableHeader = global.CuoreCableHeader || {};
  global.CuoreCableHeader.init = function (doc) { return new CableHeader(doc).init(); };
  global.CuoreCableHeader.CableHeader = CableHeader;

  // ---------------------------------------------------------------------
  // Bus capture panel: Start / Stop / Save, live frame-rate + id counts,
  // plus the per-bus preset list (chassis_a6 / body_a5).
  // ---------------------------------------------------------------------

  function BusCapturePanel(doc) {
    this.doc = doc || document;
    var panelEl = this._el("bc-panel");
    this.vin = (panelEl && panelEl.dataset) ? panelEl.dataset.vin : "";
    this.pollTimer = null;
  }

  BusCapturePanel.prototype._el = function (id) { return this.doc.getElementById(id); };

  BusCapturePanel.prototype.init = function () {
    var self = this;
    var bus = this._el("bc-bus");
    if (bus) bus.addEventListener("change", function () { self._renderBusName(); });
    this._renderBusName();
    var start = this._el("bc-start");
    if (start) start.addEventListener("click", function () { self.start(); });
    var stop = this._el("bc-stop");
    if (stop) stop.addEventListener("click", function () { self.stop(); });
    var save = this._el("bc-save");
    if (save) save.addEventListener("click", function () { self.save(); });
    this._renderPresets();
  };

  BusCapturePanel.prototype._renderBusName = function () {
    var bus = this._el("bc-bus");
    var name = this._el("bc-bus-name");
    if (bus && name) name.textContent = "(" + bus.value + ")";
  };

  BusCapturePanel.prototype._notice = function (text, isError) {
    var el = this._el("bc-notice");
    if (!el) return;
    el.hidden = false;
    el.textContent = text;
    el.classList.toggle("bc-notice-error", !!isError);
  };

  BusCapturePanel.prototype._renderStatus = function (st) {
    var el = this._el("bc-status");
    if (!el) return;
    el.hidden = false;
    el.textContent = "status: " + st.status + " . " + st.elapsed_s.toFixed(1) + "s . " +
      st.frame_count + " frames . " + st.distinct_ids + " distinct ids . " +
      st.rate_hz + " Hz";
  };

  BusCapturePanel.prototype.start = function () {
    var self = this;
    var bus = this._el("bc-bus").value;
    api("POST", "/api/buscapture/" + bus + "/start").then(function (res) {
      if (!res.ok) { self._notice(res.body.error || "could not start.", true); return; }
      self._el("bc-start").hidden = true;
      self._el("bc-stop").hidden = false;
      self._el("bc-save").hidden = true;
      self._renderStatus(res.body);
      self.pollTimer = setInterval(function () { self._poll(bus); }, 1000);
    });
  };

  BusCapturePanel.prototype._poll = function (bus) {
    var self = this;
    api("GET", "/api/buscapture/" + bus + "/status").then(function (res) {
      if (res.ok) self._renderStatus(res.body);
    });
  };

  BusCapturePanel.prototype.stop = function () {
    var self = this;
    var bus = this._el("bc-bus").value;
    if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
    api("POST", "/api/buscapture/" + bus + "/stop").then(function (res) {
      self._el("bc-start").hidden = false;
      self._el("bc-stop").hidden = true;
      if (!res.ok) { self._notice(res.body.error || "could not stop.", true); return; }
      self._renderStatus(res.body);
      self._el("bc-save").hidden = false;
    });
  };

  BusCapturePanel.prototype.save = function () {
    var self = this;
    var bus = this._el("bc-bus").value;
    api("POST", "/api/buscapture/" + bus + "/save", { vin: this.vin }).then(function (res) {
      var el = self._el("bc-result");
      if (!el) return;
      el.hidden = false;
      if (!res.ok) {
        el.textContent = res.body.error || "could not save.";
      } else {
        el.textContent = "saved " + res.body.saved_name + " (" + res.body.frame_count +
          " frames, " + res.body.distinct_ids + " distinct ids)";
        self._el("bc-save").hidden = true;
      }
    });
  };

  BusCapturePanel.prototype._renderPresets = function () {
    var self = this;
    var wrap = this._el("bc-presets");
    if (!wrap) return;
    ["chassis_a6", "body_a5"].forEach(function (name) {
      var q = self.vin ? ("?vin=" + encodeURIComponent(self.vin)) : "";
      fetch("/api/buscapture/presets/" + name + q)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (preset) {
          if (!preset) return;
          var box = self.doc.createElement("div");
          box.className = "bc-preset";
          var head = self.doc.createElement("div");
          head.className = "bc-preset-head";
          var headName = self.doc.createElement("span");
          headName.textContent = preset.name;
          var headCable = self.doc.createElement("span");
          headCable.textContent = "needs " + preset.cable_required;
          head.appendChild(headName);
          head.appendChild(headCable);
          box.appendChild(head);
          var items = self.doc.createElement("div");
          items.className = "bc-preset-items";
          (preset.items || []).forEach(function (it) {
            var row = self.doc.createElement("div");
            row.className = "bc-preset-item status-" + it.status;
            var st = self.doc.createElement("span");
            st.className = "bc-item-status";
            st.textContent = it.status.replace("_", " ");
            var lbl = self.doc.createElement("span");
            lbl.textContent = it.label;
            row.appendChild(st);
            row.appendChild(lbl);
            items.appendChild(row);
          });
          box.appendChild(items);
          wrap.appendChild(box);
        });
    });
  };

  global.CuoreBusCapture = global.CuoreBusCapture || {};
  global.CuoreBusCapture.init = function (doc) { return new BusCapturePanel(doc).init(); };
  global.CuoreBusCapture.BusCapturePanel = BusCapturePanel;

})(typeof window !== "undefined" ? window : globalThis);
