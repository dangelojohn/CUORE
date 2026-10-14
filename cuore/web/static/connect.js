// connect.js -- "Connect to car": adapter -> bus -> VIN -> guided full scan,
// inline in the compact drawer under the vehicle status strip
// (_vbar.html's #connect-drawer). Progressive enhancement only: with no JS
// the button above (#connect-car-btn) is a plain <a href="/v/{vin}/scan">
// to the guided-scan wizard, which already works with zero JS (see
// cuore/web/fullscan_routes.py's own docstring) -- this script only
// intercepts the tap and runs the same sequence inline instead, using:
//
//   1. POST /api/live/connect/start {vin} -- the one additive route
//      (cuore/api/live.py) that runs the honest pre-checks in order
//      (adapter found -> bus verified -> VIN matches) and, if every one
//      passes, starts (or reports an already-open) guided scan.
//   2. The existing guided-scan HTTP surface
//      (/api/live/fullscan/guided/continue, /skip) for every pause after
//      that -- never a new endpoint for the part the wizard already does.
//
// Never runs on page load (only a real tap on #connect-car-btn starts
// anything); never clears a code (there is no clear route behind any of
// this). A refusal at any stage is shown with that stage's own error text,
// which is the live layer's real wording (ops.py/transport.py's own
// LiveError messages), never invented copy.
(function () {
  "use strict";

  var btn = document.getElementById("connect-car-btn");
  var drawer = document.getElementById("connect-drawer");
  if (!btn || !drawer) return;

  var vin = btn.getAttribute("data-vin") || "";
  var running = false;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function openDrawer() { drawer.hidden = false; }

  function setBusy(isBusy) {
    running = isBusy;
    if (isBusy) btn.setAttribute("aria-busy", "true");
    else btn.removeAttribute("aria-busy");
  }

  function renderChecks(checks) {
    var ul = el("ul", "connect-step-list");
    (checks || []).forEach(function (c) {
      var li = el("li", "connect-step " + (c.ok === false ? "is-err" : "is-ok"));
      li.appendChild(el("span", "connect-step-icon"));
      var text = (c.label || c.stage || "") + (c.ok === false && c.error ? ": " + c.error : "");
      li.appendChild(el("span", "connect-step-text", text));
      ul.appendChild(li);
    });
    return ul;
  }

  function renderRefusal(error, checksSoFar) {
    setBusy(false);
    drawer.innerHTML = "";
    drawer.appendChild(renderChecks(checksSoFar));
    drawer.appendChild(el("p", "connect-error", error));
    var retry = el("button", "btn", "Try again");
    retry.type = "button";
    retry.addEventListener("click", startConnect);
    drawer.appendChild(retry);
    openDrawer();
  }

  // Cable labels mirror fullscan_routes.py's own _CABLE_LABELS -- the same
  // wording the no-JS wizard page shows for the same pause.
  var CABLE_LABEL = { blue_a5: "the blue A5", grey_a6: "the grey A6" };

  function renderPause(guided, checks) {
    setBusy(false);
    drawer.innerHTML = "";
    drawer.appendChild(renderChecks(checks));
    var next = guided.next;
    var card = el("div", "connect-pause-card");
    var heading = (!next || next.cable === "none")
      ? "Remove the cable, then Continue"
      : "Fit " + (CABLE_LABEL[next.cable] || next.cable) + " cable (" +
        (next.bus || "") + "), then Continue";
    card.appendChild(el("p", null, heading));
    var actions = el("div", "connect-pause-actions");
    var cont = el("button", "btn primary", "Continue");
    cont.type = "button";
    cont.addEventListener("click", function () {
      doGuidedStep("/api/live/fullscan/guided/continue",
        { scan_id: guided.scan_id, cable_fitted: next ? next.cable : "none" });
    });
    var skip = el("button", "btn", "Skip");
    skip.type = "button";
    skip.addEventListener("click", function () {
      doGuidedStep("/api/live/fullscan/guided/skip", { scan_id: guided.scan_id });
    });
    actions.appendChild(cont);
    actions.appendChild(skip);
    card.appendChild(actions);
    drawer.appendChild(card);
    openDrawer();
  }

  function renderSummary(guided, checks) {
    setBusy(false);
    drawer.innerHTML = "";
    drawer.appendChild(renderChecks(checks));
    drawer.appendChild(el("p", null, "Scan saved."));
    var actions = el("div", "connect-done-actions");
    var openLink = el("a", "btn", "Open scan");
    openLink.href = "/v/" + encodeURIComponent(vin) + "/scans/" + encodeURIComponent(guided.scan_id || "");
    var healthLink = el("a", "btn", "Health report");
    healthLink.href = "/v/" + encodeURIComponent(vin) + "/health";
    actions.appendChild(openLink);
    actions.appendChild(healthLink);
    drawer.appendChild(actions);
    openDrawer();
    // The page's own verdict/strip may have moved now that the scan is on
    // file -- refresh in place rather than leave a stale verdict showing
    // next to a just-finished scan.
    setTimeout(function () { window.location.reload(); }, 900);
  }

  function handleGuided(data, checks) {
    if (!data || !data.status) {
      setBusy(false);
      drawer.innerHTML = "";
      drawer.appendChild(renderChecks(checks));
      openDrawer();
      return;
    }
    if (data.status === "done") { renderSummary(data, checks); return; }
    if (data.status === "paused") { renderPause(data, checks); return; }
    // abandoned, or any other closed state -- nothing pending to show.
    setBusy(false);
    drawer.innerHTML = "";
    drawer.appendChild(renderChecks(checks));
    openDrawer();
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        return { ok: r.ok, body: j };
      });
    });
  }

  function doGuidedStep(url, body) {
    drawer.innerHTML = "";
    drawer.appendChild(el("p", null, "Working..."));
    openDrawer();
    postJSON(url, body)
      .then(function (res) {
        if (!res.ok) {
          renderRefusal((res.body && res.body.detail) || "That step was refused.", []);
          return;
        }
        handleGuided(res.body, []);
      })
      .catch(function () { renderRefusal("Could not reach the server.", []); });
  }

  function startConnect() {
    if (running) return;
    setBusy(true);
    drawer.innerHTML = "";
    drawer.appendChild(el("p", null, "Checking the adapter..."));
    openDrawer();
    postJSON("/api/live/connect/start", { vin: vin })
      .then(function (res) {
        var body = res.body || {};
        if (!res.ok || body.ok === false) {
          var checks = body.checks || [];
          var lastLabel = checks.length ? checks[checks.length - 1].label : "Connect to car";
          renderRefusal(body.error || (lastLabel + " failed."), checks);
          return;
        }
        handleGuided(body.guided, body.checks || []);
      })
      .catch(function () { renderRefusal("Could not reach the server.", []); });
  }

  btn.addEventListener("click", function (ev) {
    ev.preventDefault();
    startConnect();
  });
})();
