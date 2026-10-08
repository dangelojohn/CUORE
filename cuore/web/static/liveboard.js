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
  function bandNote(b, unit) {
    if (!b) return "";
    var parts = [];
    if (Array.isArray(b.normal) && b.normal[0] != null && b.normal[1] != null) {
      parts.push(fmtNum(b.normal[0]) + "-" + fmtNum(b.normal[1]) + " " + (unit || "") + " normal");
    }
    var alarm = Array.isArray(b.alarm) ? b.alarm : [null, null];
    var aLo = alarm[0], aHi = alarm[1];
    var dir = b.direction || "both";
    var alarmBits = [];
    if ((dir === "below" || dir === "both") && aLo != null) alarmBits.push("<" + fmtNum(aLo));
    if ((dir === "above" || dir === "both") && aHi != null) alarmBits.push(">" + fmtNum(aHi));
    if (alarmBits.length) parts.push(alarmBits.join(" or ") + " alarm");
    var note = parts.join(", ").trim();
    if (b.confidence) {
      var tag = String(b.confidence).toUpperCase().replace(/[\s_]+/g, "-");
      note += (note ? " " : "") + "(" + tag + ")";
    }
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
    return this.loadContract().then(function () {
      self._renderGroups();
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
  };

  LiveboardApp.prototype.startLive = function () {
    var self = this;
    var p = this.sourceKind ? this.stop() : Promise.resolve();
    return p.then(function () {
      var body = { channels: self.allChannelIds, rates: self.rates };
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
    this._renderChannel(id);
    this._renderProblems();
  };

  LiveboardApp.prototype._renderGroups = function () {
    var root = this.doc.getElementById("lb-groups");
    if (!root) return;
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
        unitEl.textContent = c.unit || "";
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
    row.className = "lb-chan level-" + (v ? v.level : "unknown");
    valEl.textContent = (v && typeof v.value === "number" && !isNaN(v.value)) ? fmtValue(v.value) : "—";
    if (unitEl && v && v.unit) unitEl.textContent = v.unit;
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
      text.textContent = fmtValue(r.v.value) + " " + (r.v.unit || "") + (note ? " — " + note : "");
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
      row.classList.toggle("is-stale", (now - v.t) * 1000 > STALE_MS);
    });
  };

  LiveboardApp.prototype._tickUpdatedLabel = function () {
    var el = this.doc.getElementById("lb-status-updated");
    if (!el) return;
    if (!this._lastSampleAt) { el.textContent = "no data yet"; return; }
    var secs = Math.max(0, Math.round(this.now() - this._lastSampleAt));
    el.textContent = "updated " + secs + "s ago";
  };

  LiveboardApp.prototype._pollSessionStatus = function () {
    var self = this;
    this.api("/api/live/status").then(function (s) { self._renderAdapterChip(s); })
      .catch(function () { self._renderAdapterChip(null); });
    this.api("/api/live/session").then(function (s) { self._renderSessionChip(s); })
      .catch(function () { self._renderSessionChip(null); });
  };

  LiveboardApp.prototype._renderAdapterChip = function (s) {
    var el = this.doc.getElementById("lb-status-adapter");
    if (!el) return;
    if (!s || s.error) { el.textContent = "adapter unknown"; el.className = "lb-status-chip"; return; }
    var mesState = (s.mes && s.mes.state) || "unknown";
    el.textContent = "MES " + mesState;
    el.className = "lb-status-chip " + (mesState === "connected" ? "is-warn" : "is-ok");
  };

  LiveboardApp.prototype._renderSessionChip = function (s) {
    var el = this.doc.getElementById("lb-status-session");
    if (!el) return;
    var active = !!(s && s.active);
    if (this.sourceKind === "demo") { el.textContent = "session demo"; el.className = "lb-status-chip is-ok"; return; }
    el.textContent = "session " + (active ? "live" : "idle");
    el.className = "lb-status-chip " + (active ? "is-ok" : "");
  };

  // ---- snapshot ------------------------------------------------------------

  // ``POST /api/live/snapshots`` wants ``{id: {value, unit}}``; the two
  // ``/api/liveboard/*`` routes want ``{id: number}`` -- both built from
  // the same ``this.values`` in one pass so they can never disagree.
  LiveboardApp.prototype.snapshot = function () {
    var self = this;
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
