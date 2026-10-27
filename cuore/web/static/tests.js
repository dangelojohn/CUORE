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
 * POST /api/tests/{vin}/{test_id}/result with no page reload. "Undo" posts a
 * null result at once. Row Details are fetched lazily when opened (no-JS
 * keeps a link to the printable sheet). Sort chips are plain links.
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
    var undo = qs(".ts-btn-undo", row); // only offered while a result is on file
    if (undo) undo.hidden = (result === "not_done");
  }

  function initRow(form) {
    var row = form.closest(".ts-row");
    var buttons = qsa(".ts-btn[name='result']", form);
    var extra = null;
    var save = null;
    var chosen = null;
    var tpl = qs("#ts-extra-tpl");

    function ensureExtra() {
      if (extra || !tpl) return;
      extra = tpl.content.firstElementChild.cloneNode(true);
      form.appendChild(extra);
      save = qs(".ts-save", extra);
      var unit = qs("input[name='unit']", form);
      var hasSpec = qs("input[name='has_spec']", form);
      if (hasSpec && hasSpec.value !== "1") {
        var v = qs("input[name='value']", extra);
        if (v && v.closest("label")) v.closest("label").hidden = true;
      }
      var sys = qs("input[name='sys']", form);
      var hyp = qs("select[name='hypothesis_id']", extra);
      if (hyp && sys && sys.value) {
        qsa("option", hyp).forEach(function (o) {
          if (o.getAttribute("data-system") === sys.value) hyp.value = o.value;
        });
      }
      save.addEventListener("click", doSave);
    }

    var status = document.createElement("div");
    status.className = "ts-status";
    status.hidden = true;
    form.appendChild(status);

    function post(body, onDone) {
      var vin = form.getAttribute("data-vin");
      var testId = form.getAttribute("data-test");
      status.hidden = true;
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
        .then(function (data) { onDone(data); })
        .catch(function (err) {
          status.className = "ts-status is-error";
          status.textContent = "Could not save: " + err.message;
          status.hidden = false;
          if (save) save.disabled = false;
        });
    }

    function doSave() {
      if (!chosen) return;
      var fd = new FormData(form);
      var valueRaw = fd.get("value");
      save.disabled = true;
      post({
        result: chosen,
        value: valueRaw ? parseFloat(valueRaw) : null,
        unit: valueRaw ? (fd.get("unit") || "") : "",
        reason: fd.get("reason") || "",
        hypothesis_id: fd.get("hypothesis_id") || null,
        supports: fd.get("supports") || "for",
        by: "",
      }, function (data) {
        setChip(row, data.result || chosen);
        status.className = "ts-status is-ok";
        status.textContent = "Saved. Use Undo to clear it.";
        status.hidden = false;
        save.disabled = false;
      });
    }

    buttons.forEach(function (btn) {
      btn.type = "button"; // JS present: no longer a native submit
      btn.addEventListener("click", function () {
        if (btn.value === "") { // Undo: one tap, no panel
          post({ result: null }, function () {
            setChip(row, "not_done");
            status.className = "ts-status is-ok";
            status.textContent = "Result cleared.";
            status.hidden = false;
          });
          return;
        }
        chosen = btn.value;
        buttons.forEach(function (b) { b.classList.toggle("is-chosen", b === btn); });
        ensureExtra();
        if (extra) extra.hidden = false;
      });
    });
  }

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
    qsa(".ts-result-form").forEach(initRow);
    initLazyDetails();
  });
})();
