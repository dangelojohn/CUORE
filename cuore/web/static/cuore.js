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

  // ---------------------------------------------------------------------
  // Theme toggle (R10). data-theme on <html>, persisted per browser. Reads
  // on every load before paint would be nice but this script is loaded at
  // the end of body -- a brief flash of the ambient theme is an acceptable
  // trade for "no JS required" everywhere else staying true; this is the
  // one feature that is allowed to need scripting, since prefers-color-
  // scheme already covers the no-JS case.
  function safeStorage() {
    try {
      var k = "__cuore_probe__";
      window.localStorage.setItem(k, "1");
      window.localStorage.removeItem(k);
      return window.localStorage;
    } catch (e) {
      return null;
    }
  }
  var storage = safeStorage();

  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }

  function wireThemeToggle() {
    var btn = document.getElementById("theme-toggle");
    if (storage) {
      var saved = storage.getItem("cuore-theme");
      if (saved) applyTheme(saved);
    }
    if (!btn) return;
    btn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var isDark = current ? current === "dark"
        : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      var next = isDark ? "light" : "dark";
      applyTheme(next);
      if (storage) {
        try { storage.setItem("cuore-theme", next); } catch (e) { /* ignore */ }
      }
    });
  }

  // ---------------------------------------------------------------------
  // Dossier: collapsed-card persistence, expand/collapse all, jump row
  // "expand all"/"collapse all" buttons, and the e/c shortcuts (R3, R11).
  // Every <details class="card-details"> works with scripting off -- it
  // just forgets its open/closed state between visits.
  function dossierStorageKey(vin, name) {
    return "cuore-dossier-" + vin + "-" + name;
  }

  function wireDossierSections() {
    var root = document.querySelector(".dossier[data-vin]");
    if (!root) return;
    var vin = root.getAttribute("data-vin");
    var cards = Array.prototype.slice.call(root.querySelectorAll("details.card-details[data-persist]"));

    cards.forEach(function (card) {
      var name = card.getAttribute("data-persist");
      if (storage) {
        var saved = storage.getItem(dossierStorageKey(vin, name));
        if (saved === "open") card.open = true;
        else if (saved === "closed") card.open = false;
      }
      card.addEventListener("toggle", function () {
        if (!storage) return;
        try {
          storage.setItem(dossierStorageKey(vin, name), card.open ? "open" : "closed");
        } catch (e) { /* ignore */ }
      });
    });

    function setAll(open) {
      cards.forEach(function (card) { card.open = open; });
    }

    root.querySelectorAll("[data-expand-all]").forEach(function (b) {
      b.addEventListener("click", function () { setAll(true); });
    });
    root.querySelectorAll("[data-collapse-all]").forEach(function (b) {
      b.addEventListener("click", function () { setAll(false); });
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (typingInAField(document.activeElement)) return;
      if (ev.key === "e") setAll(true);
      else if (ev.key === "c") setAll(false);
    });
  }

  // ---------------------------------------------------------------------
  // Checklist step ticks (R4): the <form> posts and reloads with
  // scripting off. With it, intercept the submit, PATCH the state over
  // JSON, and flip the row in place -- falling back to the normal
  // navigation on any failure so a flaky connection never eats a tap.
  function wireChecklistForms() {
    document.querySelectorAll("form[data-checklist-form]").forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        if (!window.fetch) return; // let it submit normally
        var root = form.closest(".dossier[data-vin]");
        var vin = root ? root.getAttribute("data-vin") : null;
        if (!vin) return;
        ev.preventDefault();
        var stepId = form.querySelector('[name="step_id"]').value;
        var doneField = form.querySelector('[name="done"]');
        var done = doneField.value === "1";
        fetch("/api/vehicles/" + encodeURIComponent(vin) + "/checklist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ step_id: stepId, done: done }),
        }).then(function (resp) {
          if (!resp.ok) throw new Error("checklist update failed");
          var li = form.closest(".checklist-step");
          if (li) li.classList.toggle("is-done", done);
          var btn = form.querySelector(".step-check");
          if (btn) {
            btn.setAttribute("aria-pressed", done ? "true" : "false");
            var mark = btn.querySelector("span");
            if (mark) mark.textContent = done ? "✓" : "";
          }
          doneField.value = done ? "0" : "1";
        }).catch(function () {
          form.submit();
        });
      });
    });
  }

  // ---------------------------------------------------------------------
  // Floating quick-add note button (R10): opens the Notes card if it is
  // collapsed and focuses the add-note textarea. Pure convenience; the
  // notes form itself already works by scrolling to it directly.
  function wireQuickAddNote() {
    var fab = document.getElementById("quick-add-note");
    if (!fab) return;
    fab.addEventListener("click", function () {
      var card = document.getElementById("sec-notes");
      if (card && card.tagName === "DETAILS") card.open = true;
      var textarea = document.querySelector("#sec-notes textarea[name='text']");
      if (card) card.scrollIntoView({ block: "start", behavior: "smooth" });
      if (textarea) textarea.focus();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    collectRows();
    wireFilter();
    wireThemeToggle();
    wireDossierSections();
    wireChecklistForms();
    wireQuickAddNote();
  });
})();
