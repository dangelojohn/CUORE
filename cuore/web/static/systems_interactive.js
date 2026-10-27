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
