/* Systems map, tappable. Works with no script (nodes are links to ?system=KEY; the server draws the selection and
 * lists every card in a details.fold); this only upgrades it: a tap on a system node (or a "shares a cause" link)
 * highlights, on the same drawing, what the system depends on and which systems share a cause with it, and shows
 * its card inline instead of reloading. Escape or Close clears it. Same pattern as bench_interactive.js.
 *
 * Each node carries data-id ("s:evap"), data-deps (tokens it depends on: "s:electrical_supply p:f82 b:CAN-C") and
 * data-shared (systems sharing a cause). Parts carry data-id ("p:f82"); edges data-from / data-to.
 */
(function (global) {
  "use strict";
  if (global.CuoreSystemsInteractive) { global.CuoreSystemsInteractive.init(); return; }

  var WORD = { selected: "Selected", dep: "Depends on", shared: "Shares a cause" };

  function tokens(s) { return (s || "").split(/\s+/).filter(Boolean); }
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }

  function SystemsMap(root) {
    this.root = root;
    this.pop = root.querySelector("#sx-pop");
    this.current = null;
    var self = this;
    var fold = root.querySelector("#sx-fold");
    if (fold) fold.removeAttribute("open");      // the card shows on tap; the fold still lists every one
    root.addEventListener("click", function (ev) {
      var a = ev.target.closest ? ev.target.closest("a[data-system]") : null;
      if (!a || !root.contains(a)) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button > 0) return;
      ev.preventDefault();
      self.select(a.getAttribute("data-system"), a);
    });
    global.document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") self.clear(); });
    var sel = root.querySelector(".sx-node.rel-selected");
    if (sel) { this.current = sel.getAttribute("data-system"); }
    this.wireClose();
    this.initLayers();
  }

  SystemsMap.prototype.paint = function (key) {
    var root = this.root, sid = key ? "s:" + key : "";
    var node = key ? root.querySelector('.sx-node[data-system="' + key + '"]') : null;
    var dep = node ? tokens(node.getAttribute("data-deps")) : [];
    var shared = node ? tokens(node.getAttribute("data-shared")) : [];
    var depSys = {};
    dep.forEach(function (t) { if (t.indexOf("s:") === 0) depSys[t] = true; });
    var chainFrom = {};
    if (sid) { chainFrom[sid] = true; for (var t in depSys) chainFrom[t] = true; }
    function rels(id) {
      var r = [];
      if (id === sid) r.push("selected");
      if (dep.indexOf(id) > -1) r.push("dep");
      if (shared.indexOf(id) > -1) r.push("shared");
      return r;
    }
    each(root.querySelectorAll("[data-id]"), function (el) {
      var r = rels(el.getAttribute("data-id"));
      if (el.classList.contains("sx-part")) r = r.filter(function (x) { return x !== "selected"; });
      ["selected", "dep", "shared"].forEach(function (c) { el.classList.toggle("rel-" + c, r.indexOf(c) > -1); });
      var tag = el.querySelector(".sx-tag");
      if (tag) tag.textContent = r.map(function (x) { return WORD[x]; }).join(" · ");
      if (el.classList.contains("sx-node")) {
        if (r.indexOf("selected") > -1) el.setAttribute("aria-current", "true"); else el.removeAttribute("aria-current");
      }
    });
    each(root.querySelectorAll(".sx-edge"), function (e) {
      e.classList.toggle("is-on", !!sid && !!chainFrom[e.getAttribute("data-from")] && !!depSys[e.getAttribute("data-to")]);
    });
  };

  /* Layers + views. Without this script every layer and both views are visible (nothing is hidden by default).
   * Default here: confirmed relations, severity, issues and live on; guessed links off. The choice is kept for the
   * session (sessionStorage, in try/catch) so leaving a guide or reloading brings the same map back. */
  var KEY = "cuore.sx.layers";
  SystemsMap.prototype.initLayers = function () {
    var root = this.root, self = this;
    var bar = root.querySelector("#sx-layers"), vb = root.querySelector("#sx-viewbar");
    if (!bar) return;
    var saved = null;
    try { saved = JSON.parse(global.sessionStorage.getItem(KEY) || "null"); } catch (e) { saved = null; }
    var off = {};
    each(bar.querySelectorAll(".sx-lbtn"), function (b) {
      var id = b.getAttribute("data-layer");
      var on = saved && saved.off ? !saved.off[id] : b.getAttribute("data-default") === "1";
      off[id] = !on;
    });
    var view = root.getAttribute("data-guided") ? "overlap" : ((saved && saved.view) || "graph");
    function apply() {
      var list = [];
      each(bar.querySelectorAll(".sx-lbtn"), function (b) {
        var id = b.getAttribute("data-layer");
        b.setAttribute("aria-pressed", off[id] ? "false" : "true");
        if (off[id]) list.push(id);
      });
      root.setAttribute("data-off", list.join(" "));
      root.setAttribute("data-view", view);
      var hidden = {};
      each(root.querySelectorAll(".sx-node"), function (n) { if (off[n.getAttribute("data-sev")]) hidden["s:" + n.getAttribute("data-system")] = true; });
      each(root.querySelectorAll(".sx-edge"), function (e) {
        if (hidden[e.getAttribute("data-from")] || hidden[e.getAttribute("data-to")]) e.setAttribute("data-hide", ""); else e.removeAttribute("data-hide");
      });
      if (vb) each(vb.querySelectorAll(".sx-vbtn"), function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-view") === view ? "true" : "false"); });
      try { global.sessionStorage.setItem(KEY, JSON.stringify({ off: off, view: root.getAttribute("data-guided") ? (saved && saved.view) || "graph" : view })); } catch (e) { /* not kept */ }
    }
    root.classList.add("sx-js");
    bar.hidden = false; if (vb) vb.hidden = false;
    bar.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".sx-lbtn") : null;
      if (!b) return;
      var id = b.getAttribute("data-layer"); off[id] = !off[id]; saved = { off: off, view: view }; apply();
    });
    if (vb) vb.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".sx-vbtn") : null;
      if (!b) return;
      view = b.getAttribute("data-view"); apply();
    });
    apply();
    var g = root.querySelector("#sx-guide");
    if (g && g.scrollIntoView) g.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  SystemsMap.prototype.wireClose = function () {
    var self = this, c = this.pop.querySelector(".sx-pop-close");
    if (c) c.addEventListener("click", function (ev) { ev.preventDefault(); self.clear(); });
  };

  SystemsMap.prototype.select = function (key, from) {
    var li = global.document.getElementById("sx-card-" + key);
    if (!li) { global.location.href = from.href; return; }      // no card to show: fall back to the server's page
    if (this.current === key) { this.clear(from); return; }
    this.current = key;
    this.paint(key);
    var pop = this.pop;
    pop.textContent = "";
    pop.appendChild(li.firstElementChild.cloneNode(true));
    var p = global.document.createElement("p");
    var close = global.document.createElement("a");
    close.href = "#sx"; close.className = "sx-btn sx-pop-close"; close.textContent = "Close";
    p.appendChild(close); pop.appendChild(p);
    this.wireClose();
    pop.hidden = false;
    try {
      var u = new global.URL(global.location.href); u.searchParams.set("system", key); u.hash = "sx";
      global.history.replaceState(null, "", u.toString());
    } catch (e) { /* the selection still works without the address update */ }
    if (pop.scrollIntoView) pop.scrollIntoView({ block: "nearest" });
  };

  SystemsMap.prototype.clear = function (focusEl) {
    if (!this.current && this.pop.hidden) return;
    this.current = null;
    this.paint(null);
    this.pop.hidden = true; this.pop.textContent = "";
    try {
      var u = new global.URL(global.location.href); u.searchParams.delete("system");
      global.history.replaceState(null, "", u.toString());
    } catch (e) { /* ignore */ }
    if (focusEl && focusEl.focus) focusEl.focus();
  };

  function init() {
    var r = global.document.querySelector(".sx");
    if (r && !r.__sx) r.__sx = new SystemsMap(r);
  }
  global.CuoreSystemsInteractive = { init: init, SystemsMap: SystemsMap };
  if (global.document.readyState === "loading") global.document.addEventListener("DOMContentLoaded", init); else init();
})(window);
