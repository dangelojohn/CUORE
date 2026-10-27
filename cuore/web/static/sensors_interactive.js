/* Sensors outline (.si). The partial works with no script; this only upgrades it.
 *
 * Tap a sensor (a marker, a partner link or an unplaced link): the sensor and its cross-check partners are
 * highlighted on both views (solid ring = selected, dashed blue ring = partner) and its card is shown inline.
 * The fold under the drawing still lists every card; with script it starts collapsed.
 *
 * Live: when the server saw a connected session (.si[data-live="1"]) the existing SSE stream
 * (/api/live/stream, messages {t, channel, value, unit}) moves the value and the marker of the open card's
 * rows. The stream closes when the page is hidden or left; an error closes it and retries with exponential
 * back-off (2, 4, 8, 16, 32 s), then stops and says so -- never a reconnect storm. EventSource's own automatic
 * reconnect is not used. An unreadable sample never becomes 0; a value no quantity can have, or a
 * "not available" marker, is shown as invalid and not judged. Partner verdicts stay as saved (they are
 * computed from saved readings, so they are not recomputed here).
 */
(function (global) {
  "use strict";
  if (global.CuoreSensorsInteractive) { global.CuoreSensorsInteractive.init(); return; }

  var BACKOFF_S = [2, 4, 8, 16, 32];
  var STALE_MS = 20000;
  var NA_MARKERS = [-32768, -32767];

  function fmt(v) { return Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : (Math.abs(v) >= 10 ? v.toFixed(1) : String(parseFloat(v.toPrecision(3)))); }
  function pct(v, lo, hi) { return hi > lo ? Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100)) : 0; }
  function all(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
  function num(a) { if (a === null || a === "") return null; var n = parseFloat(a); return isFinite(n) ? n : null; }

  function Outline(root) {
    this.root = root;
    this.pop = root.querySelector("#si-pop");
    this.fold = root.querySelector("#si-fold");
    this.status = root.querySelector("#si-stream");
    this.url = root.getAttribute("data-stream") || "/api/live/stream";
    this.live = root.getAttribute("data-live") === "1";
    this.rows = {}; this.rpm = null; this.pending = {}; this.queued = false;
    this.es = null; this.tries = 0; this.timer = null; this.closed = false; this.reason = "";
    var self = this;
    if (this.fold) this.fold.removeAttribute("open");   // cards show on tap; the fold still lists them all
    root.addEventListener("click", function (ev) {
      var a = ev.target.closest ? ev.target.closest("a[data-sensor]") : null;
      if (!a || !root.contains(a)) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button === 1) return;
      var card = global.document.getElementById("si-card-" + a.getAttribute("data-sensor"));
      if (!card) return;
      ev.preventDefault();
      self.show(card, a);
    });
    global.document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") self.hide(); });
    this.collect();
    if (this.live) {
      this.ager = global.setInterval(function () { self.age(); }, 5000);
      global.document.addEventListener("visibilitychange", function () {
        if (global.document.hidden) self.stop("hidden"); else if (self.closed && self.reason === "paused") self.start();
      });
      global.addEventListener("pagehide", function () { self.stop("left"); global.clearInterval(self.ager); });
      this.start();
    }
  }

  Outline.prototype.say = function (state, text) {
    if (!this.status) return;
    this.status.setAttribute("data-state", state);
    this.status.textContent = (state === "live" ? "● " : "○ ") + text;
  };

  Outline.prototype.collect = function () {
    var self = this;
    this.rows = {};
    all(this.pop, ".si-row[data-channel]").forEach(function (li) {
      var id = li.getAttribute("data-channel");
      (self.rows[id] = self.rows[id] || []).push({
        li: li, last: 0, min: num(li.getAttribute("data-min")), max: num(li.getAttribute("data-max")),
        blo: num(li.getAttribute("data-blo")), bhi: num(li.getAttribute("data-bhi")),
        plo: num(li.getAttribute("data-plo")), phi: num(li.getAttribute("data-phi")),
        idle: li.getAttribute("data-idle") === "1", applies: li.getAttribute("data-applies"),
        cond: li.getAttribute("data-cond") || "", unit: li.getAttribute("data-unit") || "",
        validity: li.getAttribute("data-validity") || "ok"
      });
    });
  };

  // ---- selection ------------------------------------------------------------------------------------
  Outline.prototype.mark = function (id, partners) {
    var set = {}; (partners || []).forEach(function (p) { set[p] = true; });
    all(this.root, ".si-stage > .si-mark").forEach(function (m) {
      var sid = m.getAttribute("data-sensor");
      m.classList.toggle("is-sel", !!id && sid === id);
      m.classList.toggle("is-partner", !!id && !!set[sid]);
      if (id && sid === id) m.setAttribute("aria-current", "true"); else m.removeAttribute("aria-current");
    });
  };
  Outline.prototype.show = function (card, trigger) {
    var pop = this.pop, id = card.getAttribute("data-sensor");
    var partners = (card.getAttribute("data-partners") || "").split(" ").filter(Boolean);
    this.mark(id, partners);
    pop.textContent = "";
    var copy = card.cloneNode(true);
    copy.removeAttribute("id"); copy.removeAttribute("tabindex");
    pop.appendChild(copy);
    var close = global.document.createElement("button");
    close.type = "button"; close.className = "si-btn si-pop-close"; close.textContent = "Close";
    var self = this;
    close.addEventListener("click", function () { self.hide(trigger); });
    pop.appendChild(close);
    pop.hidden = false;
    this.collect();
    if (pop.scrollIntoView) pop.scrollIntoView({ block: "nearest" });
  };
  Outline.prototype.hide = function (trigger) {
    if (this.pop.hidden) return;
    this.pop.hidden = true; this.pop.textContent = "";
    this.mark(null, []);
    this.rows = {};
    if (trigger && trigger.focus) trigger.focus();
  };

  // ---- live ---------------------------------------------------------------------------------------------
  Outline.prototype.start = function () {
    var self = this;
    if (!global.EventSource) { this.say("off", "Live update needs a newer browser; showing the last recorded values."); return; }
    this.stop(null, true);
    this.closed = false;
    var es;
    try { es = new global.EventSource(this.url); } catch (e) { this.say("off", "Could not open the live stream."); return; }
    this.es = es;
    es.onopen = function () { self.say("live", "Live: the open card's values update as the session reads them."); };
    es.onmessage = function (ev) {
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (!m || m.channel === undefined) return;
      self.tries = 0;
      if (m.channel === "engine_rpm") { var r = typeof m.value === "number" ? m.value : parseFloat(m.value); if (isFinite(r)) self.rpm = r; }
      if (!self.rows[m.channel]) return;
      self.pending[m.channel] = m;
      if (!self.queued) { self.queued = true; global.requestAnimationFrame(function () { self.queued = false; self.flush(); }); }
    };
    es.onerror = function () {
      try { es.close(); } catch (e) {}
      self.es = null;
      if (self.tries >= BACKOFF_S.length) {
        self.closed = true; self.reason = "gave up";
        self.say("off", "Live stream closed. Reload the page to try again; showing the last values.");
        return;
      }
      var wait = BACKOFF_S[self.tries++];
      self.say("off", "Live stream interrupted; retrying in " + wait + " s.");
      self.timer = global.setTimeout(function () { self.timer = null; self.start(); }, wait * 1000);
    };
  };
  Outline.prototype.stop = function (why, quiet) {
    if (this.timer) { global.clearTimeout(this.timer); this.timer = null; }
    if (this.es) { try { this.es.close(); } catch (e) {} this.es = null; }
    if (!quiet) {
      this.closed = true; this.reason = why === "hidden" ? "paused" : "stopped";
      if (why === "hidden") this.say("off", "Live updates paused while the page is hidden.");
    }
  };
  Outline.prototype.flush = function () {
    var p = this.pending; this.pending = {};
    for (var cid in p) {
      if (!Object.prototype.hasOwnProperty.call(p, cid)) continue;
      var list = this.rows[cid] || [];
      for (var i = 0; i < list.length; i++) this.apply(list[i], p[cid]);
    }
  };
  Outline.prototype.apply = function (r, m) {
    var v = typeof m.value === "number" ? m.value : parseFloat(m.value);
    if (!isFinite(v)) return;   // an unreadable sample never becomes 0
    var li = r.li, unit = m.unit || r.unit, b = r.blo !== null;
    var q = function (role) { return li.querySelector("[data-role=" + role + "]"); };
    var validity = r.validity, why = "";
    if (NA_MARKERS.indexOf(v) > -1) { validity = "invalid"; why = "raw -32768 = 'not available' marker"; }
    else if ((r.plo !== null && v < r.plo) || (r.phi !== null && v > r.phi)) { validity = "invalid"; why = fmt(v) + (unit ? " " + unit : "") + " is not a possible value for this quantity (likely a wrong decode)"; }
    var st, word, glyph = "–", applies = r.applies === "" ? null : r.applies === "1";
    if (b && r.idle && this.rpm !== null) applies = this.rpm >= 1 && this.rpm <= 1100;
    if (!b) { st = "no_band"; word = "No band on record"; }
    else if (validity !== "ok") { st = "not_judged"; word = "Not judged: " + (validity === "invalid" ? "invalid reading" : validity === "suspect" ? "suspect decoding" : "decoding unconfirmed"); }
    else if (applies === false) { st = "not_judged"; word = "Not judged: this band is for " + (r.cond || "another condition") + (this.rpm !== null ? "; the engine was " + (this.rpm < 1 ? "stopped" : "at " + fmt(this.rpm) + " rpm, not at idle") : ""); }
    else if (v < r.blo) { st = "out"; word = "Out of band (below)"; glyph = "✕"; }
    else if (v > r.bhi) { st = "out"; word = "Out of band (above)"; glyph = "✕"; }
    else { st = "in"; word = "In band"; glyph = "✓"; }
    if ((st === "in" || st === "out") && applies === null && r.idle) word += " (whether the car was at idle is not known)";
    li.className = li.className.replace(/\bs-\w+\b/, "s-" + st).replace(/\bv-\w+\b/, "v-" + validity).replace(/\bis-stale\b/, "").replace(/\s+$/, "");
    q("value").textContent = fmt(v) + (unit ? " " + unit : "");
    q("age").textContent = "live";
    q("glyph").textContent = glyph; q("state-text").textContent = word;
    var valid = q("valid");
    if (valid) valid.textContent = validity === "ok" ? "Valid reading." : validity === "invalid" ? "Invalid: " + (why || "see the saved reading") + "." : (validity === "suspect" ? "Suspect." : "Unconfirmed decoding.");
    var mk = q("marker");
    if (mk) {
      if (b && validity === "ok" && applies !== false) { mk.hidden = false; mk.style.left = pct(v, r.min, r.max) + "%"; }
      else mk.hidden = true;
    }
    var bar = q("bar");
    if (bar) bar.setAttribute("aria-label", li.querySelector(".si-name").textContent + ": " + fmt(v) + (unit ? " " + unit : "") + ". " + word + ".");
    r.last = Date.now();
  };
  Outline.prototype.age = function () {
    var now = Date.now();
    for (var cid in this.rows) {
      var list = this.rows[cid];
      for (var i = 0; i < list.length; i++) {
        var r = list[i];
        if (!r.last) continue;
        var stale = now - r.last > STALE_MS;
        if (stale && !/ is-stale\b/.test(r.li.className)) r.li.className += " is-stale";
        if (stale) r.li.querySelector("[data-role=age]").textContent = Math.round((now - r.last) / 1000) + " s ago";
      }
    }
  };

  function init() {
    var r = global.document.querySelector(".si");
    if (r && !r.__si && r.querySelector("#si-pop")) r.__si = new Outline(r);
  }
  global.CuoreSensorsInteractive = { init: init, Outline: Outline };
  if (global.document.readyState === "loading") global.document.addEventListener("DOMContentLoaded", init); else init();
})(window);
