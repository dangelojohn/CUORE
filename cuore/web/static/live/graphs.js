/* Stacked time graphs for the Gauges page (panel #gg-panel in live_dashboard.html).
 * Polls GET /api/live/snapshot once a second, keeps a rolling in-memory history per channel, and draws
 * 1-4 plain <canvas> graphs. A click/tap on any graph puts one cursor on ALL graphs; a second tap clears it.
 * Selected channels and graph count are remembered per VIN in localStorage. No libraries, no animation:
 * graphs redraw on each poll only (so prefers-reduced-motion needs nothing extra). */
(function (global) {
  "use strict";
  var WINDOWS = [[30, "30 s"], [120, "2 min"], [600, "10 min"]];
  var MAX_WIN = 600;
  var POLL_MS = 1000;

  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function clock(ms) {
    var d = new Date(ms);
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
  }
  function fmt(v) {
    if (v === null || v === undefined || isNaN(v)) return "no value";
    return (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)).replace(/\.0$/, "");
  }

  // Last sample at or before t (samples are time-ordered); null when none.
  function valueAt(hist, t) {
    var best = null;
    for (var i = 0; i < hist.length; i++) { if (hist[i][0] <= t) best = hist[i]; else break; }
    return best;
  }
  function minMax(hist, t0) {
    var lo = null, hi = null;
    for (var i = 0; i < hist.length; i++) {
      if (hist[i][0] < t0) continue;
      var v = hist[i][1];
      if (lo === null || v < lo) lo = v;
      if (hi === null || v > hi) hi = v;
    }
    return { min: lo, max: hi };
  }

  function Graphs(opts) {
    opts = opts || {};
    this.doc = opts.document || document;
    this.fetchFn = opts.fetch || (global.fetch ? global.fetch.bind(global) : null);
    this.now = opts.now || function () { return Date.now(); };
    this.panel = this.doc.getElementById("gg-panel");
    this.vin = (this.panel && this.panel.getAttribute("data-vin")) || "";
    this.token = opts.token || this._token();
    this.hist = {};       // id -> [[ms, value], ...]
    this.units = {};      // id -> unit
    this.names = {};      // id -> display name
    this.cursor = null;   // absolute ms or null
    this.count = 1;
    this.graphs = [];     // [{channel, win}]
    this.timer = null;
    this.fs = 16;
  }
  Graphs.prototype._token = function () {
    try { return new URLSearchParams(global.location.search).get("token") || ""; } catch (e) { return ""; }
  };
  Graphs.prototype.url = function (p) {
    return this.token ? p + (p.indexOf("?") < 0 ? "?" : "&") + "token=" + encodeURIComponent(this.token) : p;
  };
  Graphs.prototype.get = function (p) {
    return this.fetchFn(this.url(p)).then(function (r) { return r.json(); });
  };
  Graphs.prototype.key = function () { return "cuore.gg." + this.vin; };

  Graphs.prototype.load = function () {
    try {
      var s = JSON.parse(global.localStorage.getItem(this.key()) || "null");
      if (s) {
        this.count = Math.min(4, Math.max(1, s.count | 0 || 1));
        this.graphs = (s.graphs || []).slice(0, 4);
      }
    } catch (e) {}
    while (this.graphs.length < 4) this.graphs.push({ channel: "", win: 120 });
  };
  Graphs.prototype.save = function () {
    try { global.localStorage.setItem(this.key(), JSON.stringify({ count: this.count, graphs: this.graphs })); } catch (e) {}
  };

  // The --fs-md token in real pixels (the token may be rem-based): measure it on a probe element.
  Graphs.prototype.measureFont = function () {
    var p = this.doc.createElement("span");
    p.style.cssText = "position:absolute;visibility:hidden;font-size:var(--fs-md)";
    p.textContent = "0";
    this.panel.appendChild(p);
    var px = parseFloat(global.getComputedStyle(p).fontSize);
    this.panel.removeChild(p);
    this.fs = px > 0 ? px : 16;
  };

  Graphs.prototype.init = function () {
    if (!this.panel || !this.fetchFn) return;
    this.load();
    this.measureFont();
    this.build();
    var self = this;
    this.get("/api/live/channels").then(function (reg) {
      ((reg && reg.channels) || []).forEach(function (c) { self.names[c.id] = c.name || c.id; if (c.unit) self.units[c.id] = c.unit; });
    }).catch(function () {}).then(function () { self.poll(); });
    this.timer = global.setInterval(function () { self.poll(); }, POLL_MS);
  };

  Graphs.prototype.build = function () {
    var self = this, d = this.doc;
    var bar = d.getElementById("gg-count");
    bar.innerHTML = "";
    var lab = d.createElement("span");
    lab.className = "gg-label"; lab.textContent = "Graphs:";
    bar.appendChild(lab);
    [1, 2, 3, 4].forEach(function (n) {
      var b = d.createElement("button");
      b.type = "button"; b.className = "btn gg-btn"; b.textContent = String(n);
      b.setAttribute("data-count", String(n));
      b.setAttribute("aria-pressed", n === self.count ? "true" : "false");
      b.addEventListener("click", function () { self.count = n; self.save(); self.build(); self.draw(); });
      bar.appendChild(b);
    });
    var host = d.getElementById("gg-graphs");
    host.innerHTML = "";
    for (var i = 0; i < this.count; i++) host.appendChild(this.buildOne(i));
    this.fillSelects();
  };

  Graphs.prototype.buildOne = function (i) {
    var self = this, d = this.doc, g = this.graphs[i];
    var box = d.createElement("div");
    box.className = "gg-graph"; box.setAttribute("data-i", String(i));
    var row = d.createElement("div");
    row.className = "gg-row";
    var sel = d.createElement("select");
    sel.className = "gg-chan"; sel.setAttribute("aria-label", "Graph " + (i + 1) + " channel");
    sel.addEventListener("change", function () { g.channel = sel.value; self.save(); self.draw(); });
    var win = d.createElement("select");
    win.className = "gg-win"; win.setAttribute("aria-label", "Graph " + (i + 1) + " time window");
    WINDOWS.forEach(function (w) {
      var o = d.createElement("option");
      o.value = String(w[0]); o.textContent = w[1];
      if (w[0] === g.win) o.selected = true;
      win.appendChild(o);
    });
    win.addEventListener("change", function () { g.win = parseInt(win.value, 10); self.save(); self.draw(); });
    row.appendChild(sel); row.appendChild(win);
    var wrap = d.createElement("div");
    wrap.className = "gg-wrap";
    var cv = d.createElement("canvas");
    cv.className = "gg-canvas"; cv.setAttribute("role", "img");
    cv.addEventListener("click", function (ev) { self.onTap(i, ev); });
    var stats = d.createElement("div");
    stats.className = "gg-stats";
    wrap.appendChild(cv); wrap.appendChild(stats);
    box.appendChild(row); box.appendChild(wrap);
    return box;
  };

  Graphs.prototype.fillSelects = function () {
    var self = this, ids = Object.keys(this.hist).sort();
    var sels = this.doc.querySelectorAll("#gg-graphs .gg-chan");
    Array.prototype.forEach.call(sels, function (sel, i) {
      var g = self.graphs[i], keep = sel.value;
      if (sel.options.length === ids.length + 1 && keep === g.channel) return;
      sel.innerHTML = "";
      var none = self.doc.createElement("option");
      none.value = ""; none.textContent = ids.length ? "Choose a channel" : "No session channels yet";
      sel.appendChild(none);
      // A remembered channel stays selectable even before the session has reported it.
      var list = ids.slice();
      if (g.channel && list.indexOf(g.channel) < 0) list.push(g.channel);
      list.forEach(function (id) {
        var o = self.doc.createElement("option");
        o.value = id; o.textContent = self.names[id] || id;
        sel.appendChild(o);
      });
      sel.value = g.channel || "";
    });
  };

  Graphs.prototype.poll = function () {
    var self = this;
    return this.get("/api/live/snapshot").then(function (snap) {
      var t = self.now();
      var ch = (snap && snap.channels) || {};
      Object.keys(ch).forEach(function (id) {
        var c = ch[id], h = self.hist[id] || (self.hist[id] = []);
        if (c.unit) self.units[id] = c.unit;
        if (typeof c.value === "number" && !isNaN(c.value)) h.push([t, c.value]);
        var cut = t - MAX_WIN * 1000;
        while (h.length && h[0][0] < cut) h.shift();
      });
      self.fillSelects();
      self.draw();
    }).catch(function () {});
  };

  Graphs.prototype.onTap = function (i, ev) {
    if (this.cursor !== null) { this.cursor = null; this.draw(); return; }
    var cv = ev.currentTarget, r = cv.getBoundingClientRect();
    var plotL = this.plotLeft();
    var f = Math.min(1, Math.max(0, (ev.clientX - r.left - plotL) / Math.max(1, r.width - plotL - 4)));
    this.cursor = this.now() - (1 - f) * this.graphs[i].win * 1000;
    this.draw();
  };
  Graphs.prototype.plotLeft = function () { return Math.round(this.fs * 4.2); };

  function css(el, name, fallback) {
    var v = global.getComputedStyle(el).getPropertyValue(name).trim();
    return v || fallback;
  }

  Graphs.prototype.draw = function () {
    var self = this, t = this.now(), lines = [];
    var cvs = this.doc.querySelectorAll("#gg-graphs .gg-graph");
    Array.prototype.forEach.call(cvs, function (box, i) {
      self.drawOne(box, self.graphs[i], t);
      var g = self.graphs[i];
      if (self.cursor !== null && g.channel) {
        var s = valueAt(self.hist[g.channel] || [], self.cursor);
        lines.push(clock(self.cursor) + "  " + (self.names[g.channel] || g.channel) + " " +
                   (s ? fmt(s[1]) + (self.units[g.channel] ? " " + self.units[g.channel] : "") : "no value"));
      }
    });
    var out = this.doc.getElementById("gg-readout");
    if (out) out.textContent = this.cursor === null ? "Tap a graph to read every graph at that moment. Tap again to clear."
                                                    : lines.join("\n");
  };

  Graphs.prototype.drawOne = function (box, g, t) {
    var cv = box.querySelector("canvas"), stats = box.querySelector(".gg-stats");
    var dpr = global.devicePixelRatio || 1;
    var w = cv.clientWidth || 300, h = cv.clientHeight || 140;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    }
    var cx = cv.getContext && cv.getContext("2d");
    var hist = g.channel ? (this.hist[g.channel] || []) : [];
    var t0 = t - g.win * 1000, unit = this.units[g.channel] || "";
    var mm = minMax(hist, t0), last = hist.length ? hist[hist.length - 1][1] : null;
    var nm = this.names[g.channel] || g.channel || "no channel";
    stats.innerHTML = "";
    [["Now", last], ["Min", mm.min], ["Max", mm.max]].forEach(function (p) {
      var d = box.ownerDocument.createElement("div");
      d.textContent = p[0] + " " + fmt(p[1]) + (p[1] !== null && unit ? " " + unit : "");
      stats.appendChild(d);
    });
    cv.setAttribute("aria-label", nm + " over " + g.win + " seconds");
    if (!cx) return;
    var ink = css(cv, "--ink", "#ccc"), ink2 = css(cv, "--ink-2", "#999"), rule = css(cv, "--rule", "#555"),
        line = css(cv, "--accent", "#e8565c"), bg = css(cv, "--surface", "#111");
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx.clearRect(0, 0, w, h);
    cx.fillStyle = bg; cx.fillRect(0, 0, w, h);
    var L = this.plotLeft(), R = 4, T = Math.round(this.fs * 0.6), B = Math.round(this.fs * 1.8);
    var pw = w - L - R, ph = h - T - B;
    cx.font = this.fs + "px sans-serif";
    cx.strokeStyle = rule; cx.lineWidth = 1; cx.strokeRect(L + 0.5, T + 0.5, pw, ph);
    cx.fillStyle = ink2; cx.textBaseline = "alphabetic";
    cx.textAlign = "left"; cx.fillText("-" + g.win + " s", L, h - 4);
    cx.textAlign = "right"; cx.fillText("now", L + pw, h - 4);
    if (mm.min === null) {
      cx.textAlign = "center"; cx.fillStyle = ink;
      cx.fillText(g.channel ? "Waiting for readings" : "Choose a channel", L + pw / 2, T + ph / 2);
      return;
    }
    var lo = mm.min, hi = mm.max;
    if (hi === lo) { hi += 1; lo -= 1; }
    cx.textAlign = "right"; cx.fillStyle = ink2;
    cx.fillText(fmt(hi), L - 4, T + this.fs); cx.fillText(fmt(lo), L - 4, T + ph);
    function X(ms) { return L + (ms - t0) / (g.win * 1000) * pw; }
    function Y(v) { return T + ph - (v - lo) / (hi - lo) * ph; }
    cx.strokeStyle = line; cx.lineWidth = 2; cx.beginPath();
    var started = false;
    hist.forEach(function (s) {
      if (s[0] < t0) return;
      if (!started) { cx.moveTo(X(s[0]), Y(s[1])); started = true; } else cx.lineTo(X(s[0]), Y(s[1]));
    });
    cx.stroke();
    if (this.cursor !== null && this.cursor >= t0 && this.cursor <= t) {
      var x = X(this.cursor);
      cx.strokeStyle = ink; cx.lineWidth = 1; cx.setLineDash([4, 3]);
      cx.beginPath(); cx.moveTo(x, T); cx.lineTo(x, T + ph); cx.stroke(); cx.setLineDash([]);
    }
  };

  global.CuoreGraphs = { Graphs: Graphs, valueAt: valueAt, minMax: minMax, fmt: fmt };
  if (global.document) global.document.addEventListener("DOMContentLoaded", function () {
    if (global.document.getElementById("gg-panel")) new Graphs().init();
  });
})(window);
