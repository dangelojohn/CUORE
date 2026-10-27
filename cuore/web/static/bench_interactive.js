/* Bench interactive pieces. Both blocks work with no script; this only upgrades them.
 *
 * Live proof (.bi-proof[data-live="1"]): subscribes to the existing SSE stream (/api/live/stream, messages
 * {t, channel, value, unit}) and moves the value markers in place. If the server saw no connected session the
 * block stays on its server-rendered "last recorded" values and nothing subscribes. The stream is closed when
 * the page is hidden or left; an error closes it and retries with exponential back-off (2, 4, 8, 16, 32 s),
 * then stops and says so -- never a reconnect storm. EventSource's own automatic reconnect is not used.
 *
 * Fault map (.bf): a tap on a marker shows that element's card inline instead of jumping to the list.
 */
(function (global) {
  "use strict";
  if (global.CuoreBenchInteractive) { global.CuoreBenchInteractive.init(); return; }

  var BACKOFF_S = [2, 4, 8, 16, 32];
  var STALE_MS = 20000;

  function fmt(v) { return Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : v.toFixed(1); }
  function pct(v, lo, hi) { return hi > lo ? Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100)) : 0; }

  // ---- live proof -------------------------------------------------------------------------------------
  function Proof(root) {
    this.root = root;
    this.url = root.getAttribute("data-stream") || "/api/live/stream";
    this.rows = {};
    this.es = null; this.tries = 0; this.timer = null; this.queued = false; this.pending = {};
    this.closed = false;
    var self = this;
    Array.prototype.forEach.call(root.querySelectorAll(".bi-row[data-channel]"), function (li) {
      self.rows[li.getAttribute("data-channel")] = {
        li: li, last: 0,
        min: parseFloat(li.getAttribute("data-min")), max: parseFloat(li.getAttribute("data-max")),
        blo: li.hasAttribute("data-blo") ? parseFloat(li.getAttribute("data-blo")) : null,
        bhi: li.hasAttribute("data-bhi") ? parseFloat(li.getAttribute("data-bhi")) : null,
        inL: li.getAttribute("data-in") || "In band", outL: li.getAttribute("data-out") || "Outside band",
        unit: li.getAttribute("data-unit") || ""
      };
    });
    this.status = root.querySelector("#bi-stream");
    this.ager = global.setInterval(function () { self.age(); }, 5000);
    var onHide = function () { if (global.document.hidden) self.stop("paused while the page is hidden"); else if (self.closed && self.reason === "paused") self.start(); };
    global.document.addEventListener("visibilitychange", onHide);
    global.addEventListener("pagehide", function () { self.stop("page left"); global.clearInterval(self.ager); });
    this.start();
  }
  Proof.prototype.say = function (state, text) {
    if (!this.status) return;
    this.status.setAttribute("data-state", state);
    this.status.textContent = (state === "live" ? "● " : "○ ") + text;
  };
  Proof.prototype.start = function () {
    var self = this;
    if (!global.EventSource) { this.say("off", "Live update needs a newer browser; showing the latest recorded values."); return; }
    this.stop(null, true);
    this.closed = false;
    var es;
    try { es = new global.EventSource(this.url); } catch (e) { this.say("off", "Could not open the live stream."); return; }
    this.es = es;
    es.onopen = function () { self.say("live", "Live: values update as the session reads them."); };
    es.onmessage = function (ev) {
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (!m || m.channel === undefined || !self.rows[m.channel]) return;
      self.tries = 0;
      self.pending[m.channel] = m;
      if (!self.queued) { self.queued = true; global.requestAnimationFrame(function () { self.queued = false; self.flush(); }); }
    };
    es.onerror = function () {
      // Do not let EventSource retry on its own: close, then back off ourselves.
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
  Proof.prototype.stop = function (why, quiet) {
    if (this.timer) { global.clearTimeout(this.timer); this.timer = null; }
    if (this.es) { try { this.es.close(); } catch (e) {} this.es = null; }
    if (!quiet) { this.closed = true; this.reason = why && why.indexOf("hidden") > -1 ? "paused" : "stopped"; if (why && this.reason === "paused") this.say("off", "Live updates paused while the page is hidden."); }
  };
  Proof.prototype.flush = function () {
    var p = this.pending; this.pending = {};
    for (var cid in p) { if (Object.prototype.hasOwnProperty.call(p, cid)) this.apply(this.rows[cid], p[cid]); }
  };
  Proof.prototype.apply = function (r, m) {
    var v = typeof m.value === "number" ? m.value : parseFloat(m.value);
    if (!isFinite(v)) return;   // an unreadable sample never becomes 0
    var li = r.li, unit = m.unit || r.unit;
    var mk = li.querySelector("[data-role=marker]");
    mk.hidden = false; mk.style.left = pct(v, r.min, r.max) + "%";
    li.querySelector("[data-role=value]").textContent = fmt(v) + (unit ? " " + unit : "");
    var st, word, glyph;
    if (r.blo === null) { st = "no_band"; word = "No target band"; glyph = "–"; }
    else if (v < r.blo) { st = "out"; word = r.outL + " (below)"; glyph = "✗"; }
    else if (v > r.bhi) { st = "out"; word = r.outL + " (above)"; glyph = "✗"; }
    else { st = "in"; word = r.inL; glyph = "✓"; }
    li.className = li.className.replace(/\bs-\w+\b/, "s-" + st).replace(/\bis-stale\b/, "").replace(/\s+$/, "");
    var stateEl = li.querySelector("[data-role=state]");
    stateEl.firstElementChild.textContent = glyph;
    li.querySelector("[data-role=state-text]").textContent = word;
    li.querySelector("[data-role=age]").textContent = "live";
    var bar = li.querySelector("[data-role=bar]");
    bar.setAttribute("aria-label", li.querySelector(".bi-name").textContent + ": " + fmt(v) + (unit ? " " + unit : "") + ". " + word + ".");
    r.last = Date.now();
  };
  Proof.prototype.age = function () {
    var now = Date.now();
    for (var cid in this.rows) {
      var r = this.rows[cid];
      if (!r.last) continue;
      var stale = now - r.last > STALE_MS;
      var has = / is-stale\b/.test(r.li.className);
      if (stale && !has) r.li.className += " is-stale";
      if (stale) r.li.querySelector("[data-role=age]").textContent = Math.round((now - r.last) / 1000) + " s ago";
    }
  };

  // ---- fault map ------------------------------------------------------------------------------------------
  function FaultMap(root) {
    this.root = root;
    this.pop = root.querySelector("#bf-pop");
    var self = this;
    var fold = root.querySelector("#bf-fold");
    if (fold) fold.removeAttribute("open");   // the cards are shown on tap; the fold still lists them all
    root.addEventListener("click", function (ev) {
      var a = ev.target.closest ? ev.target.closest("a[data-card]") : null;
      if (!a || !root.contains(a)) return;
      var card = global.document.getElementById(a.getAttribute("data-card"));
      if (!card) return;
      ev.preventDefault();
      self.show(card, a);
    });
    global.document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") self.hide(); });
  }
  FaultMap.prototype.show = function (card, marker) {
    var pop = this.pop;
    Array.prototype.forEach.call(this.root.querySelectorAll(".bf-mark.is-on"), function (m) { m.classList.remove("is-on"); });
    Array.prototype.forEach.call(this.root.querySelectorAll('a[data-card="' + card.id + '"]'), function (m) { m.classList.add("is-on"); });
    pop.textContent = "";
    var copy = card.cloneNode(true);
    copy.removeAttribute("id"); copy.removeAttribute("tabindex");
    pop.appendChild(copy);
    var close = global.document.createElement("button");
    close.type = "button"; close.className = "bf-btn bf-pop-close"; close.textContent = "Close";
    var self = this;
    close.addEventListener("click", function () { self.hide(marker); });
    pop.appendChild(close);
    pop.hidden = false;
    if (pop.scrollIntoView) pop.scrollIntoView({ block: "nearest" });
  };
  FaultMap.prototype.hide = function (marker) {
    if (this.pop.hidden) return;
    this.pop.hidden = true; this.pop.textContent = "";
    Array.prototype.forEach.call(this.root.querySelectorAll(".bf-mark.is-on"), function (m) { m.classList.remove("is-on"); });
    if (marker && marker.focus) marker.focus();
  };

  function init() {
    var p = global.document.querySelector(".bi-proof[data-live='1']");
    if (p && !p.__bi) p.__bi = new Proof(p);
    var f = global.document.querySelector(".bf");
    if (f && !f.__bf) f.__bf = new FaultMap(f);
  }
  global.CuoreBenchInteractive = { init: init, Proof: Proof, FaultMap: FaultMap };
  if (global.document.readyState === "loading") global.document.addEventListener("DOMContentLoaded", init); else init();
})(window);
