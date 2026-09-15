/* Keyboard navigation and small conveniences.
 *
 * Everything here is additive. Every page works with scripting off -- forms
 * submit, links follow, tables read. This gets used on a tablet with dirty
 * hands next to a car on a lift; a UI that needs JavaScript to function is a
 * UI that fails at exactly the wrong moment.
 */
(function () {
  "use strict";

  var rows = [];
  var cursor = -1;

  function collectRows() {
    rows = Array.prototype.slice.call(
      document.querySelectorAll("tr.row-link[data-href]")
    );
    cursor = -1;
  }

  function highlight(i) {
    if (!rows.length) return;
    if (cursor >= 0 && rows[cursor]) rows[cursor].style.outline = "";
    cursor = Math.max(0, Math.min(rows.length - 1, i));
    var row = rows[cursor];
    row.style.outline = "2px solid var(--accent)";
    row.style.outlineOffset = "-2px";
    row.scrollIntoView({ block: "nearest" });
  }

  function typingInAField(el) {
    if (!el) return false;
    var tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
           el.isContentEditable;
  }

  // A row that carries data-href behaves like a link: click it, or walk the
  // table with j/k and open with Enter.
  document.addEventListener("click", function (ev) {
    var row = ev.target.closest ? ev.target.closest("tr.row-link[data-href]") : null;
    if (!row) return;
    if (ev.target.closest("a")) return;   // let a real link win
    window.location.href = row.getAttribute("data-href");
  });

  var pendingG = false;

  document.addEventListener("keydown", function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (typingInAField(document.activeElement)) {
      if (ev.key === "Escape") document.activeElement.blur();
      return;
    }

    if (pendingG) {
      pendingG = false;
      if (ev.key === "v") { window.location.href = "/"; return; }
      if (ev.key === "m") { window.location.href = "/modules"; return; }
      if (ev.key === "r") { window.location.href = "/recordings"; return; }
      if (ev.key === "l") { window.location.href = "/logs"; return; }
    }

    switch (ev.key) {
      case "g":
        pendingG = true;
        setTimeout(function () { pendingG = false; }, 900);
        break;
      case "/": {
        var search = document.querySelector("[data-search]");
        if (search) { ev.preventDefault(); search.focus(); search.select(); }
        break;
      }
      case "j":
        if (rows.length) { ev.preventDefault(); highlight(cursor + 1); }
        break;
      case "k":
        if (rows.length) { ev.preventDefault(); highlight(cursor - 1); }
        break;
      case "Enter":
        if (cursor >= 0 && rows[cursor]) {
          window.location.href = rows[cursor].getAttribute("data-href");
        }
        break;
      case "?": {
        var help = document.getElementById("keyhelp");
        if (help) help.hidden = !help.hidden;
        break;
      }
    }
  });

  // Filter a table in place. Cheap, and far more useful on a long DTC list
  // than a round trip to the server.
  function wireFilter() {
    var box = document.querySelector("[data-filter-target]");
    if (!box) return;
    var table = document.querySelector(box.getAttribute("data-filter-target"));
    if (!table) return;
    box.addEventListener("input", function () {
      var needle = box.value.trim().toLowerCase();
      var bodyRows = table.querySelectorAll("tbody tr");
      for (var i = 0; i < bodyRows.length; i++) {
        var text = bodyRows[i].textContent.toLowerCase();
        bodyRows[i].hidden = needle !== "" && text.indexOf(needle) === -1;
      }
      collectRows();
    });
    // A link can pre-fill the box via ?filter=... (see the live-module page's
    // link back to the registry). Purely additive: with no query param, or
    // with scripting off, the box just starts empty as it always did.
    var params = new URLSearchParams(window.location.search);
    var pre = params.get("filter");
    if (pre) {
      box.value = pre;
      box.dispatchEvent(new Event("input"));
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    collectRows();
    wireFilter();
  });
})();
