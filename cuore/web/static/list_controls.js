/* Sort bar for the Live board reading list (liveboard_groups.html).
 * Sorting is client-side on the rendered rows; the server order stays the default (no JS = no bar).
 * Choice is remembered per VIN in localStorage ("cuore.lb.sort.<vin>"). Plain JS, no libraries. */
(function (global) {
  "use strict";
  var RANK = { excessive: 0, moderate: 1, ok: 2, unknown: 3 };

  function rowOf(item) { return item.classList.contains("lb-chan") ? item : item.querySelector(".lb-chan"); }
  function nameOf(item) {
    var n = item.querySelector(".lb-chan-name");
    return (n ? n.textContent : "").trim().toLowerCase();
  }
  function valueOf(item) {
    var v = item.querySelector(".lb-chan-value");
    var x = v ? parseFloat(v.textContent) : NaN;
    return isNaN(x) ? null : x;
  }
  function levelOf(item) {
    var r = rowOf(item), m = r && /level-(\w+)/.exec(r.className);
    return m && RANK[m[1]] !== undefined ? RANK[m[1]] : 3;
  }
  function cmp(mode) {
    return function (a, b) {
      var d = 0;
      if (mode === "name") d = nameOf(a).localeCompare(nameOf(b));
      else if (mode === "value") {
        var x = valueOf(a), y = valueOf(b);   // highest first; rows with no value last
        d = x === null ? (y === null ? 0 : 1) : (y === null ? -1 : y - x);
      } else if (mode === "alarm") d = levelOf(a) - levelOf(b);
      return d || (a._lbI - b._lbI);
    };
  }

  function sortAll(root, mode) {
    var boxes = root.querySelectorAll("details.lb-group");
    Array.prototype.forEach.call(boxes, function (box) {
      var items = Array.prototype.filter.call(box.children, function (c) {
        return c.classList.contains("lb-item") || c.classList.contains("lb-chan");
      });
      if (items.length < 2) return;
      items.forEach(function (it, i) { if (it._lbI === undefined) it._lbI = i; });
      var anchor = items[items.length - 1].nextSibling;
      var sorted = items.slice().sort(cmp(mode === "group" ? "" : mode));
      sorted.forEach(function (it) { box.insertBefore(it, anchor); });
    });
  }

  function init(doc) {
    doc = doc || document;
    var root = doc.getElementById("lb-groups"), bar = doc.getElementById("lb-sortbar");
    if (!root || !bar) return;
    bar.hidden = false;
    var app = doc.getElementById("lb-app");
    var key = "cuore.lb.sort." + ((app && app.getAttribute("data-vin")) || "");
    var buttons = bar.querySelectorAll("[data-sort]");
    function apply(mode, save) {
      sortAll(root, mode);
      Array.prototype.forEach.call(buttons, function (b) {
        var on = b.getAttribute("data-sort") === mode;
        b.setAttribute("aria-pressed", on ? "true" : "false");
        b.classList.toggle("is-on", on);
      });
      if (save) { try { global.localStorage.setItem(key, mode); } catch (e) {} }
    }
    Array.prototype.forEach.call(buttons, function (b) {
      b.addEventListener("click", function () { apply(b.getAttribute("data-sort"), true); });
    });
    var mode = "group";
    try { mode = global.localStorage.getItem(key) || "group"; } catch (e) {}
    if (!/^(name|value|alarm|group)$/.test(mode)) mode = "group";
    apply(mode, false);
    // Values arrive after render: re-sort on the polling tick when sorting by value or alarm.
    if (global.setInterval) global.setInterval(function () {
      var cur = bar.querySelector('[aria-pressed="true"]');
      var m = cur && cur.getAttribute("data-sort");
      if (m === "value" || m === "alarm") sortAll(root, m);
    }, 3000);
  }

  global.CuoreListControls = { init: init, sortAll: sortAll };
  if (global.document) global.document.addEventListener("DOMContentLoaded", function () { init(); });
})(window);
