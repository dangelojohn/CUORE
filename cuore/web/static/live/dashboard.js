/* Customizable live-data dashboard app (/v/{vin}/gauges, /v/{vin}/gauges/hud).
 *
 * Talks to two backends this module does not own:
 *   - the widget library, window.CuoreWidgets (cuore/web/static/live/widgets.js)
 *   - the layout/replay/custom-channel/snapshot/trigger API under /api/live
 *     (cuore/api/live_ui.py), plus the existing poll/stream engine already in
 *     cuore/api/live.py (/api/live/session/*, /api/live/stream).
 *
 * Every dependency on the outside world (fetch, EventSource, the DOM
 * document, the wall clock) is passed through `init(opts)` so a test page can
 * replace all four with fakes and drive the whole app deterministically --
 * see dashboard_test.html. Real pages call `CuoreDashboard.init()` with no
 * arguments and get the real browser globals.
 */
(function (global) {
  "use strict";

  var RATE_TIERS = { fast: 8, normal: 2, slow: 0.5 };
  var PALETTE = ["#6aa6d8", "#e8565c", "#d9a63c", "#52b579", "#b584e0", "#4fc3c9",
                "#e0954f", "#8f9bb3"];
  var WINDOW_CHOICES = [10, 30, 60, 120, 300, 600];
  var LS_PREFIX = "cuore.gauges.";

  function lsGet(key, fallback) {
    try {
      var v = global.localStorage.getItem(LS_PREFIX + key);
      return v === null ? fallback : JSON.parse(v);
    } catch (e) { return fallback; }
  }
  function lsSet(key, val) {
    try { global.localStorage.setItem(LS_PREFIX + key, JSON.stringify(val)); }
    catch (e) { /* private browsing, quota, etc -- a UI convenience only */ }
  }

  function uid(prefix) {
    return prefix + "_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 7);
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    attrs = attrs || {};
    for (var k in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
      if (k === "text") node.textContent = attrs[k];
      else if (k === "html") node.innerHTML = attrs[k];
      else if (k.indexOf("on") === 0 && typeof attrs[k] === "function") {
        node.addEventListener(k.slice(2), attrs[k]);
      } else if (k === "class") node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function opt(value, label, selected) {
    var o = document.createElement("option");
    o.value = value; o.textContent = label;
    if (selected) o.selected = true;
    return o;
  }

  function fmtClock(sec) {
    sec = Math.max(0, Math.floor(sec));
    var m = Math.floor(sec / 60), s = sec % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }

  // ---------------------------------------------------------------------
  // Demo simulator: plausible, loosely-correlated values for a handful of
  // well-known channel ids, and a generic waveform for anything else.
  // ---------------------------------------------------------------------

  function demoDriveInputs(t) {
    // A slow "driving cycle": throttle wanders 0..1, correlating rpm, speed
    // and boost the way a real drive would (not independent random walks).
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
  function hashSeed(s) { var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 1000; return h / 1000 * 6.28; }
  function round2(v) { return Math.round(v * 100) / 100; }

  // ---------------------------------------------------------------------
  // Data sources
  // ---------------------------------------------------------------------

  function LiveSource(app, opts) {
    this.app = app;
    this.opts = opts || {};
    this.manageSession = !opts || opts.manageSession !== false;
    this.es = null; this._statusTimer = null;
  }
  LiveSource.prototype.start = function () {
    var self = this;
    var p = Promise.resolve();
    if (this.manageSession) {
      var channels = this.app.currentPageChannelIds();
      var rates = this.app.currentPageRates();
      var body = { channels: channels, rates: rates };
      if (this.opts && this.opts.monitorDtcs) body.monitor_dtcs = true;
      p = this.app.api("/api/live/session/start", {
        method: "POST", body: JSON.stringify(body),
      }).then(function (session) { self.app.session = session; });
    }
    return p.then(function () {
      self.es = new self.app.ESClass(self.app.apiUrl("/api/live/stream"));
      self.es.onmessage = function (ev) { self._onMessage(ev); };
      if (self.manageSession) {
        self._statusTimer = global.setInterval(function () { self._pollStatus(); }, 2000);
      }
    });
  };
  LiveSource.prototype._onMessage = function (ev) {
    var msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === "dtc") { this.app.onDtcEvent(msg); return; }
    if (msg.channel === undefined) return;
    this.app.onSample({ channel: msg.channel, t: msg.t, value: msg.value, unit: msg.unit, alarm: msg.alarm });
  };
  LiveSource.prototype._pollStatus = function () {
    var self = this;
    this.app.api("/api/live/session").then(function (s) { self.app.onSessionStatus(s); }).catch(function () {});
  };
  LiveSource.prototype.stop = function () {
    if (this.es) { try { this.es.close(); } catch (e) {} this.es = null; }
    if (this._statusTimer) { global.clearInterval(this._statusTimer); this._statusTimer = null; }
    if (!this.manageSession) return Promise.resolve();
    return this.app.api("/api/live/session/stop", { method: "POST" }).catch(function () {});
  };
  LiveSource.prototype.pause = function () {};
  LiveSource.prototype.isPaused = function () { return false; };

  function ReplaySource(app, opts) {
    this.app = app; this.opts = opts || {}; this.es = null;
  }
  ReplaySource.prototype.start = function () {
    var self = this;
    var q = "?speed=" + encodeURIComponent(this.opts.speed || 1);
    if (this.opts.start) q += "&start=" + encodeURIComponent(this.opts.start);
    var url = this.app.apiUrl("/api/live/replay/" + encodeURIComponent(this.opts.recording || "") + "/stream" + q);
    this.es = new this.app.ESClass(url);
    this.es.onmessage = function (ev) { self._onMessage(ev); };
    return Promise.resolve();
  };
  ReplaySource.prototype._onMessage = function (ev) {
    var msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === "tag") {
      this.app.addMarker(msg.label || msg.text || msg.tag || "tag", { t: msg.t });
      return;
    }
    if (msg.type === "dtc") { this.app.onDtcEvent(msg); return; }
    if (msg.type === "end") { this.app.onReplayEnd(); return; }
    if (msg.channel === undefined) return;
    this.app.onSample({ channel: msg.channel, t: msg.t, value: msg.value, unit: msg.unit, alarm: msg.alarm });
  };
  ReplaySource.prototype.stop = function () {
    if (this.es) { try { this.es.close(); } catch (e) {} this.es = null; }
    return Promise.resolve();
  };
  ReplaySource.prototype.pause = function () {};
  ReplaySource.prototype.isPaused = function () { return false; };

  function DemoSource(app) {
    this.app = app; this.t0 = this.app.now(); this._paused = false; this._d = {}; this._timer = null;
  }
  DemoSource.prototype.start = function () {
    var self = this;
    this._timer = global.setInterval(function () { self.tick(); }, 200);
    return Promise.resolve();
  };
  DemoSource.prototype.tick = function () {
    if (this._paused) return;
    var t = this.app.now() - this.t0;
    var d = demoDriveInputs(t);
    var ids = this.app.currentPageChannelIds();
    for (var i = 0; i < ids.length; i++) {
      var id = ids[i];
      var meta = this.app.channelMeta(id);
      var r = demoValue(id, t, d, meta);
      this.app.onSample({ channel: id, t: t, value: r.value, unit: r.unit || (meta && meta.unit) || "", alarm: null });
    }
  };
  DemoSource.prototype.stop = function () {
    if (this._timer) { global.clearInterval(this._timer); this._timer = null; }
    return Promise.resolve();
  };
  DemoSource.prototype.pause = function (p) { this._paused = !!p; };
  DemoSource.prototype.isPaused = function () { return this._paused; };

  // ---------------------------------------------------------------------
  // Main app
  // ---------------------------------------------------------------------

  function DashboardApp(opts) {
    opts = opts || {};
    this.fetchFn = opts.fetch || (global.fetch ? global.fetch.bind(global) : null);
    this.ESClass = opts.EventSource || global.EventSource;
    this.doc = opts.document || document;
    this.now = opts.now || function () { return Date.now() / 1000; };
    this.root = opts.root || this.doc.getElementById("dd-app");
    this.vin = opts.vin || (this.root && this.root.getAttribute("data-vin")) || "";
    this.token = opts.token || this._tokenFromLocation();
    this.hud = !!opts.hud;

    this.channelsById = {};
    this.customChannels = { channels: [] };
    this.presets = {};
    this.layouts = [];
    this.layout = null;
    this.pageId = null;
    this.widgets = {};          // widgetId -> {spec, config, instance, el}
    this.source = null;
    this.sourceKind = null;
    this.replayOpts = {};
    this.windowSec = lsGet("windowSec", 60);
    this.soundOn = lsGet("sound", false);
    this.editMode = false;
    this.dirty = false;
    this.triggers = { rules: [] };
    this.alarmLog = [];
    this._lastFired = {};
    this._lastValues = {};
    this._prevAlarmLevel = {};
    this._levelState = {};
    this._speakAt = 0;
    this._audioCtx = null;
    this.recording = { active: false, startedAt: null };
    this._recordTimer = null;
    this._wakeLock = null;

    this.onTrigger = opts.onTrigger || null;   // test hook
  }

  DashboardApp.prototype._tokenFromLocation = function () {
    try {
      var q = new URLSearchParams(global.location.search);
      return q.get("token") || "";
    } catch (e) { return ""; }
  };

  DashboardApp.prototype.apiUrl = function (path) {
    if (!this.token) return path;
    return path + (path.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(this.token);
  };

  DashboardApp.prototype.api = function (path, options) {
    var self = this;
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    return this.fetchFn(this.apiUrl(path), Object.assign({}, options, { headers: headers }))
      .then(function (resp) {
        return resp.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (e) { body = text; }
          if (!resp.ok) {
            var detail = (body && body.detail) ? body.detail : (resp.statusText || ("HTTP " + resp.status));
            var err = new Error(detail);
            err.status = resp.status; err.body = body;
            throw err;
          }
          return body;
        });
      });
  };

  // --- bootstrap -----------------------------------------------------------

  DashboardApp.prototype.bootstrap = function () {
    var self = this;
    return Promise.all([
      this.api("/api/live/channels").catch(function () { return { channels: [], presets: {} }; }),
      this.api("/api/live/custom-channels").catch(function () { return { channels: [] }; }),
      this.api("/api/live/layouts").catch(function () { return { layouts: [] }; }),
      this.api("/api/live/triggers").catch(function () { return { rules: [] }; }),
    ]).then(function (r) {
      self._applyChannelRegistry(r[0], r[1]);
      self.layouts = (r[2] && r[2].layouts) || [];
      self.triggers = r[3] && r[3].rules ? r[3] : { rules: [] };
      var wantId = lsGet("lastLayout", null);
      var have = self.layouts.some(function (l) { return l.id === wantId; });
      var startId = have ? wantId : (self.layouts[0] && self.layouts[0].id) || null;
      if (!self.hud) self._buildChrome();
      if (startId) {
        return self.loadLayout(startId).then(function () {
          if (self.hud) self._startHud();
          else self._maybeAutostart();
        });
      }
      if (self.hud) self._startHud();
      return null;
    });
  };

  //: ``?autostart=demo|live|replay`` lets a screenshot/smoke-test load the
  //: page already connected, without a click -- purely a convenience for
  //: ``check_live_dashboard_page.py``; normal use always starts on Connect.
  DashboardApp.prototype._maybeAutostart = function () {
    var self = this;
    var kind;
    try { kind = new URLSearchParams(global.location.search).get("autostart"); } catch (e) { kind = null; }
    if (!kind) return;
    this.setSource(kind, {}).then(function () {
      var connectBtn = self.doc.getElementById("dd-connect");
      var stopBtn = self.doc.getElementById("dd-stop");
      if (connectBtn) { connectBtn.hidden = true; connectBtn.classList.add("dd-connected"); }
      if (stopBtn) stopBtn.hidden = false;
    }).catch(function () {});
  };

  DashboardApp.prototype._applyChannelRegistry = function (reg, custom) {
    var self = this;
    this.channelsById = {};
    ((reg && reg.channels) || []).forEach(function (c) { self.channelsById[c.id] = c; });
    this.presets = (reg && reg.presets) || {};
    this.customChannels = custom && custom.channels ? custom : { channels: [] };
    this.customChannels.channels.forEach(function (c) { self.channelsById[c.id] = c; });
  };

  DashboardApp.prototype.channelMeta = function (id) {
    return this.channelsById[id] || { id: id, name: id, unit: "" };
  };

  DashboardApp.prototype.allChannelChoices = function () {
    var out = [];
    for (var id in this.channelsById) if (Object.prototype.hasOwnProperty.call(this.channelsById, id)) out.push(this.channelsById[id]);
    return out.sort(function (a, b) { return (a.name || a.id).localeCompare(b.name || b.id); });
  };

  // --- layouts ---------------------------------------------------------

  DashboardApp.prototype.loadLayout = function (id) {
    var self = this;
    return this.api("/api/live/layouts/" + encodeURIComponent(id)).then(function (layout) {
      self.layout = layout;
      self.dirty = false;
      lsSet("lastLayout", layout.id);
      var wantPage = lsGet("lastPage:" + layout.id, null);
      var have = (layout.pages || []).some(function (p) { return p.id === wantPage; });
      var pid = have ? wantPage : (layout.pages && layout.pages[0] && layout.pages[0].id);
      if (!self.hud) {
        self._renderLayoutSelect();
        self._renderPageTabs();
        self.updateHudLink();
      }
      if (pid) return self.switchToPage(pid);
      return null;
    });
  };

  DashboardApp.prototype.currentPage = function () {
    if (!this.layout) return null;
    var self = this;
    return (this.layout.pages || []).filter(function (p) { return p.id === self.pageId; })[0] || null;
  };

  DashboardApp.prototype.switchToPage = function (pageId) {
    this.pageId = pageId;
    if (this.layout) lsSet("lastPage:" + this.layout.id, pageId);
    if (!this.hud) {
      this._renderPageTabs();
      this._renderGrid();
      this.updateHudLink();
    }
    return Promise.resolve();
  };

  DashboardApp.prototype.currentPageChannelIds = function () {
    var page = this.currentPage();
    if (!page) return [];
    var ids = {};
    (page.widgets || []).forEach(function (w) {
      (w.channels || []).forEach(function (c) { ids[c] = true; });
      if (w.xChannel) ids[w.xChannel] = true;
      if (w.yChannel) ids[w.yChannel] = true;
    });
    return Object.keys(ids);
  };

  DashboardApp.prototype.currentPageRates = function () {
    var page = this.currentPage();
    var out = {};
    if (!page) return out;
    (page.widgets || []).forEach(function (w) {
      var tiers = w.rates || {};
      (w.channels || []).forEach(function (c) {
        var tier = tiers[c] || "normal";
        var hz = RATE_TIERS[tier] || RATE_TIERS.normal;
        out[c] = Math.max(out[c] || 0, hz);
      });
    });
    return out;
  };

  DashboardApp.prototype.exportLayoutJSON = function () {
    if (!this.layout) return null;
    return JSON.parse(JSON.stringify(this.layout));
  };

  DashboardApp.prototype.markDirty = function () { this.dirty = true; };

  DashboardApp.prototype.saveLayout = function () {
    if (!this.layout) return Promise.reject(new Error("no layout loaded"));
    if (this.layout.builtin) return Promise.reject(new Error("built-in layouts are read-only -- use Save as"));
    var self = this;
    return this.api("/api/live/layouts/" + encodeURIComponent(this.layout.id), {
      method: "PUT", body: JSON.stringify(this.exportLayoutJSON()),
    }).then(function (saved) { self.layout = saved || self.layout; self.dirty = false; return self.layout; });
  };

  DashboardApp.prototype.saveLayoutAs = function (name) {
    var self = this;
    var copy = this.exportLayoutJSON() || { pages: [{ id: uid("page"), title: "Page 1", widgets: [] }] };
    copy.id = uid("layout");
    copy.name = name;
    copy.builtin = false;
    return this.api("/api/live/layouts/" + encodeURIComponent(copy.id), {
      method: "PUT", body: JSON.stringify(copy),
    }).then(function (saved) {
      self.layout = saved || copy;
      self.dirty = false;
      return self.api("/api/live/layouts").then(function (r) {
        self.layouts = (r && r.layouts) || self.layouts;
        if (!self.hud) self._renderLayoutSelect();
        return self.layout;
      });
    });
  };

  DashboardApp.prototype.deleteLayout = function (id) {
    var self = this;
    return this.api("/api/live/layouts/" + encodeURIComponent(id), { method: "DELETE" }).then(function () {
      self.layouts = self.layouts.filter(function (l) { return l.id !== id; });
      if (!self.hud) self._renderLayoutSelect();
    });
  };

  DashboardApp.prototype.exportLayoutUrl = function () {
    if (!this.layout) return "";
    return this.apiUrl("/api/live/layouts/" + encodeURIComponent(this.layout.id) + "/export");
  };

  DashboardApp.prototype.importLayoutFromText = function (text) {
    var self = this;
    var parsed;
    try { parsed = JSON.parse(text); } catch (e) { return Promise.reject(new Error("not valid JSON: " + e.message)); }
    return this.api("/api/live/layouts/import", { method: "POST", body: JSON.stringify(parsed) })
      .then(function (imported) {
        return self.api("/api/live/layouts").then(function (r) {
          self.layouts = (r && r.layouts) || self.layouts;
          if (!self.hud) self._renderLayoutSelect();
          var id = (imported && imported.id) || parsed.id;
          if (id) return self.loadLayout(id);
          return null;
        });
      });
  };

  // --- pages / widgets (edit model) ------------------------------------

  DashboardApp.prototype.addPage = function (title) {
    if (!this.layout) return null;
    var page = { id: uid("page"), title: title || "New page", widgets: [] };
    this.layout.pages.push(page);
    this.markDirty();
    if (!this.hud) this._renderPageTabs();
    return page;
  };

  DashboardApp.prototype.renamePage = function (pageId, title) {
    var page = (this.layout.pages || []).filter(function (p) { return p.id === pageId; })[0];
    if (!page) return;
    page.title = title;
    this.markDirty();
    if (!this.hud) this._renderPageTabs();
  };

  DashboardApp.prototype.deletePage = function (pageId) {
    if (!this.layout || this.layout.pages.length <= 1) return;
    this.layout.pages = this.layout.pages.filter(function (p) { return p.id !== pageId; });
    this.markDirty();
    if (this.pageId === pageId) this.switchToPage(this.layout.pages[0].id);
    else if (!this.hud) this._renderPageTabs();
  };

  DashboardApp.prototype.addWidgetToPage = function (pageId, spec) {
    var page = (this.layout.pages || []).filter(function (p) { return p.id === pageId; })[0];
    if (!page) return null;
    spec = Object.assign({}, spec);
    spec.id = spec.id || uid("w");
    spec.channels = spec.channels || [];
    spec.size = [clamp((spec.size && spec.size[0]) || 1, 1, 4), clamp((spec.size && spec.size[1]) || 1, 1, 3)];
    page.widgets.push(spec);
    this.markDirty();
    if (pageId === this.pageId && !this.hud) this._renderGrid();
    return spec;
  };

  DashboardApp.prototype.removeWidgetFromPage = function (pageId, widgetId) {
    var page = (this.layout.pages || []).filter(function (p) { return p.id === pageId; })[0];
    if (!page) return;
    page.widgets = page.widgets.filter(function (w) { return w.id !== widgetId; });
    this.markDirty();
    if (this.widgets[widgetId]) {
      try { this.widgets[widgetId].instance.destroy(); } catch (e) {}
      delete this.widgets[widgetId];
    }
    if (pageId === this.pageId && !this.hud) this._renderGrid();
  };

  DashboardApp.prototype.updateWidget = function (pageId, widgetId, patch) {
    var page = (this.layout.pages || []).filter(function (p) { return p.id === pageId; })[0];
    if (!page) return;
    var spec = (page.widgets || []).filter(function (w) { return w.id === widgetId; })[0];
    if (!spec) return;
    Object.assign(spec, patch);
    this.markDirty();
    if (pageId === this.pageId && !this.hud) this._renderGrid();
  };

  DashboardApp.prototype.moveWidget = function (pageId, widgetId, dir) {
    var page = (this.layout.pages || []).filter(function (p) { return p.id === pageId; })[0];
    if (!page) return;
    var i = page.widgets.findIndex(function (w) { return w.id === widgetId; });
    var j = i + dir;
    if (i < 0 || j < 0 || j >= page.widgets.length) return;
    var tmp = page.widgets[i]; page.widgets[i] = page.widgets[j]; page.widgets[j] = tmp;
    this.markDirty();
    if (pageId === this.pageId && !this.hud) this._renderGrid();
  };

  // --- widget mounting ---------------------------------------------------

  DashboardApp.prototype._buildWidgetConfig = function (spec) {
    var self = this;
    var chans = (spec.channels || []).map(function (cid, i) {
      var meta = self.channelMeta(cid);
      return { id: cid, name: meta.name || cid, unit: meta.unit || "", color: PALETTE[i % PALETTE.length] };
    });
    return {
      title: spec.title || (chans[0] ? chans[0].name : spec.type),
      channels: chans,
      min: spec.min, max: spec.max,
      warn: spec.warn || null, alarm: spec.alarm || null,
      decimals: spec.decimals != null ? spec.decimals : 1,
      smoothing: spec.smoothing || 0,
      windowSec: spec.windowSec || this.windowSec,
      xChannel: spec.xChannel, yChannel: spec.yChannel,
      mirror: !!spec.mirror,
      orientation: spec.orientation || "horizontal",
      onCursor: function (t) { self._onWidgetCursor(spec.id, t); },
    };
  };

  DashboardApp.prototype._mountWidget = function (spec) {
    var self = this;
    var body = el("div", { class: "dd-widget-body" });
    var config = this._buildWidgetConfig(spec);
    var instance = null;
    var CW = global.CuoreWidgets;
    if (CW && CW.types && CW.types[spec.type]) {
      try { instance = CW.create(spec.type, body, config); }
      catch (e) { body.appendChild(el("div", { class: "dd-missing", text: "widget error: " + e.message })); }
    } else {
      body.appendChild(el("div", { class: "dd-missing", text: "widgets.js: unknown type " + spec.type }));
    }
    if (!instance) instance = this._nullWidget();
    var head = el("div", { class: "dd-widget-head" }, [
      el("span", { class: "dd-wtitle", text: config.title }),
    ]);
    if (this.editMode) {
      head.appendChild(el("button", { title: "Settings", text: "⚙", onclick: function () { self.openWidgetSettings(spec.id); } }));
      head.appendChild(el("button", { title: "Move up", text: "↑", onclick: function () { self.moveWidget(self.pageId, spec.id, -1); } }));
      head.appendChild(el("button", { title: "Move down", text: "↓", onclick: function () { self.moveWidget(self.pageId, spec.id, 1); } }));
      head.appendChild(el("button", { title: "Shrink", text: "–", onclick: function () { self._resizeWidget(spec.id, -1, 0); } }));
      head.appendChild(el("button", { title: "Grow", text: "+", onclick: function () { self._resizeWidget(spec.id, 1, 0); } }));
      head.appendChild(el("button", { title: "Taller", text: "↕", onclick: function () { self._resizeWidget(spec.id, 0, 1); } }));
      head.appendChild(el("button", { title: "Delete", text: "✕", onclick: function () {
        if (global.confirm("Remove this widget?")) self.removeWidgetFromPage(self.pageId, spec.id);
      } }));
    }
    var wrapper = el("div", {
      class: "dd-widget", "data-widget-id": spec.id,
      draggable: this.editMode ? "true" : "false",
      style: "grid-column: span " + spec.size[0] + "; grid-row: span " + spec.size[1] + ";",
    }, [head, body]);
    this._wireDrag(wrapper, spec.id);
    this.widgets[spec.id] = { spec: spec, config: config, instance: instance, el: wrapper };
    return wrapper;
  };

  DashboardApp.prototype._nullWidget = function () {
    return {
      push: function () {}, setConfig: function () {}, resize: function () {}, destroy: function () {},
      pause: function () {}, isPaused: function () { return false; }, setWindow: function () {},
      setCursor: function () {}, stats: function () { return {}; }, resetStats: function () {},
      level: function () { return "ok"; }, snapshot: function () { return {}; },
    };
  };

  DashboardApp.prototype._resizeWidget = function (widgetId, dw, dh) {
    var w = this.widgets[widgetId]; if (!w) return;
    var size = w.spec.size;
    this.updateWidget(this.pageId, widgetId, { size: [clamp(size[0] + dw, 1, 4), clamp(size[1] + dh, 1, 3)] });
  };

  DashboardApp.prototype._wireDrag = function (wrapper, widgetId) {
    var self = this;
    wrapper.addEventListener("dragstart", function (ev) {
      if (!self.editMode) return;
      wrapper.classList.add("dd-dragging");
      ev.dataTransfer.setData("text/plain", widgetId);
      ev.dataTransfer.effectAllowed = "move";
    });
    wrapper.addEventListener("dragend", function () { wrapper.classList.remove("dd-dragging"); });
    wrapper.addEventListener("dragover", function (ev) { if (self.editMode) ev.preventDefault(); });
    wrapper.addEventListener("drop", function (ev) {
      if (!self.editMode) return;
      ev.preventDefault();
      var draggedId = ev.dataTransfer.getData("text/plain");
      if (!draggedId || draggedId === widgetId) return;
      self._reorderByDrag(draggedId, widgetId);
    });
  };

  DashboardApp.prototype._reorderByDrag = function (draggedId, targetId) {
    var page = this.currentPage(); if (!page) return;
    var from = page.widgets.findIndex(function (w) { return w.id === draggedId; });
    var to = page.widgets.findIndex(function (w) { return w.id === targetId; });
    if (from < 0 || to < 0) return;
    var item = page.widgets.splice(from, 1)[0];
    page.widgets.splice(to, 0, item);
    this.markDirty();
    this._renderGrid();
  };

  DashboardApp.prototype._onWidgetCursor = function (fromId, t) {
    for (var id in this.widgets) {
      if (id === fromId) continue;
      try { this.widgets[id].instance.setCursor(t); } catch (e) {}
    }
  };

  // --- rendering (skipped entirely in HUD mode / headless test harness) --

  DashboardApp.prototype._renderGrid = function () {
    if (!this.root) return;
    var grid = this.doc.getElementById("dd-grid");
    if (!grid) return;
    for (var id in this.widgets) { try { this.widgets[id].instance.destroy(); } catch (e) {} }
    this.widgets = {};
    grid.innerHTML = "";
    var page = this.currentPage();
    var self = this;
    (page ? page.widgets : []).forEach(function (spec) { grid.appendChild(self._mountWidget(spec)); });
    if (this.editMode) {
      grid.appendChild(el("button", { class: "dd-add-tile", title: "Add widget", text: "+", onclick: function () { self.openAddWidget(); } }));
    }
  };

  DashboardApp.prototype._renderPageTabs = function () {
    if (!this.root) return;
    var bar = this.doc.getElementById("dd-pagetabs");
    if (!bar) return;
    bar.innerHTML = "";
    var self = this;
    (this.layout ? this.layout.pages : []).forEach(function (p, i) {
      var btn = el("button", {
        text: p.title, class: p.id === self.pageId ? "on" : "", "data-page-id": p.id,
        onclick: function () { self.switchToPage(p.id); },
      });
      if (self.editMode) {
        btn.title = "Double-click to rename";
        btn.addEventListener("dblclick", function () {
          var name = global.prompt("Page title", p.title);
          if (name) self.renamePage(p.id, name);
        });
      }
      bar.appendChild(btn);
    });
    if (this.editMode) {
      bar.appendChild(el("button", { class: "dd-page-add", text: "+ Page", onclick: function () {
        var name = global.prompt("New page title", "Page " + ((self.layout.pages.length || 0) + 1));
        if (name) self.addPage(name).id && self.switchToPage(self.layout.pages[self.layout.pages.length - 1].id);
      } }));
      if (this.layout && this.layout.pages.length > 1) {
        bar.appendChild(el("button", { text: "Delete page", onclick: function () {
          if (global.confirm("Delete page \"" + (self.currentPage() || {}).title + "\"?")) self.deletePage(self.pageId);
        } }));
      }
    }
  };

  DashboardApp.prototype._renderLayoutSelect = function () {
    if (!this.root) return;
    var sel = this.doc.getElementById("dd-layout-select");
    if (!sel) return;
    sel.innerHTML = "";
    var self = this;
    this.layouts.forEach(function (l) {
      sel.appendChild(opt(l.id, l.name + (l.builtin ? " (built-in)" : ""), self.layout && l.id === self.layout.id));
    });
  };

  // --- toolbar / chrome ---------------------------------------------------

  DashboardApp.prototype._buildChrome = function () {
    var self = this;
    if (!this.root) return;

    var soundBox = this.doc.getElementById("dd-sound");
    if (soundBox) { soundBox.checked = this.soundOn; soundBox.addEventListener("change", function () { self.soundOn = soundBox.checked; lsSet("sound", self.soundOn); }); }

    var windowSel = this.doc.getElementById("dd-window-select");
    if (windowSel) {
      windowSel.value = String(this.windowSec);
      windowSel.addEventListener("change", function () {
        self.windowSec = parseInt(windowSel.value, 10) || 60;
        lsSet("windowSec", self.windowSec);
        for (var id in self.widgets) { try { self.widgets[id].instance.setWindow(self.windowSec); } catch (e) {} }
      });
    }

    var layoutSel = this.doc.getElementById("dd-layout-select");
    if (layoutSel) layoutSel.addEventListener("change", function () {
      if (self.dirty && !global.confirm("Discard unsaved changes to this layout?")) { self._renderLayoutSelect(); return; }
      self.loadLayout(layoutSel.value);
    });

    var saveBtn = this.doc.getElementById("dd-layout-save");
    if (saveBtn) saveBtn.addEventListener("click", function () {
      self.saveLayout().catch(function (e) { global.alert("Save failed: " + e.message); });
    });
    var saveAsBtn = this.doc.getElementById("dd-layout-saveas");
    if (saveAsBtn) saveAsBtn.addEventListener("click", function () {
      var name = global.prompt("Save layout as:", (self.layout && self.layout.name ? self.layout.name + " copy" : "My layout"));
      if (name) self.saveLayoutAs(name).catch(function (e) { global.alert("Save as failed: " + e.message); });
    });
    var exportBtn = this.doc.getElementById("dd-layout-export");
    if (exportBtn) exportBtn.addEventListener("click", function () {
      var url = self.exportLayoutUrl();
      if (url) global.open(url, "_blank");
    });
    var importBtn = this.doc.getElementById("dd-layout-import");
    var importFile = this.doc.getElementById("dd-import-file");
    if (importBtn && importFile) {
      importBtn.addEventListener("click", function () { importFile.click(); });
      importFile.addEventListener("change", function () {
        var file = importFile.files && importFile.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function () {
          self.importLayoutFromText(String(reader.result)).catch(function (e) { global.alert("Import failed: " + e.message); });
        };
        reader.readAsText(file);
        importFile.value = "";
      });
    }

    var sourceSel = this.doc.getElementById("dd-source-select");
    var replayRec = this.doc.getElementById("dd-replay-recording");
    var replaySpeed = this.doc.getElementById("dd-replay-speed");
    var monitorDtcsWrap = this.doc.getElementById("dd-monitor-dtcs-wrap");
    if (sourceSel) {
      sourceSel.addEventListener("change", function () {
        var kind = sourceSel.value;
        if (replayRec) replayRec.hidden = kind !== "replay";
        if (replaySpeed) replaySpeed.hidden = kind !== "replay";
        if (monitorDtcsWrap) monitorDtcsWrap.hidden = kind !== "live";
      });
      if (monitorDtcsWrap) monitorDtcsWrap.hidden = sourceSel.value !== "live";
    }
    if (replayRec) {
      this.api("/api/live/recordings").then(function (r) {
        (r.recordings || []).forEach(function (rec) { replayRec.appendChild(opt(rec.id || rec.name, rec.name || rec.id, false)); });
      }).catch(function () {});
    }
    if (replaySpeed) {
      [0.25, 0.5, 1, 2, 4, 8, 16].forEach(function (s) { replaySpeed.appendChild(opt(String(s), s + "x", s === 1)); });
    }

    var connectBtn = this.doc.getElementById("dd-connect");
    var stopBtn = this.doc.getElementById("dd-stop");
    var monitorDtcsBox = this.doc.getElementById("dd-monitor-dtcs");
    if (connectBtn) connectBtn.addEventListener("click", function () {
      var kind = sourceSel ? sourceSel.value : "demo";
      var opts = kind === "replay" ? { recording: replayRec ? replayRec.value : "", speed: replaySpeed ? parseFloat(replaySpeed.value) : 1 } : {};
      if (kind === "live" && monitorDtcsBox) opts.monitorDtcs = monitorDtcsBox.checked;
      self.setSource(kind, opts).then(function () {
        connectBtn.hidden = true; if (stopBtn) stopBtn.hidden = false;
        connectBtn.classList.add("dd-connected");
      }).catch(function (e) { global.alert("Could not start: " + e.message); });
    });
    if (stopBtn) stopBtn.addEventListener("click", function () {
      self.setSource(null).then(function () {
        stopBtn.hidden = true; if (connectBtn) { connectBtn.hidden = false; connectBtn.classList.remove("dd-connected"); }
      });
    });

    var recordBtn = this.doc.getElementById("dd-record");
    if (recordBtn) recordBtn.addEventListener("click", function () {
      if (self.recording.active) self.stopRecording(); else self.startRecording();
    });
    var snapBtn = this.doc.getElementById("dd-snapshot");
    if (snapBtn) snapBtn.addEventListener("click", function () {
      self.takeSnapshot().catch(function (e) { global.alert("Snapshot failed: " + e.message); });
    });
    var markBtn = this.doc.getElementById("dd-mark");
    if (markBtn) markBtn.addEventListener("click", function () {
      self.addMarker("manual mark", { t: self.elapsed() });
    });
    var pauseBtn = this.doc.getElementById("dd-pause-all");
    if (pauseBtn) pauseBtn.addEventListener("click", function () { self.togglePauseAll(); });

    var editBtn = this.doc.getElementById("dd-edit-toggle");
    if (editBtn) editBtn.addEventListener("click", function () { self.toggleEditMode(); });

    var alarmToggle = this.doc.getElementById("dd-alarm-log-toggle");
    if (alarmToggle) alarmToggle.addEventListener("click", function () { self._toggleDrawer("dd-alarm-drawer"); });
    var trigToggle = this.doc.getElementById("dd-triggers-toggle");
    if (trigToggle) trigToggle.addEventListener("click", function () { self.openTriggersDialog(); });
    var chanToggle = this.doc.getElementById("dd-channels-toggle");
    if (chanToggle) chanToggle.addEventListener("click", function () { self.openCustomChannelsDialog(); });

    global.addEventListener("beforeunload", function (ev) {
      if (self.dirty) { ev.preventDefault(); ev.returnValue = ""; return ""; }
    });

    this.doc.addEventListener("keydown", function (ev) { self._onKeydown(ev); });
  };

  DashboardApp.prototype._toggleDrawer = function (id) {
    var d = this.doc.getElementById(id);
    if (!d) return;
    d.hidden = !d.hidden;
    if (id === "dd-alarm-drawer" && !d.hidden) this._renderAlarmLog();
  };

  DashboardApp.prototype._renderAlarmLog = function () {
    var d = this.doc.getElementById("dd-alarm-drawer");
    if (!d) return;
    var body = d.querySelector(".dd-log-body") || d;
    body.innerHTML = "";
    var rows = this.alarmLog.slice(-200).reverse();
    var self = this;
    rows.forEach(function (r) {
      body.appendChild(el("div", { class: "dd-log-row level-" + r.level }, [
        el("span", { class: "t", text: fmtClock(r.t || 0) }),
        el("span", { class: "lv", text: (r.level || "").toUpperCase() + " " }),
        el("span", { text: r.text + (r.value != null ? " (" + r.value + ")" : "") }),
      ]));
    });
    if (!rows.length) body.appendChild(el("div", { class: "muted small", text: "No alarms or markers yet." }));
  };

  DashboardApp.prototype.updateHudLink = function () {
    var a = this.doc.getElementById("dd-hud-link");
    if (!a || !this.layout) return;
    var q = "?layout=" + encodeURIComponent(this.layout.id) + "&page=" + encodeURIComponent(this.pageId || "");
    if (this.sourceKind) q += "&source=" + encodeURIComponent(this.sourceKind);
    if (this.sourceKind === "replay") {
      q += "&recording=" + encodeURIComponent(this.replayOpts.recording || "") + "&speed=" + encodeURIComponent(this.replayOpts.speed || 1);
    }
    a.href = a.getAttribute("href").split("?")[0] + q;
  };

  // --- edit mode -----------------------------------------------------------

  DashboardApp.prototype.toggleEditMode = function () {
    if (!this.editMode && this.layout && this.layout.builtin) {
      if (global.confirm("This is a built-in layout (read-only). Save a copy to edit it?")) {
        var name = global.prompt("New layout name:", this.layout.name + " copy");
        if (!name) return;
        var self = this;
        this.saveLayoutAs(name).then(function () { self.editMode = true; self._afterEditToggle(); });
      }
      return;
    }
    this.editMode = !this.editMode;
    this._afterEditToggle();
  };

  DashboardApp.prototype._afterEditToggle = function () {
    var btn = this.doc.getElementById("dd-edit-toggle");
    if (btn) btn.textContent = this.editMode ? "Done editing" : "Edit layout";
    this._renderPageTabs();
    this._renderGrid();
  };

  DashboardApp.prototype.openAddWidget = function () {
    var dlg = this.doc.getElementById("dd-add-widget");
    if (!dlg) return;
    this._fillAddWidgetDialog(dlg);
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "open");
  };

  DashboardApp.prototype._fillAddWidgetDialog = function (dlg) {
    var self = this;
    dlg.innerHTML = "";
    var CW = global.CuoreWidgets;
    var typeSel = el("select", { id: "dd-aw-type" });
    var types = (CW && CW.types) || { digital: { label: "Digital", minChannels: 1, maxChannels: 1 } };
    Object.keys(types).forEach(function (t) { typeSel.appendChild(opt(t, types[t].label || t, false)); });
    var chanWrap = el("div", { class: "dd-chanlist", id: "dd-aw-channels" });
    var titleInput = el("input", { type: "text", id: "dd-aw-title", placeholder: "Title (optional)" });
    var errBox = el("div", { class: "dd-error" });

    function renderChannels() {
      chanWrap.innerHTML = "";
      var t = types[typeSel.value] || {};
      var max = t.maxChannels || 1;
      self.allChannelChoices().forEach(function (c) {
        var cb = el("input", { type: "checkbox", value: c.id });
        cb.addEventListener("change", function () {
          var checked = chanWrap.querySelectorAll("input:checked");
          if (checked.length > max) cb.checked = false;
        });
        chanWrap.appendChild(el("label", {}, [cb, document.createTextNode(c.name + (c.unit ? " (" + c.unit + ")" : ""))]));
      });
    }
    typeSel.addEventListener("change", renderChannels);
    renderChannels();

    dlg.appendChild(el("h2", { text: "Add widget" }));
    dlg.appendChild(el("div", { class: "dd-field" }, [el("label", { text: "Type" }), typeSel]));
    dlg.appendChild(el("div", { class: "dd-field" }, [el("label", { text: "Title" }), titleInput]));
    dlg.appendChild(el("div", { class: "dd-field" }, [el("label", { text: "Channels" }), chanWrap]));
    dlg.appendChild(errBox);
    dlg.appendChild(el("div", { class: "dd-actions" }, [
      el("button", { class: "btn", text: "Cancel", type: "button", onclick: function () { dlg.close ? dlg.close() : dlg.removeAttribute("open"); } }),
      el("button", { class: "btn primary", text: "Add", type: "button", onclick: function () {
        var t = types[typeSel.value] || {};
        var chosen = Array.prototype.map.call(chanWrap.querySelectorAll("input:checked"), function (i) { return i.value; });
        var min = t.minChannels || 1;
        if (chosen.length < min) { errBox.textContent = "Pick at least " + min + " channel(s) for this widget type."; return; }
        var size = t.defaultSize || [1, 1];
        self.addWidgetToPage(self.pageId, { type: typeSel.value, title: titleInput.value, channels: chosen, size: size });
        dlg.close ? dlg.close() : dlg.removeAttribute("open");
      } }),
    ]));
  };

  DashboardApp.prototype.openWidgetSettings = function (widgetId) {
    var dlg = this.doc.getElementById("dd-widget-settings");
    var w = this.widgets[widgetId];
    if (!dlg || !w) return;
    var self = this;
    var spec = w.spec;
    dlg.innerHTML = "";
    var titleInput = el("input", { type: "text", value: spec.title || "" });
    var minInput = el("input", { type: "number", value: spec.min != null ? spec.min : "" });
    var maxInput = el("input", { type: "number", value: spec.max != null ? spec.max : "" });
    var warnLo = el("input", { type: "number", value: spec.warn ? spec.warn[0] : "" });
    var warnHi = el("input", { type: "number", value: spec.warn ? spec.warn[1] : "" });
    var alarmLo = el("input", { type: "number", value: spec.alarm ? spec.alarm[0] : "" });
    var alarmHi = el("input", { type: "number", value: spec.alarm ? spec.alarm[1] : "" });
    var decimals = el("input", { type: "number", value: spec.decimals != null ? spec.decimals : 1 });
    var smoothing = el("input", { type: "number", value: spec.smoothing || 0, step: "0.1" });
    var windowInput = el("input", { type: "number", value: spec.windowSec || self.windowSec });
    var orientSel = el("select", {}, [opt("horizontal", "Horizontal", spec.orientation !== "vertical"), opt("vertical", "Vertical", spec.orientation === "vertical")]);
    var mirrorBox = el("input", { type: "checkbox" }); mirrorBox.checked = !!spec.mirror;

    function num(input) { var v = input.value; return v === "" ? undefined : parseFloat(v); }

    dlg.appendChild(el("h2", { text: "Widget settings" }));
    [["Title", titleInput], ["Min", minInput], ["Max", maxInput],
     ["Warn low", warnLo], ["Warn high", warnHi], ["Alarm low", alarmLo], ["Alarm high", alarmHi],
     ["Decimals", decimals], ["Smoothing", smoothing], ["Window (s)", windowInput],
     ["Orientation", orientSel], ["Mirror", mirrorBox]].forEach(function (pair) {
      dlg.appendChild(el("div", { class: "dd-field" }, [el("label", { text: pair[0] }), pair[1]]));
    });
    dlg.appendChild(el("div", { class: "dd-actions" }, [
      el("button", { class: "btn", text: "Cancel", type: "button", onclick: function () { dlg.close ? dlg.close() : dlg.removeAttribute("open"); } }),
      el("button", { class: "btn primary", text: "Save", type: "button", onclick: function () {
        var patch = {
          title: titleInput.value, min: num(minInput), max: num(maxInput),
          warn: (warnLo.value !== "" && warnHi.value !== "") ? [num(warnLo), num(warnHi)] : null,
          alarm: (alarmLo.value !== "" && alarmHi.value !== "") ? [num(alarmLo), num(alarmHi)] : null,
          decimals: num(decimals), smoothing: num(smoothing), windowSec: num(windowInput),
          orientation: orientSel.value, mirror: mirrorBox.checked,
        };
        self.updateWidget(self.pageId, widgetId, patch);
        dlg.close ? dlg.close() : dlg.removeAttribute("open");
      } }),
    ]));
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "open");
  };

  // --- triggers ------------------------------------------------------------

  var OPS = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"];
  var ACTIONS = ["record_start", "record_stop", "snapshot", "beep", "speak", "mark"];

  DashboardApp.prototype.openTriggersDialog = function () {
    var dlg = this.doc.getElementById("dd-triggers-dialog");
    if (!dlg) return;
    this._renderTriggersDialog(dlg);
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "open");
  };

  DashboardApp.prototype._renderTriggersDialog = function (dlg) {
    var self = this;
    dlg.innerHTML = "";
    dlg.appendChild(el("h2", { text: "Triggers" }));
    var rowsWrap = el("div", { class: "dd-rows" });
    var errBox = el("div", { class: "dd-error" });

    function rowFor(rule) {
      var when = rule.when || {};
      var isDtc = when.dtc !== undefined;
      var enabled = el("input", { type: "checkbox" }); enabled.checked = rule.enabled !== false;
      var kindSel = el("select", {}, [opt("channel", "Channel", !isDtc), opt("dtc", "DTC", isDtc)]);
      var chanSel = el("select", {});
      self.allChannelChoices().forEach(function (c) { chanSel.appendChild(opt(c.id, c.name, when.channel === c.id)); });
      var opSel = el("select", {});
      OPS.forEach(function (o) { opSel.appendChild(opt(o, o, when.op === o)); });
      var valInput = el("input", { type: "number", value: when.value != null ? when.value : "" });
      var dtcInput = el("input", { type: "text", placeholder: "code, or blank = any",
        value: (isDtc && when.dtc !== "any") ? when.dtc : "" });
      var actionSel = el("select", {});
      ACTIONS.forEach(function (a) { actionSel.appendChild(opt(a, a, rule.action === a)); });
      var textInput = el("input", { type: "text", value: rule.text || "", placeholder: "text (speak/mark)" });
      var cooldown = el("input", { type: "number", value: rule.cooldown_s != null ? rule.cooldown_s : 10, style: "max-width:70px" });
      var del = el("button", { class: "btn", type: "button", text: "✕", onclick: function () { row.remove(); } });
      function syncKind() {
        var dtc = kindSel.value === "dtc";
        chanSel.hidden = dtc; opSel.hidden = dtc; valInput.hidden = dtc;
        dtcInput.hidden = !dtc;
      }
      kindSel.addEventListener("change", syncKind);
      syncKind();
      var row = el("div", { class: "dd-row" },
        [enabled, kindSel, chanSel, opSel, valInput, dtcInput, actionSel, textInput, cooldown, del]);
      row._read = function () {
        var out = {
          id: rule.id || uid("rule"), enabled: enabled.checked,
          action: actionSel.value, text: textInput.value, cooldown_s: parseFloat(cooldown.value) || 0,
        };
        out.when = (kindSel.value === "dtc")
          ? { dtc: dtcInput.value.trim() || "any" }
          : { channel: chanSel.value, op: opSel.value, value: valInput.value === "" ? 0 : parseFloat(valInput.value) };
        return out;
      };
      return row;
    }

    (this.triggers.rules || []).forEach(function (r) { rowsWrap.appendChild(rowFor(r)); });
    dlg.appendChild(rowsWrap);
    dlg.appendChild(el("button", { class: "btn", type: "button", text: "+ Rule", onclick: function () {
      rowsWrap.appendChild(rowFor({}));
    } }));
    dlg.appendChild(errBox);
    dlg.appendChild(el("div", { class: "dd-actions" }, [
      el("button", { class: "btn", type: "button", text: "Close", onclick: function () { dlg.close ? dlg.close() : dlg.removeAttribute("open"); } }),
      el("button", { class: "btn primary", type: "button", text: "Save", onclick: function () {
        var rules = Array.prototype.map.call(rowsWrap.children, function (r) { return r._read(); });
        self.api("/api/live/triggers", { method: "PUT", body: JSON.stringify({ rules: rules }) }).then(function (saved) {
          self.triggers = saved && saved.rules ? saved : { rules: rules };
          dlg.close ? dlg.close() : dlg.removeAttribute("open");
        }).catch(function (e) { errBox.textContent = e.message; });
      } }),
    ]));
  };

  // --- custom channels -------------------------------------------------

  DashboardApp.prototype.openCustomChannelsDialog = function () {
    var dlg = this.doc.getElementById("dd-channels-dialog");
    if (!dlg) return;
    this._renderCustomChannelsDialog(dlg);
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "open");
  };

  DashboardApp.prototype._renderCustomChannelsDialog = function (dlg) {
    var self = this;
    dlg.innerHTML = "";
    dlg.appendChild(el("h2", { text: "Custom channels" }));
    var rowsWrap = el("div", { class: "dd-rows" });
    var errBox = el("div", { class: "dd-error" });

    function rowFor(c) {
      c = c || {};
      var idInput = el("input", { type: "text", value: c.id || "", placeholder: "id" });
      var nameInput = el("input", { type: "text", value: c.name || "", placeholder: "name" });
      var kindSel = el("select", {}, [opt("did", "Torque-style (DID)", c.kind !== "computed"), opt("computed", "Computed", c.kind === "computed")]);
      var moduleInput = el("input", { type: "text", value: c.module || "", placeholder: "module (ECM...)" });
      var didInput = el("input", { type: "text", value: c.did || "", placeholder: "DID hex" });
      var formulaInput = el("input", { type: "text", value: c.formula || "", placeholder: "formula, e.g. A-40" });
      var exprInput = el("input", { type: "text", value: c.expr || "", placeholder: "expr over channel ids" });
      var unitInput = el("input", { type: "text", value: c.unit || "", placeholder: "unit" });
      var del = el("button", { class: "btn", type: "button", text: "✕", onclick: function () { row.remove(); } });

      function syncKind() {
        var computed = kindSel.value === "computed";
        moduleInput.hidden = computed; didInput.hidden = computed; formulaInput.hidden = computed;
        exprInput.hidden = !computed;
      }
      kindSel.addEventListener("change", syncKind); syncKind();

      var row = el("div", { class: "dd-row" }, [idInput, nameInput, kindSel, moduleInput, didInput, formulaInput, exprInput, unitInput, del]);
      row._read = function () {
        var out = { id: idInput.value.trim(), name: nameInput.value.trim() || idInput.value.trim(), unit: unitInput.value, kind: kindSel.value };
        if (kindSel.value === "computed") out.expr = exprInput.value;
        else { out.module = moduleInput.value; out.did = didInput.value; out.formula = formulaInput.value; }
        return out;
      };
      return row;
    }

    (this.customChannels.channels || []).forEach(function (c) { rowsWrap.appendChild(rowFor(c)); });
    dlg.appendChild(rowsWrap);
    dlg.appendChild(el("button", { class: "btn", type: "button", text: "+ Channel", onclick: function () { rowsWrap.appendChild(rowFor({})); } }));
    dlg.appendChild(errBox);
    dlg.appendChild(el("div", { class: "dd-actions" }, [
      el("button", { class: "btn", type: "button", text: "Close", onclick: function () { dlg.close ? dlg.close() : dlg.removeAttribute("open"); } }),
      el("button", { class: "btn primary", type: "button", text: "Save", onclick: function () {
        var channels = Array.prototype.map.call(rowsWrap.children, function (r) { return r._read(); }).filter(function (c) { return c.id; });
        self.api("/api/live/custom-channels", { method: "PUT", body: JSON.stringify({ channels: channels }) }).then(function (saved) {
          self._applyChannelRegistry({ channels: Object.values(self.channelsById), presets: self.presets }, saved && saved.channels ? saved : { channels: channels });
          dlg.close ? dlg.close() : dlg.removeAttribute("open");
        }).catch(function (e) { errBox.textContent = e.message; });
      } }),
    ]));
  };

  // --- sources / data flow ----------------------------------------------

  DashboardApp.prototype.setSource = function (kind, opts) {
    var self = this;
    var stop = this.source ? this.source.stop() : Promise.resolve();
    return stop.then(function () {
      self.source = null; self.sourceKind = null;
      var demoBanner = self.doc.getElementById("dd-demo-banner");
      if (demoBanner) demoBanner.hidden = true;
      if (!kind) return null;
      self.sourceKind = kind;
      self.replayOpts = opts || {};
      if (kind === "live") self.source = new LiveSource(self, opts);
      else if (kind === "replay") self.source = new ReplaySource(self, opts);
      else if (kind === "demo") self.source = new DemoSource(self);
      else throw new Error("unknown source " + kind);
      if (kind === "demo" && demoBanner) demoBanner.hidden = false;
      self.updateHudLink();
      return self.source.start();
    });
  };

  DashboardApp.prototype.onSessionStatus = function (status) {
    var el2 = this.doc.getElementById("dd-connect");
    if (el2 && status && status.achieved_hz) el2.title = "achieved: " + JSON.stringify(status.achieved_hz);
  };

  DashboardApp.prototype.onReplayEnd = function () {
    this.addLog("replay finished", "mark");
  };

  DashboardApp.prototype.togglePauseAll = function () {
    var paused = this.source && this.source.isPaused && this.source.isPaused();
    var next = !paused;
    if (this.source && this.source.pause) this.source.pause(next);
    for (var id in this.widgets) { try { this.widgets[id].instance.pause(next); } catch (e) {} }
    var btn = this.doc.getElementById("dd-pause-all");
    if (btn) btn.textContent = next ? "Resume" : "Pause all";
  };

  DashboardApp.prototype.onSample = function (sample) {
    for (var id in this.widgets) {
      var w = this.widgets[id];
      var cfg = w.config;
      var uses = cfg.channels.some(function (c) { return c.id === sample.channel; }) ||
        cfg.xChannel === sample.channel || cfg.yChannel === sample.channel;
      if (uses) {
        try { w.instance.push(sample.channel, sample.t, sample.value); } catch (e) {}
      }
    }
    this._updateAlarmLevel(sample);
    this.evaluateTriggers(sample);
    this._lastValues[sample.channel] = sample.value;
  };

  DashboardApp.prototype._widgetLevelFor = function (channelId) {
    for (var id in this.widgets) {
      var w = this.widgets[id];
      if (w.config.channels.some(function (c) { return c.id === channelId; })) {
        try { return w.instance.level(channelId); } catch (e) { return "ok"; }
      }
    }
    return "ok";
  };

  DashboardApp.prototype._updateAlarmLevel = function (sample) {
    var level = sample.alarm || this._widgetLevelFor(sample.channel);
    if (!level) level = "ok";
    var prev = this._levelState[sample.channel] || "ok";
    this._levelState[sample.channel] = level;
    for (var id in this.widgets) {
      var w = this.widgets[id];
      if (w.config.channels.some(function (c) { return c.id === sample.channel; })) {
        w.el.classList.toggle("dd-level-warn", level === "warn");
        w.el.classList.toggle("dd-level-alarm", level === "alarm");
      }
    }
    if (level !== prev && level !== "ok") {
      this.addLog(this.channelMeta(sample.channel).name + " " + level, level, sample.value, sample.channel);
      if (this.soundOn) { this.playBeep(level); this.speak(this.channelMeta(sample.channel).name + " " + level); }
    }
  };

  DashboardApp.prototype.addLog = function (text, level, value, channel) {
    var entry = { t: this.elapsed(), text: text, level: level || "info", value: value, channel: channel };
    this.alarmLog.push(entry);
    if (this.alarmLog.length > 500) this.alarmLog.shift();
    this._renderAlarmLog();
    return entry;
  };

  DashboardApp.prototype.addMarker = function (text, sample) {
    var entry = this.addLog(text, "mark", null, sample && sample.channel);
    entry.t = (sample && sample.t != null) ? sample.t : entry.t;
    for (var id in this.widgets) {
      try { this.widgets[id].instance.setCursor(entry.t); } catch (e) {}
      try { this.widgets[id].instance.addMarker(entry.t, text); } catch (e) {}
    }
    return entry;
  };

  // A DTC transition reported by the live poller (see cuore/live/poller.py
  // _poll_dtcs) or replayed from a recording: logged, drawn as a marker on
  // every graph, and able to drive a trigger whose ``when`` names ``dtc``.
  DashboardApp.prototype.onDtcEvent = function (msg) {
    var t = (msg && msg.t != null) ? msg.t : this.elapsed();
    var added = (msg && msg.added) || [];
    var removed = (msg && msg.removed) || [];
    var self = this;
    added.forEach(function (entry) { self.addLog("DTC+ " + entry, "dtc", null, null); });
    removed.forEach(function (entry) { self.addLog("DTC- " + entry, "dtc", null, null); });
    var label = added.length ? ("DTC+ " + added.join(", "))
      : (removed.length ? ("DTC- " + removed.join(", ")) : "DTC change");
    for (var id in this.widgets) {
      try { this.widgets[id].instance.addMarker(t, label); } catch (e) {}
    }
    this._evaluateDtcTriggers(added, t);
  };

  DashboardApp.prototype.elapsed = function () {
    if (this.source instanceof DemoSource) return this.now() - this.source.t0;
    return this.now();
  };

  DashboardApp.prototype.playBeep = function (level) {
    try {
      var Ctx = global.AudioContext || global.webkitAudioContext;
      if (!Ctx) return;
      if (!this._audioCtx) this._audioCtx = new Ctx();
      var ctx = this._audioCtx;
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.frequency.value = level === "alarm" ? 880 : 587;
      osc.type = "square";
      gain.gain.value = 0.05;
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + (level === "alarm" ? 0.28 : 0.14));
    } catch (e) { /* no audio available -- not fatal */ }
  };

  DashboardApp.prototype.speak = function (text) {
    try {
      if (!global.speechSynthesis || !global.SpeechSynthesisUtterance) return;
      var now = this.now();
      if (now - this._speakAt < 4) return;   // rate-limit
      this._speakAt = now;
      var u = new global.SpeechSynthesisUtterance(text);
      global.speechSynthesis.speak(u);
    } catch (e) { /* not fatal */ }
  };

  DashboardApp.prototype.evaluateTriggers = function (sample) {
    var self = this;
    (this.triggers.rules || []).forEach(function (rule) {
      if (rule.enabled === false) return;
      var when = rule.when || {};
      var fire = false;
      if (when.alarm) {
        if ((!when.channel || when.channel === sample.channel) && sample.alarm) {
          var prevLevel = self._prevAlarmLevel[sample.channel];
          if (sample.alarm === when.alarm && prevLevel !== when.alarm) fire = true;
        }
        if (sample.alarm) self._prevAlarmLevel[sample.channel] = sample.alarm;
      } else if (when.channel === sample.channel && typeof when.value === "number") {
        var prev = self._lastValues[sample.channel];
        var v = sample.value;
        switch (when.op) {
          case ">": fire = v > when.value; break;
          case "<": fire = v < when.value; break;
          case ">=": fire = v >= when.value; break;
          case "<=": fire = v <= when.value; break;
          case "==": fire = v === when.value; break;
          case "!=": fire = v !== when.value; break;
          case "crosses_above": fire = prev != null && prev <= when.value && v > when.value; break;
          case "crosses_below": fire = prev != null && prev >= when.value && v < when.value; break;
          default: fire = false;
        }
      }
      if (!fire) return;
      var now = self.now();
      var last = self._lastFired[rule.id];
      var cooldown = rule.cooldown_s || 0;
      if (last != null && now - last < cooldown) return;
      self._lastFired[rule.id] = now;
      self._runTriggerAction(rule, sample);
    });
  };

  // Triggers whose ``when`` is {"dtc": "any"} or {"dtc": "<code>"} -- fires
  // when any of this event's *added* codes matches (removed codes clearing
  // never fire a dtc trigger; that is what record_stop / manual stop is for).
  DashboardApp.prototype._evaluateDtcTriggers = function (added, t) {
    var self = this;
    (this.triggers.rules || []).forEach(function (rule) {
      if (rule.enabled === false) return;
      var when = rule.when || {};
      if (!when.dtc) return;
      var fire = when.dtc === "any" ? added.length > 0
        : added.some(function (entry) { return entry.split(" ")[0] === when.dtc; });
      if (!fire) return;
      var now = self.now();
      var last = self._lastFired[rule.id];
      var cooldown = rule.cooldown_s || 0;
      if (last != null && now - last < cooldown) return;
      self._lastFired[rule.id] = now;
      self._runTriggerAction(rule, { channel: null, value: null, t: t });
    });
  };

  DashboardApp.prototype._runTriggerAction = function (rule, sample) {
    if (this.onTrigger) try { this.onTrigger(rule, sample); } catch (e) {}
    switch (rule.action) {
      case "record_start": this.startRecording(); break;
      case "record_stop": this.stopRecording(); break;
      case "snapshot": this.takeSnapshot().catch(function () {}); break;
      case "beep": this.playBeep("alarm"); break;
      case "speak": this.speak(rule.text || (this.channelMeta(sample.channel).name + " trigger")); break;
      case "mark": this.addMarker(rule.text || ("trigger: " + rule.id), sample); break;
      default: break;
    }
  };

  // --- recording / snapshot ------------------------------------------------

  DashboardApp.prototype.startRecording = function () {
    var self = this;
    if (this.recording.active) return Promise.resolve();
    return this.api("/api/live/record/start", { method: "POST" }).then(function () {
      self.recording = { active: true, startedAt: self.now() };
      self._updateRecordUI();
      self._recordTimer = global.setInterval(function () { self._updateRecordUI(); }, 1000);
    }).catch(function (e) { global.alert && global.alert("Could not start recording: " + e.message); });
  };

  DashboardApp.prototype.stopRecording = function () {
    var self = this;
    if (!this.recording.active) return Promise.resolve();
    return this.api("/api/live/record/stop", { method: "POST" }).then(function (r) {
      self.recording = { active: false, startedAt: null };
      if (self._recordTimer) { global.clearInterval(self._recordTimer); self._recordTimer = null; }
      self._updateRecordUI();
      self.addLog("recording saved" + (r && r.rows != null ? " (" + r.rows + " rows)" : ""), "mark");
    });
  };

  DashboardApp.prototype._updateRecordUI = function () {
    var btn = this.doc.getElementById("dd-record");
    var elapsedEl = this.doc.getElementById("dd-record-elapsed");
    if (btn) { btn.textContent = this.recording.active ? "Stop recording" : "Record"; btn.classList.toggle("dd-recording", this.recording.active); }
    if (elapsedEl) {
      elapsedEl.hidden = !this.recording.active;
      if (this.recording.active) elapsedEl.textContent = fmtClock(this.now() - this.recording.startedAt);
    }
  };

  DashboardApp.prototype.takeSnapshot = function () {
    var values = {};
    for (var id in this.widgets) {
      try { Object.assign(values, this.widgets[id].instance.snapshot()); } catch (e) {}
    }
    var payload = {
      source: this.sourceKind || "unknown",
      vin: this.vin,
      layout: this.layout ? this.layout.id : null,
      page: this.pageId,
      at: new Date().toISOString(),
      values: values,
    };
    var self = this;
    return this.api("/api/live/snapshots", { method: "POST", body: JSON.stringify(payload) }).then(function (r) {
      self.addLog("snapshot saved", "mark");
      return r;
    });
  };

  // --- keyboard --------------------------------------------------------

  DashboardApp.prototype._onKeydown = function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var target = ev.target;
    var typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
    if (typing) return;
    if (this.doc.querySelector && this.doc.querySelector("dialog[open]")) return;
    if (ev.key === " ") { ev.preventDefault(); this.togglePauseAll(); return; }
    if (ev.key >= "1" && ev.key <= "9" && this.layout) {
      var idx = parseInt(ev.key, 10) - 1;
      var page = this.layout.pages[idx];
      if (page) this.switchToPage(page.id);
      return;
    }
    if (ev.key === "r" || ev.key === "R") { if (this.recording.active) this.stopRecording(); else this.startRecording(); return; }
    if (ev.key === "s" || ev.key === "S") { this.takeSnapshot().catch(function () {}); return; }
    if (ev.key === "e" || ev.key === "E") { this.toggleEditMode(); return; }
  };

  // --- HUD ---------------------------------------------------------------

  DashboardApp.prototype._startHud = function () {
    var self = this;
    var params = new URLSearchParams(global.location.search);
    var pageId = params.get("page") || this.pageId;
    var sourceKind = params.get("source") || "demo";
    var page = (this.layout ? this.layout.pages : []).filter(function (p) { return p.id === pageId; })[0] ||
      (this.layout && this.layout.pages[0]);
    var ids = [];
    if (page) (page.widgets || []).forEach(function (w) { (w.channels || []).forEach(function (c) { if (ids.indexOf(c) === -1) ids.push(c); }); });
    ids = ids.slice(0, 4);
    this.pageId = page ? page.id : null;

    var grid = this.doc.getElementById("dd-hud-grid");
    if (grid) {
      grid.className = "dd-hud-grid dd-hud-" + Math.max(1, ids.length);
      var mirror = params.get("mirror") === "1";
      var self2 = this;
      ids.forEach(function (cid) {
        var meta = self2.channelMeta(cid);
        var cell = el("div", { class: "dd-hud-widget" + (mirror ? " dd-hud-mirror" : "") });
        grid.appendChild(cell);
        var CW = global.CuoreWidgets;
        var config = { title: meta.name, channels: [{ id: cid, name: meta.name, unit: meta.unit || "" }], decimals: 1, mirror: mirror };
        var instance = null;
        if (CW && CW.types && CW.types.hud) { try { instance = CW.create("hud", cell, config); } catch (e) {} }
        if (!instance) instance = self2._nullWidget();
        self2.widgets[cid + "_hud"] = { spec: { id: cid + "_hud", channels: [cid] }, config: config, instance: instance, el: cell };
      });
    }
    var mirrorBtn = this.doc.getElementById("dd-hud-mirror");
    if (mirrorBtn) mirrorBtn.addEventListener("click", function () {
      self.doc.querySelectorAll(".dd-hud-widget").forEach(function (c) { c.classList.toggle("dd-hud-mirror"); });
    });
    if (global.navigator && global.navigator.wakeLock && global.navigator.wakeLock.request) {
      global.navigator.wakeLock.request("screen").then(function (lock) { self._wakeLock = lock; }).catch(function () {});
    }
    var replayOpts = sourceKind === "replay" ? { recording: params.get("recording") || "", speed: parseFloat(params.get("speed") || "1") } : {};
    this.setSource(sourceKind, sourceKind === "live" ? { manageSession: false } : replayOpts).catch(function () {});
  };

  // -----------------------------------------------------------------------

  var CuoreDashboard = {
    VERSION: "1.0",
    init: function (opts) {
      var app = new DashboardApp(opts || {});
      app.ready = app.bootstrap().catch(function (e) {
        if (global.console) global.console.error("CuoreDashboard bootstrap failed", e);
      });
      CuoreDashboard._app = app;
      return app;
    },
    initHud: function (opts) {
      opts = Object.assign({ hud: true }, opts || {});
      return this.init(opts);
    },
  };

  global.CuoreDashboard = CuoreDashboard;
})(typeof window !== "undefined" ? window : this);
