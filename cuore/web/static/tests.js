/* Tests page client script -- /v/{vin}/tests.
 *
 * The page works with no JavaScript at all: PASS / FAIL / Skip / Undo are
 * plain form buttons (POST, then a 303 back to this page with the
 * "just recorded" banner, cuore/web/tests_routes.py). This script only
 * enhances:
 *   - a row's "Procedure, pass criteria" fold fetches its body when first
 *     opened (without JS the fold holds a link to the printable sheet);
 *   - the Undo banner is scrolled into view when the page lands on it.
 */
(function () {
  "use strict";

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function initLazyDetails() {
    qsa("details.ts-details[data-src]").forEach(function (d) {
      d.addEventListener("toggle", function () {
        if (!d.open || d.getAttribute("data-loaded")) return;
        d.setAttribute("data-loaded", "1");
        fetch(d.getAttribute("data-src"))
          .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
          .then(function (html) { qs(".ts-detail-body", d).innerHTML = html; })
          .catch(function () { d.removeAttribute("data-loaded"); });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initLazyDetails();
    var undo = qs("#ts-undo");
    if (undo && undo.scrollIntoView) undo.scrollIntoView({ block: "nearest" });
  });
})();
