/* job.js -- progressive enhancement for /v/{vin}/job only
 * (JOB_UX_FIXES_2026-10-08.md). Every form on this page already works
 * with this script absent: it only upgrades the experience, never
 * supplies the only way to do something.
 *
 *  - toast: reads the server-rendered .flash-toast (from the ?msg=&mk=
 *    redirect every mutating route uses, fix #5) and re-shows it as a
 *    small auto-dismissing toast, then strips the query params so a
 *    refresh doesn't replay it.
 *  - confirm modal: promotes the server-rendered .confirm-pending-panel
 *    (fix #1's "tap again" step) into a <dialog>.
 *  - evidence picker: the "+ Evidence for/against" <select> of on-file
 *    items fills the hidden kind/ref_id fields and the visible label
 *    before submit (fix #2).
 *  - similar-hypothesis hint: debounced GET to .../hypotheses/similar
 *    (fix #11) while typing a new hypothesis's text.
 *  - step 6 checklist rows: intercepts the existing plain POST so it
 *    never navigates away from the job page (fix #5's worst bug), using
 *    fetch + a client-side redirect back to the same step/row instead.
 */
(function () {
  "use strict";
  var root = document.querySelector(".job-page");
  if (!root) return;

  function qs(sel, ctx) { return (ctx || document).querySelector(sel); }
  function qsa(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  // ---------- toast (fix #5) ----------------------------------------------

  function showToast(text, kind, undoForm) {
    var el = document.createElement("div");
    el.className = "job-toast";
    el.setAttribute("role", "status");
    var span = document.createElement("span");
    span.textContent = text;
    el.appendChild(span);
    if (undoForm) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn small";
      btn.textContent = "Undo";
      btn.addEventListener("click", function () {
        var f = document.querySelector(undoForm);
        if (f) { try { f.requestSubmit ? f.requestSubmit() : f.submit(); } catch (e) { f.submit(); } }
        el.remove();
      });
      el.appendChild(btn);
    }
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 6000);
  }

  (function initFlash() {
    var flash = qs("[data-flash]", root);
    if (flash) {
      var kind = /flash-err/.test(flash.className) ? "err" : /flash-warn/.test(flash.className) ? "warn" : "ok";
      var undoHyp = new URLSearchParams(location.search).get("undo_hyp");
      var undoSel = undoHyp ? '[data-undo-hyp="' + undoHyp + '"] form' : null;
      showToast(flash.textContent.trim(), kind, undoSel);
      flash.remove();
    }
    // strip msg/mk (and confirm, handled separately below) from the URL bar
    // so a page refresh never replays a stale toast.
    var url = new URL(location.href);
    var changed = false;
    ["msg", "mk"].forEach(function (p) { if (url.searchParams.has(p)) { url.searchParams.delete(p); changed = true; } });
    if (changed && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);
    }
  })();

  // ---------- confirm modal (fix #1) --------------------------------------

  qsa(".confirm-pending-panel", root).forEach(function (panel) {
    if (!("HTMLDialogElement" in window)) return;
    var dlg = document.createElement("dialog");
    dlg.className = "job-confirm-modal";
    while (panel.firstChild) dlg.appendChild(panel.firstChild);
    panel.replaceWith(dlg);
    document.body.appendChild(dlg);
    try { dlg.showModal(); } catch (e) { /* already-open or unsupported: fall back to inline panel */ }
    dlg.addEventListener("click", function (ev) {
      if (ev.target === dlg) dlg.close();
    });
    var cancel = dlg.querySelector('a.btn:not(.primary)');
    if (cancel) cancel.addEventListener("click", function () { dlg.close(); });
  });

  // ---------- evidence picker (fix #2) ------------------------------------

  qsa(".evidence-form", root).forEach(function (form) {
    var pick = form.querySelector('select[name="_pick"]');
    var label = form.querySelector('input[name="label"]');
    var kindField = form.querySelector(".evidence-kind-field");
    var idField = form.querySelector(".evidence-id-field");
    if (!pick) return;
    pick.addEventListener("change", function () {
      if (!pick.value) return;
      var parts = pick.value.split("|");
      kindField.value = parts[0] || "observation";
      idField.value = parts[1] || "";
      if (label) label.value = parts[2] || parts[1] || "";
    });
  });

  // ---------- similar-hypothesis hint (fix #11) ---------------------------

  (function initSimilarHint() {
    var form = qs("#manual-hyp-form", root);
    if (!form) return;
    var text = qs("#hyp_text", form);
    var hint = qs("#similar-hint", root);
    var url = form.getAttribute("data-similar-url");
    if (!text || !hint || !url) return;
    var timer = null;
    text.addEventListener("input", function () {
      clearTimeout(timer);
      var val = text.value.trim();
      if (val.length < 6) { hint.hidden = true; return; }
      timer = setTimeout(function () {
        var sysSel = qs("#hyp_system", form);
        var sysVal = sysSel ? sysSel.value : "";
        fetch(url + "?text=" + encodeURIComponent(val) + "&system=" + encodeURIComponent(sysVal))
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            if (data && data.similar) {
              hint.hidden = false;
              hint.textContent = 'Similar to "' + data.similar.text + '" -- add anyway, or ';
              var a = document.createElement("a");
              a.href = "#hyp-" + data.similar.id;
              a.textContent = "go to it instead";
              hint.appendChild(a);
            } else {
              hint.hidden = true;
            }
          })
          .catch(function () { hint.hidden = true; });
      }, 400);
    });
  })();

  // ---------- step 6: never navigate away (fix #5) ------------------------
  // The checklist row's own form (from _open_work.html, not owned by this
  // page) posts to /v/{vin}/checklist and that route's own redirect target
  // is outside this page's control. Here we only short-circuit it when JS
  // is available: submit via fetch, then move the address bar back to this
  // same step/row ourselves instead of letting the server's redirect carry
  // the browser to a different tab.
  (function enhanceChecklistForms() {
    var step6 = qs("#step-6", root);
    if (!step6) return;
    var section = step6.closest(".dossier-section");
    if (!section) return;
    qsa("form[data-checklist-form]", section).forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var fd = new FormData(form);
        var li = form.closest(".checklist-step");
        var rowId = li ? li.id : "";
        fetch(form.getAttribute("action"), { method: "POST", body: fd, credentials: "same-origin" })
          .then(function () {
            var url = new URL(location.href);
            url.searchParams.set("step", "6");
            url.hash = rowId;
            location.href = url.pathname + "?" + url.searchParams.toString() + url.hash;
          })
          .catch(function () { form.submit(); });
      });
    });
  })();

  // ---------- step 6: the result sheet (fix #3) ---------------------------
  // Ticking a row's own checkbox (above) still just marks it done, exactly
  // as before this page existed -- that is the no-JS path and it keeps
  // working. This adds a second, explicit "Record result" control per row
  // that opens a sheet (Result pass/fail/inconclusive/not possible,
  // measured value+unit, which hypothesis it bears on) and posts straight
  // to the real contract endpoint, POST /api/vehicles/{vin}/checklist/
  // {step_id}/result -- which itself links pass/fail evidence onto the
  // chosen hypothesis, feeding fix #1's confirm gate.
  (function enhanceResultSheet() {
    var step6 = qs("#step-6", root);
    if (!step6) return;
    var section = step6.closest(".dossier-section");
    if (!section) return;
    var vin = document.body.getAttribute("data-vin");
    if (!vin) return;

    var hyps = [];
    fetch("/api/vehicles/" + encodeURIComponent(vin) + "/job", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.job && data.job.hypotheses) {
          hyps = data.job.hypotheses.filter(function (h) { return !h.deleted; });
        }
      })
      .catch(function () {});

    var RESULTS = ["pass", "fail", "inconclusive", "not_possible"];
    var RESULT_LABEL = { pass: "Pass", fail: "Fail", inconclusive: "Inconclusive", not_possible: "Not possible" };

    function buildSheet(li, stepId, stepText) {
      var dlg = document.createElement("dialog");
      dlg.className = "job-confirm-modal result-sheet";
      var html = '<p><b>Record a result</b></p><p class="small muted">' + stepText + '</p>' +
        '<div class="field"><label>Result</label><div class="result-radios">' +
        RESULTS.map(function (r) {
          return '<label><input type="radio" name="result" value="' + r + '"> ' + RESULT_LABEL[r] + '</label>';
        }).join(" ") + '</div></div>' +
        '<div class="field"><label>Measured value</label>' +
        '<input type="number" step="any" name="value" style="width:48%"> ' +
        '<input type="text" name="unit" placeholder="unit" style="width:40%"></div>' +
        '<div class="field"><label>Reason (if fail/inconclusive/not possible)</label>' +
        '<input type="text" name="reason" style="width:100%"></div>' +
        '<div class="field"><label>Supports/refutes which hypothesis?</label>' +
        '<select name="hypothesis_id" style="width:100%"><option value="">(none)</option>' +
        hyps.map(function (h) { return '<option value="' + h.id + '">' + h.text.replace(/</g, "&lt;") + '</option>'; }).join("") +
        '</select></div>' +
        '<div class="field"><label><input type="radio" name="supports" value="for" checked> for</label> ' +
        '<label><input type="radio" name="supports" value="against"> against</label></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">' +
        '<button type="button" class="btn" data-cancel>Cancel</button>' +
        '<button type="button" class="btn primary" data-save>Save result</button></div>';
      dlg.innerHTML = html;
      document.body.appendChild(dlg);
      dlg.querySelector("[data-cancel]").addEventListener("click", function () { dlg.close(); dlg.remove(); });
      dlg.querySelector("[data-save]").addEventListener("click", function () {
        var result = (dlg.querySelector('input[name="result"]:checked') || {}).value;
        if (!result) { showToast("Pick a result first.", "err"); return; }
        var body = {
          result: result,
          reason: dlg.querySelector('input[name="reason"]').value,
          value: dlg.querySelector('input[name="value"]').value || null,
          unit: dlg.querySelector('input[name="unit"]').value,
          hypothesis_id: dlg.querySelector('select[name="hypothesis_id"]').value || null,
          supports: (dlg.querySelector('input[name="supports"]:checked') || {}).value || "for",
        };
        if (body.value !== null) body.value = parseFloat(body.value);
        fetch("/api/vehicles/" + encodeURIComponent(vin) + "/checklist/" + encodeURIComponent(stepId) + "/result", {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
          .then(function (r) { if (!r.ok) throw new Error("save failed"); return r.json(); })
          .then(function () {
            var existing = li.querySelector(".result-chip");
            if (existing) existing.remove();
            var chip = document.createElement("span");
            chip.className = "result-chip result-chip-" + result;
            chip.textContent = RESULT_LABEL[result];
            var textEl = li.querySelector(".step-text");
            if (textEl) textEl.appendChild(chip);
            showToast("Saved.", "ok");
            dlg.close(); dlg.remove();
          })
          .catch(function () { showToast("Could not save -- try again.", "err"); });
      });
      try { dlg.showModal(); } catch (e) { /* unsupported: no-op, row still works via the plain checkbox */ }
    }

    qsa(".checklist-step", section).forEach(function (li) {
      var fact = li.getAttribute("data-fact") || "";
      var stepId = fact.indexOf("checklist|") === 0 ? fact.slice("checklist|".length) : "";
      if (!stepId) return;
      var textEl = li.querySelector(".step-text");
      var stepText = textEl ? textEl.textContent.trim() : stepId;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn small result-sheet-trigger";
      btn.textContent = "Record result";
      btn.addEventListener("click", function () { buildSheet(li, stepId, stepText); });
      li.appendChild(btn);
    });
  })();
})();
