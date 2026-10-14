// cuore/web/templates/fullscan.html's "feels uninterrupted" touches.
//
// Additive only: every phase already renders correctly with no JS at all
// (plain <form> posts, a full page reload per action -- see
// cuore/web/fullscan_routes.py's own docstring). This file adds two things
// on top, neither of which changes what gets posted or rendered:
//
//   1. A "Working..." busy state on the button that is about to block for
//      a real multi-second adapter read (Start / Continue), so the click
//      doesn't look dead while the request is in flight.
//   2. A 1.5s poll of the guided-scan state while a pause card is showing,
//      so this tab notices if another interface (the MCP tools, a second
//      browser tab) continued, skipped or abandoned the same session, and
//      reloads to match -- it only ever reflects what the server says is
//      open, never acts on its own.
(function () {
  "use strict";

  var root = document.querySelector(".fscan");
  if (!root) return;

  document.querySelectorAll(".fscan form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector("button[type=submit]");
      if (!btn || btn.disabled) return;
      btn.disabled = true;
      btn.textContent = "Working...";
    });
  });

  var phase = root.dataset.phase;
  var scanId = root.dataset.scanId;
  var pausePhases = {"pause_blue": "blue_a5", "pause_grey": "grey_a6", "remove_cable": "none"};
  if (!scanId || !pausePhases.hasOwnProperty(phase)) return;

  var expectedCable = pausePhases[phase];

  function poll() {
    fetch("/api/live/fullscan/guided/state", {credentials: "same-origin"})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (st) {
        if (!st || st.scan_id !== scanId) {
          window.location.reload();
          return;
        }
        var nextCable = st.next ? st.next.cable : (st.status === "done" ? "done" : null);
        if (nextCable !== expectedCable) {
          window.location.reload();
        }
      })
      .catch(function () { /* a missed poll is not worth surfacing */ });
  }

  setInterval(poll, 1500);
})();
