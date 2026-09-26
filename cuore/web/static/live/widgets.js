/* CUORE live-data widget library.
 *
 * Vanilla ES2019, no build step, no CDN. Two other agents build on top of
 * this: a dashboard app that instantiates widgets through the contract
 * below, and backend APIs that feed values in. This file owns only the
 * widgets themselves -- nothing here knows about pages, presets, or how
 * values get from the car to the browser.
 *
 * Design split: gauges that are mostly static geometry (digital, bar,
 * tiles, hud, table) are plain DOM + CSS, styled from cuore.css's tokens so
 * theme and layout come for free. The analog dial is SVG (explicit in the
 * contract). The five time-series types (line, multiline, stacked, scope,
 * scatter) share one Canvas-based engine, because redrawing a few hundred
 * points sixty times a second is what canvas is for.
 *
 * Contract: window.CuoreWidgets = { types, create, format }. See the
 * spec this was built against for the full shape -- push()/setConfig()/
 * resize()/destroy()/pause()/isPaused()/setWindow()/setCursor()/stats()/
 * resetStats()/level()/snapshot() on every widget instance.
 *
 * Extensions beyond the base contract (all additive, no signature changed):
 *   - channels[] may carry optional per-channel `min`/`max` (multiline uses
 *     these for independent y-axes when given; falls back to auto-range).
 *   - config.normalized (bool, multiline): scale every trace to its own
 *     0..1 range instead of absolute units, for shape comparison.
 *   - config.trigger (number, scope): rising-edge level; when set the scope
 *     freezes one windowSec sweep per trigger instead of free-scrolling.
 *   - config.binned (bool, scatter, default true): draw the binned-average
 *     line described in the spec; set false to hide it.
 *   - onCursor firing: implemented for line/multiline/stacked (spec calls
 *     it out for stacked explicitly; the others fire it too so a dashboard
 *     can sync any combination of graphs, not just stacked-driven ones).
 */
(function (global) {
  "use strict";

  // ---------------------------------------------------------------- utils

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function isNum(v) { return typeof v === "number" && !Number.isNaN(v) && Number.isFinite(v); }

  function format(value, decimals) {
    if (!isNum(value)) return "—";
    var d = (decimals === null || decimals === undefined) ? 1 : decimals;
    return value.toFixed(d);
  }

  function inBand(value, band) {
    if (!band || band[0] === null || band[0] === undefined) return false;
    var lo = Math.min(band[0], band[1]), hi = Math.max(band[0], band[1]);
    return value >= lo && value <= hi;
  }

  function levelOf(value, warn, alarm) {
    if (!isNum(value)) return "ok";
    if (inBand(value, alarm)) return "alarm";
    if (inBand(value, warn)) return "warn";
    return "ok";
  }

  function levelVar(level, bg) {
    var base = level === "alarm" ? "--sev-returned" : level === "warn" ? "--sev-chronic" : "--ok";
    return base + (bg ? "-bg" : "");
  }

  function cssVar(fromEl, name) {
    var v = getComputedStyle(fromEl).getPropertyValue(name);
    return v ? v.trim() : "";
  }

  var PALETTE = ["--ok", "--sev-cleared", "--sev-chronic", "--accent", "--sev-once", "--sev-returned"];
  function paletteVar(index) { return PALETTE[index % PALETTE.length]; }

  function mkEl(tag, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }
  function svgEl(tag, attrs) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    if (attrs) for (var k in attrs) if (attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]);
    return e;
  }
  function setAttrs(e, attrs) {
    for (var k in attrs) if (attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]);
  }

  // requestAnimationFrame-batched draw scheduler shared by every instance:
  // push() only ever stores data; this loop is the only thing that paints,
  // and it paints each dirty widget at most once per frame.
  var dirty = [];
  var rafHandle = null;
  function scheduleDraw(widget) {
    if (dirty.indexOf(widget) === -1) dirty.push(widget);
    if (rafHandle === null) rafHandle = requestAnimationFrame(flush);
  }
  function unscheduleDraw(widget) {
    var i = dirty.indexOf(widget);
    if (i !== -1) dirty.splice(i, 1);
  }
  function flush() {
    rafHandle = null;
    var list = dirty; dirty = [];
    for (var i = 0; i < list.length; i++) {
      try { list[i]._draw(); } catch (err) { /* one widget's failure must not sink the frame */ }
    }
  }

  // ------------------------------------------------------------ ChannelSeries

  function ChannelSeries(def) {
    this.id = def.id;
    this.name = def.name || def.id;
    this.unit = def.unit || "";
    this.color = def.color || null;
    this.min = (def.min === undefined) ? null : def.min;   // optional per-channel y-range (multiline)
    this.max = (def.max === undefined) ? null : def.max;
    this.buf = [];                 // [{t, v}] v may be null (gap)
    this.n = 0; this.sum = 0; this.smin = null; this.smax = null; this.last = null;
    this.peak = null;
    this.ema = null;
  }
  ChannelSeries.prototype.push = function (t, v, smoothing) {
    this.buf.push({ t: t, v: v });
    if (v === null) return;
    this.n++; this.sum += v; this.last = v;
    if (this.smin === null || v < this.smin) this.smin = v;
    if (this.smax === null || v > this.smax) this.smax = v;
    if (this.peak === null || v > this.peak) this.peak = v;
    if (smoothing && smoothing > 0 && this.ema !== null) {
      this.ema = smoothing * this.ema + (1 - smoothing) * v;
    } else {
      this.ema = v;
    }
  };
  ChannelSeries.prototype.avg = function () { return this.n ? this.sum / this.n : null; };
  ChannelSeries.prototype.resetStats = function () {
    this.n = 0; this.sum = 0; this.smin = null; this.smax = null; this.peak = null;
  };
  ChannelSeries.prototype.trim = function (keepSec) {
    var n = this.buf.length;
    if (!n) return;
    var latestT = this.buf[n - 1].t;
    var cutoff = latestT - keepSec;
    var i = 0;
    while (i < n && this.buf[i].t < cutoff) i++;
    if (i > 0) this.buf.splice(0, i);
  };
  ChannelSeries.prototype.observedRange = function () {
    if (this.min !== null && this.max !== null) return [this.min, this.max];
    if (this.smin === null) return [0, 1];
    if (this.smin === this.smax) return [this.smin - 1, this.smax + 1];
    return [this.smin, this.smax];
  };

  // ----------------------------------------------------------------- Base

  function WidgetBase(type, container, config) {
    this.type = type;
    this.container = container;
    this._destroyed = false;
    this._paused = false;
    this.channels = [];
    this._byId = {};
    this.root = mkEl("div", "cw cw-" + type);
    container.appendChild(this.root);
    this.config = this._defaults();
    this._applyConfig(config || {});
    this._buildDom();
    this._wireResize();
    scheduleDraw(this);
  }

  WidgetBase.prototype._defaults = function () {
    return {
      title: "", channels: [], min: 0, max: 100,
      warn: null, alarm: null, decimals: 1, smoothing: 0,
      windowSec: 60, orientation: "horizontal", mirror: false,
      sparkline: true, normalized: false, binned: true,
      trigger: null, xChannel: null, yChannel: null, onCursor: null
    };
  };

  WidgetBase.prototype._applyConfig = function (partial) {
    for (var k in partial) if (partial.hasOwnProperty(k)) this.config[k] = partial[k];
    if (partial.hasOwnProperty("channels")) this._syncChannels(this.config.channels || []);
  };

  WidgetBase.prototype._syncChannels = function (defs) {
    var byId = {}, list = [];
    for (var i = 0; i < defs.length; i++) {
      var d = defs[i];
      var existing = this._byId[d.id];
      if (existing) {
        existing.name = d.name || existing.name;
        if (d.unit !== undefined) existing.unit = d.unit;
        if (d.color) existing.color = d.color;
        if (d.min !== undefined) existing.min = d.min;
        if (d.max !== undefined) existing.max = d.max;
      } else {
        existing = new ChannelSeries(d);
      }
      byId[d.id] = existing;
      list.push(existing);
    }
    this.channels = list;
    this._byId = byId;
  };

  WidgetBase.prototype.setConfig = function (partial) {
    this._applyConfig(partial || {});
    this._onConfigChanged();
    scheduleDraw(this);
  };
  WidgetBase.prototype._onConfigChanged = function () {};

  WidgetBase.prototype.push = function (channelId, t, value) {
    if (this._destroyed) return;
    var ch = this._byId[channelId];
    if (!ch) return;
    var v = null;
    if (value !== null && value !== undefined) {
      var n = Number(value);
      v = isNum(n) ? n : null;
    }
    ch.push(t, v, this.config.smoothing);
    var keep = Math.max(this.config.windowSec || 60, 5) * 4;
    ch.trim(keep);
    scheduleDraw(this);
  };

  WidgetBase.prototype.stats = function (channelId) {
    var ch = this._byId[channelId];
    if (!ch) return { last: null, min: null, max: null, avg: null, n: 0 };
    return { last: ch.last, min: ch.smin, max: ch.smax, avg: ch.avg(), n: ch.n };
  };
  WidgetBase.prototype.resetStats = function () {
    for (var i = 0; i < this.channels.length; i++) this.channels[i].resetStats();
    scheduleDraw(this);
  };
  WidgetBase.prototype.level = function (channelId) {
    var ch = this._byId[channelId];
    if (!ch) return "ok";
    return levelOf(ch.last, this.config.warn, this.config.alarm);
  };
  WidgetBase.prototype.snapshot = function () {
    var out = {};
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i];
      out[ch.id] = { value: ch.last, unit: ch.unit, min: ch.smin, max: ch.smax, avg: ch.avg() };
    }
    return out;
  };
  WidgetBase.prototype.pause = function (b) {
    this._paused = !!b;
    if (!this._paused) this._onResume();
    scheduleDraw(this);
  };
  WidgetBase.prototype._onResume = function () {};
  WidgetBase.prototype.isPaused = function () { return this._paused; };
  WidgetBase.prototype.setWindow = function (sec) {
    this.config.windowSec = sec;
    this._onConfigChanged();
    scheduleDraw(this);
  };
  WidgetBase.prototype.setCursor = function (t) {};
  WidgetBase.prototype.resize = function () { this._layout(); scheduleDraw(this); };
  WidgetBase.prototype._layout = function () {};
  WidgetBase.prototype._wireResize = function () {
    var self = this;
    if (typeof ResizeObserver !== "undefined") {
      this._ro = new ResizeObserver(function () { self._layout(); scheduleDraw(self); });
      this._ro.observe(this.root);
    }
  };
  WidgetBase.prototype.destroy = function () {
    this._destroyed = true;
    unscheduleDraw(this);
    if (this._ro) this._ro.disconnect();
    this._teardown();
    if (this.root.parentNode) this.root.parentNode.removeChild(this.root);
  };
  WidgetBase.prototype._teardown = function () {};
  WidgetBase.prototype._buildDom = function () {};
  WidgetBase.prototype._draw = function () {};

  // helper used by several DOM widgets to keep a level-driven modifier class
  function setLevelClass(node, level) {
    node.classList.remove("lvl-ok", "lvl-warn", "lvl-alarm");
    node.classList.add("lvl-" + level);
  }

  // ================================================================= DIGITAL

  function DigitalWidget(container, config) { WidgetBase.call(this, "digital", container, config); }
  DigitalWidget.prototype = Object.create(WidgetBase.prototype);

  DigitalWidget.prototype._buildDom = function () {
    this.root.innerHTML =
      '<div class="cw-title"></div>' +
      '<div class="cw-digital-value"><span class="num">—</span><span class="unit"></span></div>' +
      '<div class="cw-digital-sub">' +
      '<span class="s-min">min —</span><span class="s-avg">avg —</span><span class="s-max">max —</span>' +
      '</div>';
    this._titleEl = this.root.querySelector(".cw-title");
    this._numEl = this.root.querySelector(".num");
    this._unitEl = this.root.querySelector(".unit");
    this._minEl = this.root.querySelector(".s-min");
    this._avgEl = this.root.querySelector(".s-avg");
    this._maxEl = this.root.querySelector(".s-max");
  };
  DigitalWidget.prototype._draw = function () {
    var ch = this.channels[0];
    this._titleEl.textContent = this.config.title || (ch ? ch.name : "");
    if (!ch) return;
    var d = this.config.decimals;
    this._numEl.textContent = format(ch.last, d);
    this._unitEl.textContent = ch.unit || "";
    this._minEl.textContent = "min " + format(ch.smin, d);
    this._avgEl.textContent = "avg " + format(ch.avg(), d);
    this._maxEl.textContent = "max " + format(ch.smax, d);
    setLevelClass(this.root, this.level(ch.id));
  };

  // ===================================================================== BAR

  function BarWidget(container, config) { WidgetBase.call(this, "bar", container, config); }
  BarWidget.prototype = Object.create(WidgetBase.prototype);

  BarWidget.prototype._buildDom = function () {
    this.root.innerHTML =
      '<div class="cw-title"></div>' +
      '<div class="cw-bar-track"><div class="cw-bar-zone warn"></div><div class="cw-bar-zone alarm"></div>' +
      '<div class="cw-bar-fill"></div><div class="cw-bar-peak"></div></div>' +
      '<div class="cw-bar-value"></div>';
    this._track = this.root.querySelector(".cw-bar-track");
    this._fill = this.root.querySelector(".cw-bar-fill");
    this._peak = this.root.querySelector(".cw-bar-peak");
    this._zoneWarn = this.root.querySelector(".cw-bar-zone.warn");
    this._zoneAlarm = this.root.querySelector(".cw-bar-zone.alarm");
    this._valueEl = this.root.querySelector(".cw-bar-value");
    this._titleEl = this.root.querySelector(".cw-title");
  };
  BarWidget.prototype._pct = function (v) {
    var lo = this.config.min, hi = this.config.max;
    if (hi === lo) return 0;
    return clamp((v - lo) / (hi - lo), 0, 1) * 100;
  };
  BarWidget.prototype._placeZone = function (node, band) {
    if (!band) { node.style.display = "none"; return; }
    node.style.display = "block";
    var a = this._pct(band[0]), b = this._pct(band[1]);
    var lo = Math.min(a, b), hi = Math.max(a, b);
    if (this.config.orientation === "vertical") {
      node.style.bottom = lo + "%"; node.style.top = "";
      node.style.height = (hi - lo) + "%"; node.style.left = "0"; node.style.width = "100%";
    } else {
      node.style.left = lo + "%"; node.style.width = (hi - lo) + "%";
      node.style.top = "0"; node.style.height = "100%";
    }
  };
  BarWidget.prototype._onConfigChanged = function () {
    this.root.classList.toggle("vertical", this.config.orientation === "vertical");
    this._placeZone(this._zoneWarn, this.config.warn);
    this._placeZone(this._zoneAlarm, this.config.alarm);
  };
  BarWidget.prototype._layout = function () { this._onConfigChanged(); };
  BarWidget.prototype._draw = function () {
    this._onConfigChanged();
    var ch = this.channels[0];
    this._titleEl.textContent = this.config.title || (ch ? ch.name : "");
    if (!ch) return;
    var pct = this._pct(ch.last === null ? this.config.min : ch.last);
    var vertical = this.config.orientation === "vertical";
    if (vertical) { this._fill.style.height = pct + "%"; this._fill.style.width = "100%"; }
    else { this._fill.style.width = pct + "%"; this._fill.style.height = "100%"; }
    var lvl = this.level(ch.id);
    this._fill.style.background = "var(" + levelVar(lvl) + ")";
    if (ch.peak !== null) {
      var ppct = this._pct(ch.peak);
      if (vertical) { this._peak.style.bottom = ppct + "%"; this._peak.style.display = "block"; }
      else { this._peak.style.left = ppct + "%"; this._peak.style.display = "block"; }
    } else {
      this._peak.style.display = "none";
    }
    this._valueEl.textContent = format(ch.last, this.config.decimals) + " " + (ch.unit || "");
  };

  // ==================================================================== DIAL

  var DIAL_MIN_ANGLE = -120, DIAL_MAX_ANGLE = 120; // 240 degree sweep, 0 = straight up

  function polar(cx, cy, r, angleDeg) {
    var rad = (angleDeg - 0) * Math.PI / 180;
    return { x: cx + r * Math.sin(rad), y: cy - r * Math.cos(rad) };
  }
  function arcPath(cx, cy, r, a0, a1) {
    var p0 = polar(cx, cy, r, a0), p1 = polar(cx, cy, r, a1);
    var large = (a1 - a0) > 180 ? 1 : 0;
    return "M " + p0.x.toFixed(2) + " " + p0.y.toFixed(2) +
      " A " + r + " " + r + " 0 " + large + " 1 " + p1.x.toFixed(2) + " " + p1.y.toFixed(2);
  }

  function DialWidget(container, config) { WidgetBase.call(this, "dial", container, config); }
  DialWidget.prototype = Object.create(WidgetBase.prototype);

  DialWidget.prototype._buildDom = function () {
    this.root.innerHTML = '<div class="cw-title"></div><div class="cw-dial-wrap"></div><div class="cw-dial-value"></div>';
    this._titleEl = this.root.querySelector(".cw-title");
    this._wrap = this.root.querySelector(".cw-dial-wrap");
    this._valueEl = this.root.querySelector(".cw-dial-value");
    this._svg = svgEl("svg", { viewBox: "0 0 200 140", class: "cw-dial-svg" });
    this._wrap.appendChild(this._svg);
    this._trackPath = svgEl("path", { class: "cw-dial-track" });
    this._warnPath = svgEl("path", { class: "cw-dial-warn" });
    this._alarmPath = svgEl("path", { class: "cw-dial-alarm" });
    this._ticksGroup = svgEl("g", { class: "cw-dial-ticks" });
    this._needle = svgEl("line", { class: "cw-dial-needle", x1: "100", y1: "100", x2: "100", y2: "35" });
    this._peakMark = svgEl("circle", { class: "cw-dial-peak", r: "3" });
    this._hub = svgEl("circle", { class: "cw-dial-hub", cx: "100", cy: "100", r: "6" });
    this._svg.appendChild(this._trackPath);
    this._svg.appendChild(this._warnPath);
    this._svg.appendChild(this._alarmPath);
    this._svg.appendChild(this._ticksGroup);
    this._svg.appendChild(this._peakMark);
    this._svg.appendChild(this._needle);
    this._svg.appendChild(this._hub);
    this._buildTicks();
  };
  DialWidget.prototype._angleFor = function (v) {
    var lo = this.config.min, hi = this.config.max;
    var f = hi === lo ? 0 : clamp((v - lo) / (hi - lo), 0, 1);
    return DIAL_MIN_ANGLE + f * (DIAL_MAX_ANGLE - DIAL_MIN_ANGLE);
  };
  DialWidget.prototype._buildTicks = function () {
    while (this._ticksGroup.firstChild) this._ticksGroup.removeChild(this._ticksGroup.firstChild);
    var lo = this.config.min, hi = this.config.max, steps = 4;
    for (var i = 0; i <= steps; i++) {
      var v = lo + (hi - lo) * (i / steps);
      var a = this._angleFor(v);
      var p1 = polar(100, 100, 78, a), p2 = polar(100, 100, 68, a);
      var tick = svgEl("line", { x1: p1.x.toFixed(2), y1: p1.y.toFixed(2), x2: p2.x.toFixed(2), y2: p2.y.toFixed(2), class: "cw-dial-tick" });
      this._ticksGroup.appendChild(tick);
      var lp = polar(100, 100, 58, a);
      var label = svgEl("text", { x: lp.x.toFixed(2), y: (lp.y + 3).toFixed(2), class: "cw-dial-ticklabel", "text-anchor": "middle" });
      label.textContent = format(v, this.config.decimals >= 1 ? 0 : this.config.decimals);
      this._ticksGroup.appendChild(label);
    }
  };
  DialWidget.prototype._onConfigChanged = function () {
    setAttrs(this._trackPath, { d: arcPath(100, 100, 80, DIAL_MIN_ANGLE, DIAL_MAX_ANGLE) });
    if (this.config.warn) {
      var w0 = this._angleFor(Math.min(this.config.warn[0], this.config.warn[1]));
      var w1 = this._angleFor(Math.max(this.config.warn[0], this.config.warn[1]));
      setAttrs(this._warnPath, { d: arcPath(100, 100, 80, w0, w1), display: "" });
    } else { this._warnPath.setAttribute("display", "none"); }
    if (this.config.alarm) {
      var l0 = this._angleFor(Math.min(this.config.alarm[0], this.config.alarm[1]));
      var l1 = this._angleFor(Math.max(this.config.alarm[0], this.config.alarm[1]));
      setAttrs(this._alarmPath, { d: arcPath(100, 100, 80, l0, l1), display: "" });
    } else { this._alarmPath.setAttribute("display", "none"); }
    this._buildTicks();
  };
  DialWidget.prototype._layout = function () {};
  DialWidget.prototype._draw = function () {
    this._onConfigChanged();
    var ch = this.channels[0];
    this._titleEl.textContent = this.config.title || (ch ? ch.name : "");
    if (!ch) return;
    var v = ch.ema !== null ? ch.ema : this.config.min;
    var a = this._angleFor(v);
    var tip = polar(100, 100, 78, a);
    setAttrs(this._needle, { x2: tip.x.toFixed(2), y2: tip.y.toFixed(2) });
    var lvl = this.level(ch.id);
    this._needle.setAttribute("stroke", "var(" + levelVar(lvl) + ")");
    if (ch.peak !== null) {
      var pp = polar(100, 100, 80, this._angleFor(ch.peak));
      setAttrs(this._peakMark, { cx: pp.x.toFixed(2), cy: pp.y.toFixed(2), display: "" });
    } else {
      this._peakMark.setAttribute("display", "none");
    }
    this._valueEl.textContent = format(ch.last, this.config.decimals) + " " + (ch.unit || "");
  };

  // ============================================================ GRAPH BASE
  // Shared canvas engine for line / multiline / stacked / scope / scatter.

  function GraphBase(type, container, config) {
    this._viewStart = null; this._viewEnd = null; // null = auto-follow
    this._hoverT = null; this._hoverX = null;
    this._dragging = false; this._dragStartX = 0; this._dragStartView = null;
    WidgetBase.call(this, type, container, config);
  }
  GraphBase.prototype = Object.create(WidgetBase.prototype);

  GraphBase.prototype._buildDom = function () {
    this.root.innerHTML = '<div class="cw-title"></div><div class="cw-graph-wrap"></div><div class="cw-legend"></div>';
    this._titleEl = this.root.querySelector(".cw-title");
    this._wrap = this.root.querySelector(".cw-graph-wrap");
    this._legend = this.root.querySelector(".cw-legend");
    this._canvas = mkEl("canvas", "cw-graph-canvas");
    this._wrap.appendChild(this._canvas);
    this._ctx = this._canvas.getContext("2d");
    this.root.tabIndex = 0;
    this._wireInteraction();
    this._buildLegend();
  };

  GraphBase.prototype._buildLegend = function () {
    this._legend.innerHTML = "";
    this._legendVals = [];
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i];
      var item = mkEl("span", "cw-legend-item");
      var swatch = mkEl("i", "cw-legend-swatch");
      swatch.style.background = ch.color || ("var(" + paletteVar(i) + ")");
      var label = mkEl("b");
      label.textContent = ch.name;
      var val = mkEl("span", "cw-legend-val");
      item.appendChild(swatch); item.appendChild(label); item.appendChild(val);
      this._legend.appendChild(item);
      this._legendVals.push(val);
    }
  };
  GraphBase.prototype._onConfigChanged = function () {
    if (this._legendVals.length !== this.channels.length) this._buildLegend();
  };

  GraphBase.prototype._resizeCanvas = function () {
    var dpr = global.devicePixelRatio || 1;
    var w = this._wrap.clientWidth || 300, h = this._wrap.clientHeight || 150;
    if (w < 10) w = 300;
    if (h < 10) h = 150;
    var pw = Math.round(w * dpr), ph = Math.round(h * dpr);
    if (this._canvas.width !== pw || this._canvas.height !== ph) {
      this._canvas.width = pw; this._canvas.height = ph;
    }
    this._canvas.style.width = w + "px";
    this._canvas.style.height = h + "px";
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._cw = w; this._ch = h;
  };
  GraphBase.prototype._layout = function () { this._resizeCanvas(); };

  GraphBase.prototype._latestT = function () {
    var t = null;
    for (var i = 0; i < this.channels.length; i++) {
      var buf = this.channels[i].buf;
      if (buf.length) { var lt = buf[buf.length - 1].t; if (t === null || lt > t) t = lt; }
    }
    return t;
  };
  GraphBase.prototype._defaultWindowSec = function () { return this.config.windowSec || 60; }; // scope overrides
  GraphBase.prototype._currentView = function () {
    var win = this._defaultWindowSec();
    if (this._viewStart !== null && this._viewEnd !== null) return [this._viewStart, this._viewEnd];
    var latest = this._latestT();
    if (latest === null) return [0, win];
    return [latest - win, latest];
  };
  GraphBase.prototype.pause = function (b) {
    WidgetBase.prototype.pause.call(this, b);
    if (this._paused && this._viewStart === null) {
      var v = this._currentView();
      this._viewStart = v[0]; this._viewEnd = v[1];
    }
  };
  GraphBase.prototype._onResume = function () { this._viewStart = null; this._viewEnd = null; };
  GraphBase.prototype.setCursor = function (t) {
    this._hoverT = t;
    scheduleDraw(this);
  };
  GraphBase.prototype._fireCursor = function (t) {
    if (typeof this.config.onCursor === "function") {
      try { this.config.onCursor(t); } catch (e) {}
    }
  };

  GraphBase.prototype._wireInteraction = function () {
    var self = this;
    this.root.addEventListener("keydown", function (ev) {
      if (ev.key === " " || ev.code === "Space") {
        ev.preventDefault();
        self.pause(!self._paused);
      }
    });
    this._canvas.addEventListener("click", function () { self.root.focus(); self.pause(!self._paused); });
    this._canvas.addEventListener("dblclick", function () {
      self._viewStart = null; self._viewEnd = null;
      scheduleDraw(self);
    });
    this._canvas.addEventListener("wheel", function (ev) {
      if (!self._paused) return;
      ev.preventDefault();
      var view = self._currentView();
      var span = view[1] - view[0];
      var rect = self._canvas.getBoundingClientRect();
      var frac = rect.width ? (ev.clientX - rect.left) / rect.width : 0.5;
      var anchor = view[0] + span * frac;
      var factor = ev.deltaY > 0 ? 1.15 : 0.87;
      var newSpan = clamp(span * factor, 0.5, 3600);
      self._viewStart = anchor - newSpan * frac;
      self._viewEnd = self._viewStart + newSpan;
      scheduleDraw(self);
    }, { passive: false });
    this._canvas.addEventListener("mousedown", function (ev) {
      if (!self._paused) return;
      self._dragging = true;
      self._dragStartX = ev.clientX;
      self._dragStartView = self._currentView();
    });
    global.addEventListener("mousemove", function (ev) {
      if (self._dragging) {
        var rect = self._canvas.getBoundingClientRect();
        if (!rect.width) return;
        var span = self._dragStartView[1] - self._dragStartView[0];
        var dx = ev.clientX - self._dragStartX;
        var dt = -(dx / rect.width) * span;
        self._viewStart = self._dragStartView[0] + dt;
        self._viewEnd = self._dragStartView[1] + dt;
        scheduleDraw(self);
      }
    });
    global.addEventListener("mouseup", function () { self._dragging = false; });
    this._canvas.addEventListener("mousemove", function (ev) {
      if (self._dragging) return;
      var rect = self._canvas.getBoundingClientRect();
      if (!rect.width) return;
      var view = self._currentView();
      var frac = (ev.clientX - rect.left) / rect.width;
      var t = view[0] + frac * (view[1] - view[0]);
      self._hoverT = t; self._hoverX = ev.clientX - rect.left;
      self._fireCursor(t);
      scheduleDraw(self);
    });
    this._canvas.addEventListener("mouseleave", function () {
      self._hoverT = null; self._hoverX = null;
      self._fireCursor(null);
      scheduleDraw(self);
    });
  };

  GraphBase.prototype._teardown = function () {};

  // shared low-level draw helpers ------------------------------------------

  function drawGrid(ctx, w, h, gridColor, textColor, yLabels, xLabels) {
    ctx.save();
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.font = "10px " + (getComputedStyle(document.body).fontFamily || "sans-serif");
    ctx.fillStyle = textColor;
    for (var i = 0; i < yLabels.length; i++) {
      var yl = yLabels[i];
      ctx.beginPath();
      ctx.moveTo(0, yl.y + 0.5); ctx.lineTo(w, yl.y + 0.5);
      ctx.stroke();
      ctx.fillText(yl.text, 4, Math.max(10, yl.y - 3));
    }
    for (var j = 0; j < xLabels.length; j++) {
      var xl = xLabels[j];
      ctx.fillText(xl.text, clamp(xl.x - 12, 2, w - 30), h - 3);
    }
    ctx.restore();
  }

  function niceYLabels(lo, hi, h, count) {
    var out = [];
    for (var i = 0; i <= count; i++) {
      var v = lo + (hi - lo) * (i / count);
      var y = h - (h * (i / count));
      out.push({ v: v, y: y, text: format(v, 1) });
    }
    return out;
  }

  function shadeBand(ctx, w, y0, y1, color) {
    ctx.save();
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.22;
    ctx.fillRect(0, Math.min(y0, y1), w, Math.abs(y1 - y0));
    ctx.restore();
  }

  function yScaler(lo, hi, h) {
    var span = (hi - lo) || 1;
    return function (v) { return h - ((v - lo) / span) * h; };
  }

  // ===================================================================== LINE

  function LineWidget(container, config) { GraphBase.call(this, "line", container, config); }
  LineWidget.prototype = Object.create(GraphBase.prototype);

  LineWidget.prototype._draw = function () {
    this._resizeCanvas();
    var ctx = this._ctx, w = this._cw, h = this._ch;
    var ch = this.channels[0];
    this._titleEl.textContent = this.config.title || (ch ? ch.name : "");
    ctx.clearRect(0, 0, w, h);
    if (!ch) return;
    var view = this._currentView();
    var lo = this.config.min, hi = this.config.max;
    var scaleY = yScaler(lo, hi, h);
    var gridColor = cssVar(this.root, "--rule-soft") || "#333";
    var textColor = cssVar(this.root, "--ink-3") || "#888";
    if (this.config.warn) shadeBand(ctx, w, scaleY(this.config.warn[0]), scaleY(this.config.warn[1]), cssVar(this.root, "--sev-chronic"));
    if (this.config.alarm) shadeBand(ctx, w, scaleY(this.config.alarm[0]), scaleY(this.config.alarm[1]), cssVar(this.root, "--sev-returned"));
    var yl = niceYLabels(lo, hi, h, 4);
    drawGrid(ctx, w, h, gridColor, textColor, yl, []);
    this._plotTrace(ctx, ch, view, w, h, lo, hi, ch.color || cssVar(this.root, "--ok"));
    this._drawCursor(ctx, w, h, view);
    if (this._legendVals[0]) {
      this._legendVals[0].textContent = format(ch.last, this.config.decimals) + (ch.unit ? " " + ch.unit : "");
    }
  };
  LineWidget.prototype._plotTrace = function (ctx, ch, view, w, h, lo, hi, color) {
    var scaleX = function (t) { return ((t - view[0]) / (view[1] - view[0])) * w; };
    var scaleY = yScaler(lo, hi, h);
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false;
    var buf = ch.buf;
    for (var i = 0; i < buf.length; i++) {
      var p = buf[i];
      if (p.t < view[0] - (view[1] - view[0]) * 0.05 || p.t > view[1] + (view[1] - view[0]) * 0.05) {
        if (p.t > view[1] * 2 + 1e9) continue; // cheap skip guard, buffers already trimmed
      }
      if (p.v === null) { started = false; continue; }
      var x = scaleX(p.t), y = scaleY(p.v);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    ctx.restore();
  };
  LineWidget.prototype._drawCursor = function (ctx, w, h, view) {
    if (this._hoverT === null) return;
    var x = ((this._hoverT - view[0]) / (view[1] - view[0])) * w;
    if (x < 0 || x > w) return;
    ctx.save();
    ctx.strokeStyle = cssVar(this.root, "--ink-3");
    ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, h); ctx.stroke();
    ctx.restore();
  };

  // ================================================================ MULTILINE

  function MultilineWidget(container, config) { GraphBase.call(this, "multiline", container, config); }
  MultilineWidget.prototype = Object.create(GraphBase.prototype);

  MultilineWidget.prototype._draw = function () {
    this._resizeCanvas();
    var ctx = this._ctx, w = this._cw, h = this._ch;
    this._titleEl.textContent = this.config.title || "";
    ctx.clearRect(0, 0, w, h);
    var view = this._currentView();
    var gridColor = cssVar(this.root, "--rule-soft") || "#333";
    var textColor = cssVar(this.root, "--ink-3") || "#888";
    var normalized = !!this.config.normalized;
    // left axis from channel 0, right axis from channel 1 (if present)
    var leftLabels = [], rightLabels = [];
    if (this.channels[0]) {
      var r0 = normalized ? [0, 1] : this.channels[0].observedRange();
      leftLabels = niceYLabels(r0[0], r0[1], h, 4);
    }
    drawGrid(ctx, w, h, gridColor, textColor, leftLabels, []);
    if (this.channels[1] && !normalized) {
      var r1 = this.channels[1].observedRange();
      rightLabels = niceYLabels(r1[0], r1[1], h, 4);
      ctx.save();
      ctx.fillStyle = textColor;
      ctx.font = "10px sans-serif";
      for (var i = 0; i < rightLabels.length; i++) {
        ctx.fillText(rightLabels[i].text, w - 30, Math.max(10, rightLabels[i].y - 3));
      }
      ctx.restore();
    }
    for (var c = 0; c < this.channels.length; c++) {
      var ch = this.channels[c];
      var range = normalized ? [0, 1] : ch.observedRange();
      var color = ch.color || ("var(" + paletteVar(c) + ")");
      var resolved = color.indexOf("var(") === 0 ? cssVar(this.root, color.slice(4, -1)) : color;
      this._plotChannel(ctx, ch, view, w, h, range, resolved, normalized);
      if (this._legendVals[c]) {
        this._legendVals[c].textContent = format(ch.last, this.config.decimals) + (ch.unit ? " " + ch.unit : "");
      }
    }
    this._drawCursorMulti(ctx, w, h, view);
  };
  MultilineWidget.prototype._plotChannel = function (ctx, ch, view, w, h, range, color, normalized) {
    var scaleX = function (t) { return ((t - view[0]) / (view[1] - view[0])) * w; };
    var lo = range[0], hi = range[1];
    var span = (hi - lo) || 1;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false, buf = ch.buf;
    for (var i = 0; i < buf.length; i++) {
      var p = buf[i];
      if (p.v === null) { started = false; continue; }
      var vv = normalized ? (p.v - lo) / span : p.v;
      var y = h - ((vv - (normalized ? 0 : lo)) / (normalized ? 1 : span)) * h;
      var x = scaleX(p.t);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    ctx.restore();
  };
  MultilineWidget.prototype._drawCursorMulti = function (ctx, w, h, view) {
    if (this._hoverT === null) return;
    var x = ((this._hoverT - view[0]) / (view[1] - view[0])) * w;
    if (x < 0 || x > w) return;
    ctx.save();
    ctx.strokeStyle = cssVar(this.root, "--ink-3");
    ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, h); ctx.stroke();
    ctx.restore();
  };

  // =================================================================== STACKED

  function StackedWidget(container, config) { GraphBase.call(this, "stacked", container, config); }
  StackedWidget.prototype = Object.create(GraphBase.prototype);

  StackedWidget.prototype._draw = function () {
    this._resizeCanvas();
    var ctx = this._ctx, w = this._cw, h = this._ch;
    this._titleEl.textContent = this.config.title || "";
    ctx.clearRect(0, 0, w, h);
    var n = Math.max(this.channels.length, 1);
    var laneH = h / n;
    var view = this._currentView();
    var gridColor = cssVar(this.root, "--rule-soft") || "#333";
    var textColor = cssVar(this.root, "--ink-3") || "#888";
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i];
      var top = i * laneH;
      ctx.save();
      ctx.translate(0, top);
      ctx.strokeStyle = gridColor;
      ctx.strokeRect(0, 0, w, laneH);
      var range = ch.observedRange();
      var color = ch.color || ("var(" + paletteVar(i) + ")");
      var resolved = color.indexOf("var(") === 0 ? cssVar(this.root, color.slice(4, -1)) : color;
      this._plotLane(ctx, ch, view, w, laneH, range, resolved);
      ctx.fillStyle = textColor;
      ctx.font = "10px sans-serif";
      ctx.fillText(ch.name + (ch.unit ? " (" + ch.unit + ")" : ""), 4, 11);
      if (this._hoverT !== null) {
        var x = ((this._hoverT - view[0]) / (view[1] - view[0])) * w;
        if (x >= 0 && x <= w) {
          ctx.strokeStyle = textColor;
          ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, laneH); ctx.stroke();
          var val = this._valueAt(ch, this._hoverT);
          ctx.fillText(format(val, this.config.decimals), clamp(x + 4, 0, w - 40), 22);
        }
      }
      ctx.restore();
      if (this._legendVals[i]) {
        this._legendVals[i].textContent = format(ch.last, this.config.decimals) + (ch.unit ? " " + ch.unit : "");
      }
    }
  };
  StackedWidget.prototype._plotLane = function (ctx, ch, view, w, h, range, color) {
    var scaleX = function (t) { return ((t - view[0]) / (view[1] - view[0])) * w; };
    var scaleY = yScaler(range[0], range[1], h * 0.85);
    ctx.save();
    ctx.translate(0, h * 0.1);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false, buf = ch.buf;
    for (var i = 0; i < buf.length; i++) {
      var p = buf[i];
      if (p.v === null) { started = false; continue; }
      var x = scaleX(p.t), y = scaleY(p.v);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    ctx.restore();
  };
  StackedWidget.prototype._valueAt = function (ch, t) {
    var buf = ch.buf, best = null, bestDt = Infinity;
    for (var i = 0; i < buf.length; i++) {
      var dt = Math.abs(buf[i].t - t);
      if (dt < bestDt) { bestDt = dt; best = buf[i].v; }
    }
    return best;
  };
  StackedWidget.prototype._wireInteraction = function () {
    GraphBase.prototype._wireInteraction.call(this);
    var self = this;
    this._canvas.addEventListener("mousemove", function () { self._fireCursor(self._hoverT); });
    this._canvas.addEventListener("mouseleave", function () { self._fireCursor(null); });
  };

  // ==================================================================== SCOPE

  function ScopeWidget(container, config) {
    config = config || {};
    if (config.windowSec === undefined) config.windowSec = 5;
    GraphBase.call(this, "scope", container, config);
    this._sweeps = [];   // completed, persisted sweeps: [{points:[{t,v}]}], newest first
    this._pending = null; // {t0, points} sweep currently being filled, not drawn until complete
    this._armed = true;
  }
  ScopeWidget.prototype = Object.create(GraphBase.prototype);

  ScopeWidget.prototype._defaultWindowSec = function () { return this.config.windowSec || 5; };

  // Trigger handling has to work forward-only (we only ever see data as it
  // arrives): a rising edge starts a pending sweep, which fills for
  // windowSec of *incoming* samples and only then joins the faded history.
  // The display stays on the previous completed sweep meanwhile -- that is
  // the "freeze" the contract describes.
  ScopeWidget.prototype.push = function (channelId, t, value) {
    GraphBase.prototype.push.call(this, channelId, t, value);
    var trig = this.config.trigger;
    if (trig === null || trig === undefined) return;
    if (!this.channels[0] || channelId !== this.channels[0].id) return;
    var ch = this._byId[channelId];
    var buf = ch.buf;
    if (!buf.length) return;
    var cur = buf[buf.length - 1].v;
    var prev = buf.length >= 2 ? buf[buf.length - 2].v : null;
    var win = this._defaultWindowSec();

    if (this._pending) {
      this._pending.points.push({ t: t - this._pending.t0, v: cur });
      if (t - this._pending.t0 >= win) {
        this._sweeps.unshift(this._pending);
        if (this._sweeps.length > 3) this._sweeps.length = 3;
        this._pending = null;
      }
      return;
    }
    if (prev !== null && cur !== null && prev < trig && cur >= trig && this._armed) {
      this._pending = { t0: t, points: [{ t: 0, v: cur }] };
      this._armed = false;
    } else if (cur !== null && cur < trig) {
      this._armed = true;
    }
  };
  ScopeWidget.prototype._draw = function () {
    this._resizeCanvas();
    var ctx = this._ctx, w = this._cw, h = this._ch;
    var ch = this.channels[0];
    this._titleEl.textContent = this.config.title || (ch ? ch.name : "");
    ctx.clearRect(0, 0, w, h);
    if (!ch) return;
    var lo = this.config.min, hi = this.config.max;
    var scaleY = yScaler(lo, hi, h);
    var gridColor = cssVar(this.root, "--rule-soft") || "#333";
    var textColor = cssVar(this.root, "--ink-3") || "#888";
    if (this.config.warn) shadeBand(ctx, w, scaleY(this.config.warn[0]), scaleY(this.config.warn[1]), cssVar(this.root, "--sev-chronic"));
    if (this.config.alarm) shadeBand(ctx, w, scaleY(this.config.alarm[0]), scaleY(this.config.alarm[1]), cssVar(this.root, "--sev-returned"));
    drawGrid(ctx, w, h, gridColor, textColor, niceYLabels(lo, hi, h, 4), []);
    var win = this._defaultWindowSec();
    var color = ch.color || cssVar(this.root, "--ok");
    if (this.config.trigger !== null && this.config.trigger !== undefined) {
      for (var s = this._sweeps.length - 1; s >= 0; s--) {
        var fade = s === 0 ? 1 : (s === 1 ? 0.45 : 0.22);
        this._plotSweep(ctx, this._sweeps[s].points, win, w, h, lo, hi, color, fade);
      }
    } else {
      var view = this._currentView();
      this._plotFreerun(ctx, ch, view, w, h, lo, hi, color);
    }
    if (this._legendVals[0]) {
      this._legendVals[0].textContent = format(ch.last, this.config.decimals) + (ch.unit ? " " + ch.unit : "");
    }
  };
  ScopeWidget.prototype._plotSweep = function (ctx, points, win, w, h, lo, hi, color, alpha) {
    var scaleX = function (t) { return (t / win) * w; };
    var scaleY = yScaler(lo, hi, h);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false;
    for (var i = 0; i < points.length; i++) {
      var p = points[i];
      if (p.v === null) { started = false; continue; }
      var x = scaleX(p.t), y = scaleY(p.v);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    ctx.restore();
  };
  ScopeWidget.prototype._plotFreerun = LineWidget.prototype._plotTrace;

  // =================================================================== SCATTER

  function ScatterWidget(container, config) {
    GraphBase.call(this, "scatter", container, config);
    this._trail = []; // [{x,y,t}]
    this._lastX = null; this._lastY = null;
  }
  ScatterWidget.prototype = Object.create(GraphBase.prototype);

  ScatterWidget.prototype.push = function (channelId, t, value) {
    GraphBase.prototype.push.call(this, channelId, t, value);
    var xc = this.config.xChannel, yc = this.config.yChannel;
    if (!xc || !yc) return;
    var xch = this._byId[xc], ych = this._byId[yc];
    if (!xch || !ych) return;
    if (channelId === xc) this._lastX = (value === null) ? null : Number(value);
    if (channelId === yc) this._lastY = (value === null) ? null : Number(value);
    if (this._lastX !== null && this._lastY !== null && isNum(this._lastX) && isNum(this._lastY)) {
      this._trail.push({ x: this._lastX, y: this._lastY, t: t });
      var cutoff = t - (this.config.windowSec || 60);
      while (this._trail.length && this._trail[0].t < cutoff) this._trail.shift();
      if (this._trail.length > 4000) this._trail.splice(0, this._trail.length - 4000);
    }
  };
  ScatterWidget.prototype._draw = function () {
    this._resizeCanvas();
    var ctx = this._ctx, w = this._cw, h = this._ch;
    this._titleEl.textContent = this.config.title || "";
    ctx.clearRect(0, 0, w, h);
    var xch = this._byId[this.config.xChannel], ych = this._byId[this.config.yChannel];
    var gridColor = cssVar(this.root, "--rule-soft") || "#333";
    var textColor = cssVar(this.root, "--ink-3") || "#888";
    var xr = xch ? xch.observedRange() : [0, 1];
    var yr = ych ? ych.observedRange() : [0, 1];
    drawGrid(ctx, w, h, gridColor, textColor, niceYLabels(yr[0], yr[1], h, 4), []);
    var scaleX = function (v) { return ((v - xr[0]) / ((xr[1] - xr[0]) || 1)) * w; };
    var scaleY = yScaler(yr[0], yr[1], h);
    var n = this._trail.length;
    var color = cssVar(this.root, "--ok");
    for (var i = 0; i < n; i++) {
      var p = this._trail[i];
      var age = (n - i) / n;
      ctx.save();
      ctx.globalAlpha = 0.15 + 0.75 * (1 - age);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(scaleX(p.x), scaleY(p.y), 2.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
    if (this.config.binned !== false && n > 4) {
      this._plotBinned(ctx, xr, scaleX, scaleY, textColor);
    }
    if (this._legendVals[0] && xch) this._legendVals[0].textContent = format(xch.last, this.config.decimals) + (xch.unit ? " " + xch.unit : "");
    if (this._legendVals[1] && ych) this._legendVals[1].textContent = format(ych.last, this.config.decimals) + (ych.unit ? " " + ych.unit : "");
  };
  ScatterWidget.prototype._plotBinned = function (ctx, xr, scaleX, scaleY, color) {
    var bins = 16, sums = new Array(bins).fill(0), counts = new Array(bins).fill(0);
    var span = (xr[1] - xr[0]) || 1;
    for (var i = 0; i < this._trail.length; i++) {
      var p = this._trail[i];
      var b = clamp(Math.floor(((p.x - xr[0]) / span) * bins), 0, bins - 1);
      sums[b] += p.y; counts[b]++;
    }
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false;
    for (var b2 = 0; b2 < bins; b2++) {
      if (!counts[b2]) continue;
      var avg = sums[b2] / counts[b2];
      var x = scaleX(xr[0] + span * ((b2 + 0.5) / bins));
      var y = scaleY(avg);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    ctx.restore();
  };

  // ===================================================================== TABLE

  function TableWidget(container, config) { WidgetBase.call(this, "table", container, config); }
  TableWidget.prototype = Object.create(WidgetBase.prototype);

  TableWidget.prototype._buildDom = function () {
    this.root.innerHTML =
      '<div class="cw-title"></div>' +
      '<table class="cw-table"><thead><tr>' +
      '<th>Name</th><th class="n">Value</th><th>Unit</th><th class="n">Min</th><th class="n">Max</th><th class="n">Avg</th><th>Level</th><th>Trend</th>' +
      '</tr></thead><tbody></tbody></table>';
    this._titleEl = this.root.querySelector(".cw-title");
    this._tbody = this.root.querySelector("tbody");
    this._rows = {};
  };
  TableWidget.prototype._ensureRows = function () {
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i];
      if (this._rows[ch.id]) continue;
      var tr = mkEl("tr");
      tr.innerHTML =
        '<td class="cname"></td><td class="n cval"></td><td class="cunit"></td>' +
        '<td class="n cmin"></td><td class="n cmax"></td><td class="n cavg"></td>' +
        '<td><span class="chip clvl"></span></td><td class="cspark"></td>';
      this._tbody.appendChild(tr);
      var spark = svgEl("svg", { viewBox: "0 0 60 18", class: "cw-spark" });
      var poly = svgEl("polyline", { points: "", class: "cw-spark-line" });
      spark.appendChild(poly);
      tr.querySelector(".cspark").appendChild(spark);
      this._rows[ch.id] = {
        tr: tr, name: tr.querySelector(".cname"), val: tr.querySelector(".cval"),
        unit: tr.querySelector(".cunit"), min: tr.querySelector(".cmin"), max: tr.querySelector(".cmax"),
        avg: tr.querySelector(".cavg"), lvl: tr.querySelector(".clvl"), poly: poly
      };
    }
  };
  TableWidget.prototype._onConfigChanged = function () { this._ensureRows(); };
  TableWidget.prototype._draw = function () {
    this._ensureRows();
    this._titleEl.textContent = this.config.title || "";
    var d = this.config.decimals;
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i], row = this._rows[ch.id];
      row.name.textContent = ch.name;
      row.val.textContent = format(ch.last, d);
      row.unit.textContent = ch.unit || "";
      row.min.textContent = format(ch.smin, d);
      row.max.textContent = format(ch.smax, d);
      row.avg.textContent = format(ch.avg(), d);
      var lvl = this.level(ch.id);
      row.lvl.textContent = lvl;
      row.lvl.className = "chip clvl " + (lvl === "ok" ? "ok" : lvl === "warn" ? "chronic" : "returned");
      if (this.config.sparkline !== false) {
        var buf = ch.buf, n = buf.length, pts = [];
        var take = buf.slice(Math.max(0, n - 30));
        var range = ch.observedRange();
        var span = (range[1] - range[0]) || 1;
        for (var j = 0; j < take.length; j++) {
          if (take[j].v === null) continue;
          var x = (j / Math.max(1, take.length - 1)) * 60;
          var y = 16 - ((take[j].v - range[0]) / span) * 14;
          pts.push(x.toFixed(1) + "," + y.toFixed(1));
        }
        row.poly.setAttribute("points", pts.join(" "));
      }
    }
  };

  // ===================================================================== TILES

  function TilesWidget(container, config) { WidgetBase.call(this, "tiles", container, config); }
  TilesWidget.prototype = Object.create(WidgetBase.prototype);

  TilesWidget.prototype._buildDom = function () {
    this.root.innerHTML = '<div class="cw-title"></div><div class="cw-tiles-grid"></div>';
    this._titleEl = this.root.querySelector(".cw-title");
    this._grid = this.root.querySelector(".cw-tiles-grid");
    this._tiles = {};
  };
  TilesWidget.prototype._ensureTiles = function () {
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i];
      if (this._tiles[ch.id]) continue;
      var tile = mkEl("div", "cw-tile");
      tile.innerHTML = '<div class="cw-tile-label"></div><div class="cw-tile-value"><span class="num"></span><span class="unit"></span></div>';
      this._grid.appendChild(tile);
      this._tiles[ch.id] = { tile: tile, label: tile.querySelector(".cw-tile-label"), num: tile.querySelector(".num"), unit: tile.querySelector(".unit") };
    }
  };
  TilesWidget.prototype._onConfigChanged = function () { this._ensureTiles(); };
  TilesWidget.prototype._draw = function () {
    this._ensureTiles();
    this._titleEl.textContent = this.config.title || "";
    for (var i = 0; i < this.channels.length; i++) {
      var ch = this.channels[i], t = this._tiles[ch.id];
      t.label.textContent = ch.name;
      t.num.textContent = format(ch.last, this.config.decimals);
      t.unit.textContent = ch.unit || "";
      setLevelClass(t.tile, this.level(ch.id));
    }
  };

  // ======================================================================= HUD

  function HudWidget(container, config) { WidgetBase.call(this, "hud", container, config); }
  HudWidget.prototype = Object.create(WidgetBase.prototype);

  HudWidget.prototype._buildDom = function () {
    this.root.innerHTML = '<div class="cw-hud-label"></div><div class="cw-hud-value"><span class="num"></span><span class="unit"></span></div>';
    this._labelEl = this.root.querySelector(".cw-hud-label");
    this._numEl = this.root.querySelector(".num");
    this._unitEl = this.root.querySelector(".unit");
  };
  HudWidget.prototype._onConfigChanged = function () {
    this.root.style.transform = this.config.mirror ? "scaleX(-1)" : "";
  };
  HudWidget.prototype._draw = function () {
    this._onConfigChanged();
    var ch = this.channels[0];
    this._labelEl.textContent = this.config.title || (ch ? ch.name : "");
    if (!ch) return;
    this._numEl.textContent = format(ch.last, this.config.decimals);
    this._unitEl.textContent = ch.unit || "";
    setLevelClass(this.root, this.level(ch.id));
  };

  // ================================================================ REGISTRY

  var REGISTRY = {
    digital:   { ctor: DigitalWidget,   label: "Digital",   multiChannel: false, minChannels: 1, maxChannels: 1,  defaultSize: [1, 1] },
    bar:       { ctor: BarWidget,       label: "Bar",       multiChannel: false, minChannels: 1, maxChannels: 1,  defaultSize: [1, 2] },
    dial:      { ctor: DialWidget,      label: "Dial",      multiChannel: false, minChannels: 1, maxChannels: 1,  defaultSize: [2, 2] },
    line:      { ctor: LineWidget,      label: "Line",      multiChannel: false, minChannels: 1, maxChannels: 1,  defaultSize: [3, 2] },
    multiline: { ctor: MultilineWidget, label: "Multiline", multiChannel: true,  minChannels: 2, maxChannels: 4,  defaultSize: [3, 2] },
    stacked:   { ctor: StackedWidget,   label: "Stacked",   multiChannel: true,  minChannels: 2, maxChannels: 8,  defaultSize: [3, 3] },
    scope:     { ctor: ScopeWidget,     label: "Scope",     multiChannel: true,  minChannels: 1, maxChannels: 2,  defaultSize: [3, 2] },
    scatter:   { ctor: ScatterWidget,   label: "Scatter",   multiChannel: true,  minChannels: 2, maxChannels: 2,  defaultSize: [2, 2] },
    table:     { ctor: TableWidget,     label: "Table",     multiChannel: true,  minChannels: 1, maxChannels: 32, defaultSize: [3, 3] },
    tiles:     { ctor: TilesWidget,     label: "Tiles",     multiChannel: true,  minChannels: 1, maxChannels: 16, defaultSize: [2, 2] },
    hud:       { ctor: HudWidget,       label: "HUD",       multiChannel: false, minChannels: 1, maxChannels: 1,  defaultSize: [2, 1] }
  };

  var types = {};
  for (var key in REGISTRY) {
    if (!REGISTRY.hasOwnProperty(key)) continue;
    types[key] = {
      label: REGISTRY[key].label, multiChannel: REGISTRY[key].multiChannel,
      minChannels: REGISTRY[key].minChannels, maxChannels: REGISTRY[key].maxChannels,
      defaultSize: REGISTRY[key].defaultSize.slice()
    };
  }

  function create(type, containerEl, config) {
    var entry = REGISTRY[type];
    if (!entry) throw new Error("CuoreWidgets.create: unknown widget type '" + type + "'");
    if (!containerEl) throw new Error("CuoreWidgets.create: containerEl is required");
    return new entry.ctor(containerEl, config || {});
  }

  global.CuoreWidgets = { types: types, create: create, format: format };

})(typeof window !== "undefined" ? window : this);
