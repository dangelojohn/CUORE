/* Parts catalogue behaviour (catalog_*.html). No framework, McMaster-style:
   type-ahead under every search box, prefetch a page when its link is hovered,
   whole table rows clickable, and "continue where you left off". Every piece
   degrades to plain links and a plain GET form without this file. */
(function () {
  "use strict";

  // --- type-ahead -----------------------------------------------------------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  document.querySelectorAll("form.cat-search").forEach(function (form) {
    var input = form.querySelector("input[type=search]");
    if (!input) return;
    var box = document.createElement("div");
    box.className = "cat-ta"; box.hidden = true; box.setAttribute("role", "listbox");
    form.appendChild(box);
    var timer = null, last = "";
    input.setAttribute("autocomplete", "off");
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { box.hidden = true; return; }
      timer = setTimeout(function () {
        if (q === last) return; last = q;
        fetch("/catalog/api/typeahead?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (data) {
          if (input.value.trim() !== q) return;
          var html = "";
          (data.specs || []).forEach(function (s) {
            html += '<a class="cat-ta-row spec" href="/catalog/d/' + esc(s.diagram_id) + '#cat-torque"><span class="v">' + esc(s.value) +
              '</span><span>' + esc(s.item) + '<small>' + esc(s.section) + " · " + esc(s.confidence) + "</small></span></a>";
          });
          (data.parts || []).forEach(function (p) {
            html += '<a class="cat-ta-row" href="/catalog/p/' + esc(p.pn) + '"><span class="pn">' + esc(p.pn) +
              '</span><span>' + esc(p.name) + (p.other ? " (other engine)" : "") + "<small>" + esc(p.diagram_title) +
              (p.ref ? " · callout " + esc(p.ref) : "") + "</small></span></a>";
          });
          box.innerHTML = html || '<div class="cat-ta-none">No match. Press Enter for a full search.</div>';
          box.hidden = false;
        }).catch(function () { box.hidden = true; });
      }, 150);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { box.hidden = true; return; }
      if (e.key === "ArrowDown" && !box.hidden) { var f = box.querySelector("a"); if (f) { e.preventDefault(); f.focus(); } }
    });
    box.addEventListener("keydown", function (e) {
      var a = document.activeElement;
      if (e.key === "ArrowDown" && a.nextElementSibling) { e.preventDefault(); a.nextElementSibling.focus(); }
      if (e.key === "ArrowUp") { e.preventDefault(); (a.previousElementSibling || input).focus(); }
      if (e.key === "Escape") { box.hidden = true; input.focus(); }
    });
    document.addEventListener("click", function (e) { if (!form.contains(e.target)) box.hidden = true; });
  });

  // --- rail: open as a column on wide screens, collapsed on phones -----------
  var rail = document.querySelector(".cat-shell > .cat-rail");
  if (rail && window.matchMedia("(min-width: 1400px)").matches) rail.open = true;

  // --- prefetch on hover (catalogue pages only) ------------------------------
  var fetched = {};
  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="/catalog/"]');
    if (!a || fetched[a.href] || a.href.indexOf("/catalog/img/") > -1 || a.target) return;
    fetched[a.href] = 1;
    var l = document.createElement("link"); l.rel = "prefetch"; l.href = a.href; document.head.appendChild(l);
  });

  // --- whole row clickable ---------------------------------------------------
  document.querySelectorAll("tr[data-href]").forEach(function (tr) {
    tr.addEventListener("click", function (e) {
      if (e.target.closest("a, button, summary, input")) return;
      window.location.href = tr.getAttribute("data-href");
    });
  });

  // --- continue where you left off -------------------------------------------
  try {
    var here = document.querySelector("[data-cat-last]");
    if (here) localStorage.setItem("cuore.catalog.last", JSON.stringify({href: location.pathname + location.search, title: here.getAttribute("data-cat-last")}));
    var slot = document.getElementById("cat-continue");
    var last = JSON.parse(localStorage.getItem("cuore.catalog.last") || "null");
    if (slot && last && last.href && last.href.indexOf("/catalog/") === 0) {
      slot.innerHTML = 'Continue: <a href="' + esc(last.href) + '">' + esc(last.title) + "</a>";
      slot.hidden = false;
    }
  } catch (e) { /* storage blocked: no "continue" link, nothing else changes */ }
})();
