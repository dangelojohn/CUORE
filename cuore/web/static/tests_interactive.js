/* Tests interactive pieces. Both blocks work with no script; this only upgrades them.
 *
 * Live band (.tl): when the server saw a connected session (data-live="1") one shared EventSource on the existing
 * SSE stream (/api/live/stream, messages {t, channel, value, unit}) moves the value markers in place. The one-tap
 * "Record PASS" stays locked until every live reading has been inside its band for data-hold seconds (3) without
 * leaving it; "Record FAIL" is offered only while a reading is outside its band. Both are plain form submits to the
 * existing result route: just before submit the hidden value and reason fields are filled with the measured value
 * and its source (channel, value, "live from the open session"). Not connected: nothing subscribes and the normal
 * PASS / FAIL buttons stay as the server rendered them. An unreadable sample never becomes 0. Errors close the
 * stream and retry with back-off 2, 4, 8, 16, 32 s, then stop and say so (no reconnect storm).
 * Meter readings: typing a number judges it against the band and marks the matching button.
 *
 * Test map (.tm): a tap on a marker shows that element's card inline instead of jumping to the list.
 */
(function (global) {
  "use strict";
  if (global.CuoreTestsInteractive) { global.CuoreTestsInteractive.init(); return; }

  var BACKOFF_S = [2, 4, 8, 16, 32];
  var doc = global.document;

  function fmt(v) { return Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : v.toFixed(1); }
  function pct(v, lo, hi) { return hi > lo ? Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100)) : 0; }
  function judge(v, r) {
    if (r.blo === null) return { st: "no_band", word: "No band to judge against", glyph: "–" };
    if (v < r.blo) return { st: "out", word: "Outside the band (below)", glyph: "✗" };
    if (v > r.bhi) return { st: "out", word: "Outside the band (above)", glyph: "✗" };
    return { st: "in", word: "Inside the band", glyph: "✓" };
  }
  function setState(r, j) {
    r.li.className = r.li.className.replace(/\bs-\w+\b/, "s-" + j.st);
    r.li.querySelector("[data-role=glyph]").textContent = j.glyph;
    r.li.querySelector("[data-role=state-text]").textContent = j.word;
  }

  // ---- one live-band block -------------------------------------------------------------------------------
  function Live(root, hub) {
    var self = this;
    this.root = root; this.hub = hub;
    this.hold = (parseFloat(root.getAttribute("data-hold")) || 3) * 1000;
    this.live = root.getAttribute("data-live") === "1";
    this.form = root.querySelector("form.tl-form");
    this.rows = {}; this.order = [];
    Array.prototype.forEach.call(root.querySelectorAll(".tl-row[data-param]"), function (li) {
      var r = {
        li: li, param: li.getAttribute("data-param"), kind: li.getAttribute("data-kind"),
        min: parseFloat(li.getAttribute("data-min")), max: parseFloat(li.getAttribute("data-max")),
        blo: li.hasAttribute("data-blo") ? parseFloat(li.getAttribute("data-blo")) : null,
        bhi: li.hasAttribute("data-bhi") ? parseFloat(li.getAttribute("data-bhi")) : null,
        unit: li.getAttribute("data-unit") || "", value: null, since: null, st: null, origin: ""
      };
      self.rows[r.param] = r; self.order.push(r);
    });
    this.pass = root.querySelector("[data-role=pass]");
    this.fail = root.querySelector("[data-role=fail]");
    this.hint = root.querySelector("[data-role=hint]");
    this.hvalue = root.querySelector("[data-role=hvalue]");
    this.reason = root.querySelector("[data-role=reason]");
    this.primary = this.form ? this.form.getAttribute("data-primary") : "";
    // meter inputs
    this.order.forEach(function (r) {
      var inp = r.li.querySelector("[data-role=meter]");
      if (!inp) return;
      r.input = inp;
      inp.addEventListener("input", function () { self.meter(r); });
    });
    if (this.form) this.form.addEventListener("submit", function () { self.stamp(); });
    if (this.live) { this.lock(); this.tick = global.setInterval(function () { self.refresh(); }, 500); hub.add(this); }
  }
  Live.prototype.lock = function () {
    if (this.pass) { this.pass.disabled = true; }
    if (this.fail) { this.fail.disabled = true; }
    this.say("Record PASS unlocks after the reading stays inside its band for " + Math.round(this.hold / 1000) + " s.");
  };
  Live.prototype.say = function (t) { if (this.hint) this.hint.textContent = t; };
  Live.prototype.apply = function (m) {
    var r = this.rows[m.channel];
    if (!r || r.kind !== "live") return;
    var v = typeof m.value === "number" ? m.value : parseFloat(m.value);
    if (!isFinite(v)) return;   // an unreadable sample never becomes 0
    r.value = v; r.origin = "live from the open session"; r.unit = m.unit || r.unit;
    var j = judge(v, r);
    if (j.st !== "in") r.since = null; else if (r.since === null || r.st !== "in") r.since = Date.now();
    r.st = j.st;
    var mk = r.li.querySelector("[data-role=marker]");
    if (mk && isFinite(r.min)) { mk.hidden = false; mk.style.left = pct(v, r.min, r.max) + "%"; }
    r.li.querySelector("[data-role=value]").textContent = fmt(v) + (r.unit ? " " + r.unit : "");
    r.li.querySelector("[data-role=age]").textContent = "live";
    setState(r, j);
    var bar = r.li.querySelector("[data-role=bar]");
    if (bar) bar.setAttribute("aria-label", r.param + ": " + fmt(v) + " " + r.unit + ". " + j.word + ".");
    this.refresh();
  };
  Live.prototype.refresh = function () {
    if (!this.live || !this.pass) return;
    var all = true, any = false, outside = false, wait = 0, now = Date.now(), seen = false, hold = this.hold;
    this.order.forEach(function (r) {
      if (r.kind !== "live") return;
      seen = true;
      if (r.value === null) { all = false; return; }
      if (r.st === "out") { outside = true; all = false; return; }
      if (r.st !== "in") { all = false; return; }
      any = true;
      var held = now - r.since;
      if (held < hold) { all = false; wait = Math.max(wait, hold - held); }
    });
    this.pass.disabled = !(seen && all);
    this.fail.disabled = !outside;
    if (!seen) return;
    if (all) this.say("Held inside the band for " + Math.round(this.hold / 1000) + " s or more. One tap records PASS with this value.");
    else if (outside) this.say("A reading is outside its band. Record FAIL is available.");
    else if (any) this.say("Inside the band; hold it for " + Math.ceil(wait / 1000) + " more s to unlock Record PASS.");
    else this.say("Waiting for a live value. Nothing is recorded as 0.");
  };
  Live.prototype.meter = function (r) {
    var v = parseFloat(String(r.input.value).replace(",", "."));
    if (!isFinite(v)) { r.value = null; r.li.querySelector("[data-role=state-text]").textContent = "Not recorded"; return; }
    r.value = v; r.origin = "typed by the mechanic from a meter reading";
    var j = judge(v, r); setState(r, j);
    var mk = r.li.querySelector("[data-role=marker]");
    if (mk && isFinite(r.min)) { mk.hidden = false; mk.style.left = pct(v, r.min, r.max) + "%"; }
    if (this.pass) this.pass.classList.toggle("is-suggested", j.st === "in");
    if (this.fail) this.fail.classList.toggle("is-suggested", j.st === "out");
  };
  Live.prototype.stamp = function () {
    // attach the measured value and where it came from to the plain POST
    var p = this.rows[this.primary];
    if (!p || p.value === null) return;
    if (this.hvalue) this.hvalue.value = String(p.value);
    if (this.reason) this.reason.value = "Reading evidence: " + p.param + " " + fmt(p.value) + (p.unit ? " " + p.unit : "") + " (" + (p.origin || "recorded") + ")";
  };

  // ---- shared SSE hub -------------------------------------------------------------------------------------
  function Hub() { this.blocks = []; this.es = null; this.tries = 0; this.timer = null; this.url = null; this.queued = false; this.pending = {}; }
  Hub.prototype.add = function (b) {
    this.blocks.push(b); this.url = this.url || b.root.getAttribute("data-stream") || "/api/live/stream";
    if (this.blocks.length === 1) { var self = this; doc.addEventListener("visibilitychange", function () { if (doc.hidden) self.stop(); else self.start(); }); global.addEventListener("pagehide", function () { self.stop(); }); this.start(); }
  };
  Hub.prototype.say = function (state, text) {
    this.blocks.forEach(function (b) { var s = b.root.querySelector("[data-role=stream]"); if (s) { s.setAttribute("data-state", state); s.textContent = (state === "live" ? "● " : "○ ") + text; } });
  };
  Hub.prototype.stop = function () {
    if (this.timer) { global.clearTimeout(this.timer); this.timer = null; }
    if (this.es) { try { this.es.close(); } catch (e) {} this.es = null; }
  };
  Hub.prototype.start = function () {
    var self = this;
    if (!global.EventSource) { this.say("off", "Live update needs a newer browser; showing the latest recorded values."); return; }
    this.stop();
    var es;
    try { es = new global.EventSource(this.url); } catch (e) { this.say("off", "Could not open the live stream."); return; }
    this.es = es;
    es.onopen = function () { self.say("live", "Live: values update as the session reads them."); };
    es.onmessage = function (ev) {
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (!m || m.channel === undefined) return;
      self.tries = 0; self.pending[m.channel] = m;
      if (!self.queued) { self.queued = true; global.requestAnimationFrame(function () { self.queued = false; var p = self.pending; self.pending = {}; for (var c in p) { if (Object.prototype.hasOwnProperty.call(p, c)) self.blocks.forEach(function (b) { b.apply(p[c]); }); } }); }
    };
    es.onerror = function () {
      try { es.close(); } catch (e) {}
      self.es = null;
      self.blocks.forEach(function (b) { if (b.live && b.pass) { b.pass.disabled = true; b.fail.disabled = true; } });
      if (self.tries >= BACKOFF_S.length) { self.say("off", "Live stream closed. Reload the page to try again; showing the last values."); return; }
      var wait = BACKOFF_S[self.tries++];
      self.say("off", "Live stream interrupted; retrying in " + wait + " s.");
      self.timer = global.setTimeout(function () { self.timer = null; self.start(); }, wait * 1000);
    };
  };

  // ---- test map -------------------------------------------------------------------------------------------
  function Map(root) {
    var self = this;
    this.root = root; this.pop = root.querySelector(".tm-pop");
    var fold = root.querySelector(".tm-fold");
    if (fold) fold.removeAttribute("open");   // cards show on tap; the fold still lists them all
    root.addEventListener("click", function (ev) {
      var a = ev.target.closest ? ev.target.closest("a[data-card]") : null;
      if (!a || !root.contains(a)) return;
      var card = doc.getElementById(a.getAttribute("data-card"));
      if (!card) return;
      ev.preventDefault();
      self.show(card, a);
    });
    doc.addEventListener("keydown", function (ev) { if (ev.key === "Escape") self.hide(); });
  }
  Map.prototype.show = function (card, marker) {
    var pop = this.pop, self = this;
    Array.prototype.forEach.call(this.root.querySelectorAll(".tm-mark.is-on"), function (m) { m.classList.remove("is-on"); });
    Array.prototype.forEach.call(this.root.querySelectorAll('a[data-card="' + card.id + '"]'), function (m) { m.classList.add("is-on"); });
    pop.textContent = "";
    var copy = card.cloneNode(true);
    copy.removeAttribute("id"); copy.removeAttribute("tabindex");
    pop.appendChild(copy);
    var close = doc.createElement("button");
    close.type = "button"; close.className = "ti-btn tm-pop-close"; close.textContent = "Close";
    close.addEventListener("click", function () { self.hide(marker); });
    pop.appendChild(close);
    pop.hidden = false;
    if (pop.scrollIntoView) pop.scrollIntoView({ block: "nearest" });
  };
  Map.prototype.hide = function (marker) {
    if (this.pop.hidden) return;
    this.pop.hidden = true; this.pop.textContent = "";
    Array.prototype.forEach.call(this.root.querySelectorAll(".tm-mark.is-on"), function (m) { m.classList.remove("is-on"); });
    if (marker && marker.focus) marker.focus();
  };

  var hub = null;
  function init() {
    if (!hub) hub = new Hub();
    Array.prototype.forEach.call(doc.querySelectorAll(".tl"), function (el) { if (!el.__tl) el.__tl = new Live(el, hub); });
    Array.prototype.forEach.call(doc.querySelectorAll(".tm"), function (el) { if (!el.__tm) el.__tm = new Map(el); });
  }
  global.CuoreTestsInteractive = { init: init, Live: Live, Hub: Hub, Map: Map };
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", init); else init();
})(window);
