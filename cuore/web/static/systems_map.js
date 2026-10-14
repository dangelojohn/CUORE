/* Systems map overlay -- Phase 2 of the dive-in plan
 * (docs/research/SYSTEMS_DIVE_IN_PLAN_2026-10-08.md): "the map says
 * something about this car". Loaded by cuore/web/templates/systems.html
 * (one <script> line); everything else -- the stylesheet, the hot-edge
 * overlay, the legend, the session slider -- is built here so that line
 * stays the only template change.
 *
 * Vanilla JS, no CDN, same posture as liveboard.js/feedback.js: an IIFE,
 * a thin fetch wrapper, plain DOM. Reads the vin off <body data-vin>
 * (same convention feedback.js already uses) and the live state from
 * GET /api/systems/{vin}/state (cuore/api/systems_map.py).
 *
 * The existing map (cuore/web/systems_svg.py) already draws one <a
 * data-system="{key}"><g><rect/><text/></g></a> per system, with a
 * dependency-graph <line> underneath wired to #edge-{a}-{b}; this file
 * never touches those dependency lines -- it only repaints each cell's
 * fill/stroke/badge from the live state, and draws a *second*, separate
 * SVG overlay on top for the hot (corpus co-occurrence) edges, worded
 * "seen together on this car", never "depends on".
 */
(function () {
  "use strict";

  var STATE_LABEL = {
    ACTIVE: "Active", CLEARED_UNVERIFIED: "Cleared, unverified",
    STALE: "Stale", NO_DATA: "No data", VERIFIED_CLEAN: "Verified clean",
  };

  // Colour by state, from cuore.css' own --sev-*/--ok tokens -- never a
  // one-off hex here. NO_DATA dims rather than colouring (nothing to grade).
  var STATE_COLOR = {
    ACTIVE: { bg: "var(--sev-returned-bg)", fg: "var(--sev-returned)" },
    CLEARED_UNVERIFIED: { bg: "var(--sev-chronic-bg)", fg: "var(--sev-chronic)" },
    STALE: { bg: "var(--sev-once-bg)", fg: "var(--sev-once)" },
    VERIFIED_CLEAN: { bg: "var(--ok-bg)", fg: "var(--ok)" },
    NO_DATA: { bg: "var(--surface-2)", fg: "var(--ink-3)" },
  };

  function vinOf() {
    return document.body.getAttribute("data-vin") || "";
  }

  function injectCss() {
    if (document.querySelector('link[href^="/static/systems_map.css"]')) return;
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/systems_map.css";
    document.head.appendChild(link);
  }

  function cellEls(root) {
    return Array.prototype.slice.call(root.querySelectorAll("a[data-system]"));
  }

  // --- paint one cell from the live per-system state --------------------

  function paintCell(a, sys, dim) {
    var rect = a.querySelector("rect");
    var g = a.querySelector("g");
    if (!rect || !g) return;
    var opacity = dim ? "0.25" : "1";
    g.setAttribute("opacity", opacity);
    if (!sys) return;
    var colors = STATE_COLOR[sys.state] || STATE_COLOR.NO_DATA;
    rect.setAttribute("fill", colors.bg);
    rect.setAttribute("stroke", colors.fg);

    var title = a.querySelector("title");
    var label = (a.querySelector("text") || {}).textContent || sys.key || "";
    if (title) {
      var titleText = label + " -- " + (STATE_LABEL[sys.state] || sys.state)
        + ", " + sys.open_code_count + " open code(s)";
      // Tonight's (or newest) live module sweep: each chip names the exact
      // from-car code/ECU/state behind an ACTIVE/history colouring that
      // the MES-log corpus alone would not explain (a network U-code is
      // rarely logged against a real system key). Never silently folded
      // into the plain state label above -- the mechanic should be able
      // to tell, just from the tooltip, which evidence is live tonight.
      (sys.module_codes || []).forEach(function (c) {
        titleText += "\n" + c.chip_text;
      });
      title.textContent = titleText;
    }

    // Open-code badge: drop any badge the server-rendered SVG drew (that
    // one reflects render-time status only) and redraw from the live count.
    var oldBadge = a.querySelector("circle.smap-badge, text.smap-badge");
    while (oldBadge) { oldBadge.remove(); oldBadge = a.querySelector("circle.smap-badge, text.smap-badge"); }
    var plainCircle = a.querySelector("circle:not(.smap-badge)");
    var plainText = plainCircle ? g.querySelectorAll("text")[1] : null;
    if (plainCircle) plainCircle.remove();
    if (plainText) plainText.remove();
    if (sys.open_code_count > 0) {
      var box = rect.getBBox ? null : null; // getBBox unreliable before layout; use attrs instead
      var x = parseFloat(rect.getAttribute("x")), y = parseFloat(rect.getAttribute("y"));
      var w = parseFloat(rect.getAttribute("width"));
      var bx = x + w - 10, by = y + 10;
      var ns = "http://www.w3.org/2000/svg";
      var circle = document.createElementNS(ns, "circle");
      circle.setAttribute("class", "smap-badge");
      circle.setAttribute("cx", bx.toFixed(1)); circle.setAttribute("cy", by.toFixed(1));
      circle.setAttribute("r", "9"); circle.setAttribute("fill", colors.fg);
      var text = document.createElementNS(ns, "text");
      text.setAttribute("class", "smap-badge");
      text.setAttribute("x", bx.toFixed(1)); text.setAttribute("y", (by + 3.2).toFixed(1));
      text.setAttribute("text-anchor", "middle"); text.setAttribute("font-size", "10");
      text.setAttribute("fill", "var(--surface)");
      text.textContent = String(sys.open_code_count);
      g.appendChild(circle); g.appendChild(text);
    }
  }

  function paintModuleChips(root, state) {
    var layer = root.querySelector(".smap-module-chip-layer");
    if (!layer) {
      layer = document.createElement("div");
      layer.className = "smap-module-chip-layer";
      root.appendChild(layer);
    }
    layer.innerHTML = "";
    var rootRect = root.getBoundingClientRect();
    cellEls(root).forEach(function (a) {
      var key = a.getAttribute("data-system");
      var sys = state.systems[key];
      var chips = sys && sys.module_codes;
      if (!chips || !chips.length) return;
      // One chip per cell: the worst (ACTIVE beats HISTORY) tonight's sweep
      // found for this system -- "U1713-2F -- BCM -- failing now", the
      // exact wording the fault came in with, never reworded here.
      var worst = chips.reduce(function (best, c) {
        return (!best || (c.state === "ACTIVE" && best.state !== "ACTIVE")) ? c : best;
      }, null);
      var r = a.getBoundingClientRect();
      var chip = document.createElement("span");
      chip.className = "smap-module-chip smap-module-chip-" + (worst.state === "ACTIVE" ? "active" : "history");
      chip.textContent = worst.chip_text;
      chip.style.left = (r.left - rootRect.left) + "px";
      chip.style.top = (r.top - rootRect.top + r.height - 4) + "px";
      layer.appendChild(chip);
    });
  }

  function paintAll(root, state, dimSet) {
    cellEls(root).forEach(function (a) {
      var key = a.getAttribute("data-system");
      var sys = state.systems[key];
      var dim = dimSet ? !dimSet.has(key) : false;
      paintCell(a, sys, dim);
    });
    paintModuleChips(root, state);
  }

  // --- hot-edge overlay ---------------------------------------------------

  function cellCenter(wrapRect, a) {
    var r = a.getBoundingClientRect();
    return {
      x: r.left + r.width / 2 - wrapRect.left,
      y: r.top + r.height / 2 - wrapRect.top,
    };
  }

  function buildOverlay(wrap) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "smap-overlay");
    svg.setAttribute("aria-hidden", "true");
    wrap.style.position = wrap.style.position || "relative";
    wrap.appendChild(svg);
    return svg;
  }

  function drawEdges(root, wrap, overlay, state) {
    var ns = "http://www.w3.org/2000/svg";
    overlay.innerHTML = "";
    var wrapRect = wrap.getBoundingClientRect();
    overlay.setAttribute("width", wrapRect.width);
    overlay.setAttribute("height", wrapRect.height);
    overlay.setAttribute("viewBox", "0 0 " + wrapRect.width + " " + wrapRect.height);

    var byKey = {};
    cellEls(root).forEach(function (a) { byKey[a.getAttribute("data-system")] = a; });

    (state.edges || []).forEach(function (e) {
      if (!e.sessions_together || e.sessions_together < 1) return; // hot edges only
      var a = byKey[e.a], b = byKey[e.b];
      if (!a || !b) return;
      var p1 = cellCenter(wrapRect, a), p2 = cellCenter(wrapRect, b);
      var line = document.createElementNS(ns, "line");
      line.setAttribute("x1", p1.x.toFixed(1)); line.setAttribute("y1", p1.y.toFixed(1));
      line.setAttribute("x2", p2.x.toFixed(1)); line.setAttribute("y2", p2.y.toFixed(1));
      line.setAttribute("class", "smap-hot-edge");
      var lift = e.lift != null ? e.lift.toFixed ? e.lift.toFixed(2) : e.lift : null;
      var title = document.createElementNS(ns, "title");
      title.textContent = (lift != null ? "lift " + lift + " -- " : "")
        + "seen together on this car (" + e.sessions_together + " session(s))";
      line.appendChild(title);
      overlay.appendChild(line);
      if (lift != null) {
        var mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2;
        var text = document.createElementNS(ns, "text");
        text.setAttribute("x", mx.toFixed(1)); text.setAttribute("y", my.toFixed(1));
        text.setAttribute("class", "smap-hot-edge-label");
        text.textContent = lift + "x";
        overlay.appendChild(text);
      }
    });
  }

  // --- coverage overlay ---------------------------------------------------
  //
  // A cell whose module(s) the newest whole-car scan could not reach (grey
  // A6 cable never fitted, COM3 dropped mid-sweep, ...) gets a grey hatch
  // and the scan_coverage observation's own "why" as a tooltip -- never
  // painted as a state colour (that would claim evidence that does not
  // exist) and never worded "clean".

  function paintCoverage(wrap, coverage) {
    var layer = wrap.querySelector(".smap-coverage-layer");
    if (!layer) {
      layer = document.createElement("div");
      layer.className = "smap-coverage-layer";
      wrap.appendChild(layer);
    }
    layer.innerHTML = "";
    if (!coverage) return;
    cellEls(wrap).forEach(function (a) {
      var key = a.getAttribute("data-system");
      var gap = coverage[key];
      if (!gap) return;
      var rect = a.querySelector("rect");
      if (!rect) return;
      var hatch = document.createElement("div");
      hatch.className = "smap-coverage-hatch";
      hatch.title = (gap.module ? gap.module + ": " : "") + gap.why;
      var wrapRect = wrap.getBoundingClientRect();
      var r = a.getBoundingClientRect();
      hatch.style.left = (r.left - wrapRect.left) + "px";
      hatch.style.top = (r.top - wrapRect.top) + "px";
      hatch.style.width = r.width + "px";
      hatch.style.height = r.height + "px";
      layer.appendChild(hatch);
    });
  }

  // --- legend --------------------------------------------------------------

  function buildLegend(wrap) {
    var legend = document.createElement("div");
    legend.className = "smap-legend";
    var order = ["ACTIVE", "CLEARED_UNVERIFIED", "STALE", "NO_DATA", "VERIFIED_CLEAN"];
    var html = order.map(function (s) {
      var c = STATE_COLOR[s];
      return '<span class="smap-swatch"><i style="background:' + c.bg + ";border-color:" + c.fg
        + '"></i>' + STATE_LABEL[s] + "</span>";
    }).join("");
    html += '<span class="smap-swatch"><i class="smap-hot-sample"></i>seen together on this car (thicker = more sessions, label = lift)</span>';
    legend.innerHTML = html;
    wrap.parentNode.insertBefore(legend, wrap.nextSibling);
    return legend;
  }

  // --- session slider --------------------------------------------------------

  function buildSlider(after, sessions) {
    var box = document.createElement("div");
    box.className = "smap-slider-box";
    if (!sessions || !sessions.length) {
      box.innerHTML = '<p class="small muted">No session history on file yet for the time slider.</p>';
      after.parentNode.insertBefore(box, after.nextSibling);
      return null;
    }
    var label = document.createElement("div");
    label.className = "smap-slider-label";
    label.textContent = "Now (live state)";
    var input = document.createElement("input");
    input.type = "range"; input.className = "smap-slider";
    input.min = "0"; input.max = String(sessions.length); input.value = String(sessions.length);
    input.setAttribute("aria-label", "Session time slider");
    box.appendChild(label);
    box.appendChild(input);
    after.parentNode.insertBefore(box, after.nextSibling);
    return { input: input, label: label };
  }

  // --- live overlay -- Phase 4 ---------------------------------------------
  //
  // GET /api/systems/{vin}/live every 2s while the "Live" toggle is on:
  // per-system worst live colour grade (cuore.services.liveboard_bridge.
  // evaluate's own ok/moderate/excessive/unknown vocabulary, "none" when no
  // live session is running), a chip for any brand-new DTC, and a
  // "Snapshot" button that reuses the same two routes liveboard.js's own
  // snapshot does. Toggling off restores the base state painting -- never
  // leaves a cell showing a stale live colour.

  var LIVE_POLL_MS = 2000;
  var LIVE_GRADES = ["ok", "moderate", "excessive", "unknown", "none"];

  function clearLiveClass(a) {
    LIVE_GRADES.forEach(function (g) { a.classList.remove("smap-live-" + g); });
  }

  function showToast(msg, isError) {
    var el = document.querySelector(".smap-toast");
    if (el) el.remove();
    el = document.createElement("div");
    el.className = "smap-toast" + (isError ? " is-error" : "");
    el.textContent = msg;
    document.body.appendChild(el);
    window.setTimeout(function () { el.remove(); }, 5000);
  }

  // F6 (MECHANIC_REVIEW_3): a failed/slow /api/systems/{vin}/state fetch
  // used to silently drop the Live toggle, Snapshot button and session
  // slider with no indication anything was missing. This note is
  // persistent (no auto-dismiss) because, unlike a toast, the thing it is
  // reporting on -- missing controls -- stays missing until the page is
  // reloaded.
  function showMapNotice(wrap, msg) {
    var el = wrap.parentNode.querySelector(".smap-fetch-notice");
    if (!el) {
      el = document.createElement("div");
      el.className = "smap-fetch-notice";
      wrap.parentNode.insertBefore(el, wrap);
    }
    el.textContent = msg;
    el.hidden = false;
  }

  function clearMapNotice(wrap) {
    var el = wrap.parentNode.querySelector(".smap-fetch-notice");
    if (el) el.hidden = true;
  }

  function setupLiveOverlay(wrap, vin, state) {
    var timer = null;
    var on = false;
    var chipLayer = null;
    var lastLive = null;

    function chipLayerEl() {
      if (!chipLayer) {
        chipLayer = document.createElement("div");
        chipLayer.className = "smap-chip-layer";
        wrap.appendChild(chipLayer);
      }
      return chipLayer;
    }

    function positionOverCell(el, a) {
      var wrapRect = wrap.getBoundingClientRect();
      var r = a.getBoundingClientRect();
      el.style.left = (r.left - wrapRect.left + r.width - 16) + "px";
      el.style.top = (r.top - wrapRect.top - 6) + "px";
    }

    function renderChips(newCodes) {
      var layer = chipLayerEl();
      layer.innerHTML = "";
      var bySystem = {};
      (newCodes || []).forEach(function (nc) {
        (nc.systems && nc.systems.length ? nc.systems : [null]).forEach(function (sysKey) {
          if (!sysKey) return;
          (bySystem[sysKey] = bySystem[sysKey] || []).push(nc);
        });
      });
      cellEls(wrap).forEach(function (a) {
        var key = a.getAttribute("data-system");
        var hits = bySystem[key];
        if (!hits || !hits.length) return;
        hits.forEach(function (nc, i) {
          var chip = document.createElement("a");
          chip.className = "smap-new-code-chip";
          chip.textContent = nc.code;
          chip.title = nc.code + ": new since " + (nc.since || "unknown time");
          chip.href = "/v/" + encodeURIComponent(vin) + "/job?step=7&codes="
            + encodeURIComponent(nc.code) + "&system=" + encodeURIComponent(key);
          layer.appendChild(chip);
          positionOverCell(chip, a);
          chip.style.marginLeft = (i * 12) + "px";
        });
      });
    }

    function applyLive(data) {
      lastLive = data;
      var scannerEl = wrap.parentNode.querySelector(".smap-scanner-label");
      if (scannerEl) scannerEl.textContent = (data && data.scanner) || "";
      cellEls(wrap).forEach(function (a) {
        var key = a.getAttribute("data-system");
        clearLiveClass(a);
        var row = data && data.systems ? data.systems[key] : null;
        var grade = row ? row.grade : "none";
        a.classList.add("smap-live-" + grade);
        var title = a.querySelector("title");
        if (title && row && row.value != null) {
          title.textContent += " -- live " + row.value + (row.unit ? " " + row.unit : "")
            + " (" + grade + ")";
        }
      });
      renderChips(data && data.new_codes);
    }

    function restore() {
      cellEls(wrap).forEach(clearLiveClass);
      if (chipLayer) chipLayer.innerHTML = "";
      paintAll(wrap, state, null);
      var scannerEl = wrap.parentNode.querySelector(".smap-scanner-label");
      if (scannerEl) scannerEl.textContent = "";
    }

    function poll() {
      fetch("/api/systems/" + encodeURIComponent(vin) + "/live")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) { if (on && data) applyLive(data); })
        .catch(function () { /* a missed poll just leaves the last paint up */ });
    }

    function start() {
      on = true;
      poll();
      timer = window.setInterval(poll, LIVE_POLL_MS);
    }

    function stop() {
      on = false;
      if (timer) { window.clearInterval(timer); timer = null; }
      restore();
    }

    function flatValuesFromLive() {
      var liveValues = {}, flatValues = {};
      if (!lastLive || !lastLive.systems) return { liveValues: liveValues, flatValues: flatValues };
      Object.keys(lastLive.systems).forEach(function (key) {
        var row = lastLive.systems[key];
        if (!row.channel || row.value == null) return;
        liveValues[row.channel] = { value: row.value, unit: row.unit || "" };
        flatValues[row.channel] = row.value;
      });
      return { liveValues: liveValues, flatValues: flatValues };
    }

    function takeSnapshot() {
      var vals = flatValuesFromLive();
      if (!Object.keys(vals.flatValues).length) {
        showToast("No live readings to snapshot yet.", true);
        return;
      }
      var body = {
        layout: "systems-map", page: "systems-map", source: "live",
        values: vals.liveValues, note: "",
      };
      fetch("/api/live/snapshots", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function (saved) {
          return fetch("/api/liveboard/evaluate", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ values: vals.flatValues }),
          })
            .then(function (r) { return r.ok ? r.json() : null; })
            .catch(function () { return null; })
            .then(function (resp) {
              var recs = (resp && resp.recommendations) || [];
              var worst = recs.length ? (recs[0].level || "unknown") : "unknown";
              showToast("Snapshot " + (saved.id || "") + " saved -- " + recs.length
                + " reading(s), worst: " + worst);
            });
        })
        .catch(function (err) {
          showToast("Snapshot failed: " + (err && err.message ? err.message : err), true);
        });
    }

    var bar = document.createElement("div");
    bar.className = "smap-live-bar";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "smap-live-toggle";
    toggle.setAttribute("aria-pressed", "false");
    toggle.textContent = "Live";
    toggle.addEventListener("click", function () {
      var next = toggle.getAttribute("aria-pressed") !== "true";
      toggle.setAttribute("aria-pressed", next ? "true" : "false");
      if (next) start(); else stop();
    });

    var scannerEl = document.createElement("span");
    scannerEl.className = "smap-scanner-label";

    var snapBtn = document.createElement("button");
    snapBtn.type = "button";
    snapBtn.className = "smap-snapshot-btn";
    snapBtn.textContent = "Snapshot";
    snapBtn.addEventListener("click", takeSnapshot);

    bar.appendChild(toggle);
    bar.appendChild(scannerEl);
    bar.appendChild(snapBtn);
    wrap.parentNode.insertBefore(bar, wrap);
  }

  // --- wire it all together -----------------------------------------------

  function init() {
    var vin = vinOf();
    var wrap = document.querySelector(".sys-graph-wrap");
    if (!vin || !wrap) return;
    injectCss();

    // F7 (MECHANIC_REVIEW_3): the graph's own overflow-x:auto wrap (never
    // page-level scroll) needs a visible hint when it is actually wider
    // than its box -- at 400px, EVAP/ADAS nodes can sit off-screen with no
    // scrollbar and nothing else on screen saying there is more to the
    // right. Re-checked on resize since this depends on viewport width.
    var hint = document.querySelector(".sys-graph-hint");
    var updateScrollHint = function () {
      if (!hint) return;
      hint.hidden = wrap.scrollWidth <= wrap.clientWidth + 1;
    };
    updateScrollHint();
    window.addEventListener("resize", updateScrollHint);

    // F6: a request still in flight after 3s gets the same honest note a
    // failure does -- nothing on screen should let "still loading" and
    // "failed" look identical to a mechanic waiting on the controls.
    var settled = false;
    var slowTimer = window.setTimeout(function () {
      if (!settled) showMapNotice(wrap, "Live overlay unavailable -- still waiting on the server.");
    }, 3000);

    fetch("/api/systems/" + encodeURIComponent(vin) + "/state")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (state) {
        settled = true;
        window.clearTimeout(slowTimer);
        if (!state) {
          showMapNotice(wrap, "Live overlay unavailable.");
          return;
        }
        clearMapNotice(wrap);
        var root = wrap;
        paintAll(root, state, null);
        paintCoverage(wrap, state.coverage);
        var overlay = buildOverlay(wrap);
        var redraw = function () { drawEdges(root, wrap, overlay, state); paintCoverage(wrap, state.coverage); };
        redraw();
        window.addEventListener("resize", redraw);

        setupLiveOverlay(wrap, vin, state);
        buildLegend(wrap);
        var slider = buildSlider(wrap.parentNode.querySelector(".smap-legend") || wrap, state.sessions);
        if (slider) {
          slider.input.addEventListener("input", function () {
            var v = parseInt(slider.input.value, 10);
            if (v >= state.sessions.length) {
              slider.label.textContent = "Now (live state)";
              paintAll(root, state, null);
            } else {
              var sess = state.sessions[v];
              slider.label.textContent = (sess.when || sess.id) + " -- "
                + (sess.systems_fired.length ? sess.systems_fired.join(", ") : "no systems fired");
              paintAll(root, state, new Set(sess.systems_fired));
            }
            redraw();
          });
        }
      })
      .catch(function () {
        // F6: the map still works unpainted -- never break the page -- but
        // the mechanic must be told the Live/Snapshot/slider controls are
        // missing rather than just finding them absent.
        settled = true;
        window.clearTimeout(slowTimer);
        showMapNotice(wrap, "Live overlay unavailable.");
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
