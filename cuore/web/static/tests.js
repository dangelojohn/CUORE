/* Tests page client script -- /v/{vin}/tests.
 *
 * Every row's result form already works with no JavaScript at all: the
 * four PASS/FAIL/Inconclusive/Not possible buttons are plain
 * name="result" value="..." submit buttons, posting to the server-rendered
 * fallback route (cuore/web/tests_routes.py's tests_result_form), which
 * redirects back to this same page anchored on the row.
 *
 * When JS *is* available, this turns those same buttons into a two-step
 * flow -- click a result, a compact panel reveals (value/unit, hypothesis,
 * reason), click Save, and the result posts through fetch to
 * POST /api/tests/{vin}/{test_id}/result with no page reload. The filter
 * chips (category / Recommended) are JS-only; with no JS every row is
 * simply shown.
 */
(function () {
  "use strict";

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function resultLabel(result) {
    return (result || "not_done").replace(/_/g, " ").toUpperCase();
  }

  function setChip(row, result) {
    var chip = qs('[data-role="result-chip"]', row);
    if (!chip) return;
    chip.className = "chip ts-result-chip ts-result-" + result;
    chip.textContent = resultLabel(result);
  }

  function initRow(form) {
    var row = form.closest(".ts-row");
    var buttons = qsa(".ts-btn[name='result']", form);
    var extra = qs(".ts-extra", form);
    var save = qs(".ts-save", form);
    var chosen = null;

    var status = document.createElement("div");
    status.className = "ts-status";
    status.hidden = true;
    if (extra) extra.insertAdjacentElement("afterend", status);

    buttons.forEach(function (btn) {
      btn.type = "button"; // JS present: no longer a native submit
      btn.addEventListener("click", function () {
        chosen = btn.value;
        buttons.forEach(function (b) { b.classList.toggle("is-chosen", b === btn); });
        if (extra) extra.hidden = false;
        if (save) save.hidden = false;
      });
    });

    if (save) {
      save.type = "button";
      save.addEventListener("click", function () {
        if (!chosen) return;
        var vin = form.getAttribute("data-vin");
        var testId = form.getAttribute("data-test");
        var fd = new FormData(form);
        var valueRaw = fd.get("value");
        var body = {
          result: chosen,
          value: valueRaw ? parseFloat(valueRaw) : null,
          unit: fd.get("unit") || "",
          reason: fd.get("reason") || "",
          hypothesis_id: fd.get("hypothesis_id") || null,
          supports: fd.get("supports") || "for",
          by: fd.get("by") || "",
        };
        status.hidden = true;
        save.disabled = true;
        fetch("/api/tests/" + encodeURIComponent(vin) + "/" + encodeURIComponent(testId) + "/result", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
          .then(function (r) {
            if (!r.ok) {
              return r.json().catch(function () { return {}; }).then(function (e) {
                throw new Error(e.detail || ("save failed (" + r.status + ")"));
              });
            }
            return r.json();
          })
          .then(function (data) {
            setChip(row, data.result || chosen);
            status.className = "ts-status is-ok";
            status.textContent = "Saved.";
            status.hidden = false;
            save.disabled = false;
          })
          .catch(function (err) {
            status.className = "ts-status is-error";
            status.textContent = "Could not save: " + err.message;
            status.hidden = false;
            save.disabled = false;
          });
      });
    }
  }

  function initFilters() {
    var bar = qs("#ts-filters");
    if (!bar) return;
    var chips = qsa(".ts-filter-chip", bar);
    var rows = qsa(".ts-row");
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        chips.forEach(function (c) { c.classList.toggle("is-on", c === chip); });
        var filter = chip.getAttribute("data-filter");
        rows.forEach(function (row) {
          var show = true;
          if (filter === "recommended") {
            show = row.getAttribute("data-recommended") === "1";
          } else if (filter && filter.indexOf("cat:") === 0) {
            show = row.getAttribute("data-category") === filter.slice(4);
          }
          row.hidden = !show;
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    qsa(".ts-result-form").forEach(initRow);
    initFilters();
  });
})();
