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

  // R8: Undo on the toast -- a selector to a <form> (submitted as-is, the
  // Delete/undelete case) or to a <button> (clicked as-is, the
  // status-change case below, since each status is its own submit button
  // rather than a value you can set and resubmit).
  function showToast(text, kind, undoSel) {
    var el = document.createElement("div");
    el.className = "job-toast";
    el.setAttribute("role", "status");
    var span = document.createElement("span");
    span.textContent = text;
    el.appendChild(span);
    if (undoSel) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn small";
      btn.textContent = "Undo";
      btn.addEventListener("click", function () {
        var target = document.querySelector(undoSel);
        if (target) {
          if (target.tagName === "FORM") {
            try { target.requestSubmit ? target.requestSubmit() : target.submit(); } catch (e) { target.submit(); }
          } else {
            target.click();
          }
        }
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
      var params = new URLSearchParams(location.search);
      var undoHyp = params.get("undo_hyp");
      var undoStatus = params.get("undo_status"); // "<hypId>:<prevStatus>"
      var undoSel = null;
      if (undoHyp) {
        undoSel = '[data-undo-hyp="' + undoHyp + '"] form';
      } else if (undoStatus && undoStatus.indexOf(":") !== -1) {
        var parts = undoStatus.split(":");
        var hypId = parts[0], prevStatus = parts.slice(1).join(":");
        undoSel = '#hyp-' + hypId + ' .hyp-status-row button[value="' + prevStatus + '"]';
      }
      showToast(flash.textContent.trim(), kind, undoSel);
      flash.remove();
    }
    // strip msg/mk/undo_status (and confirm, handled separately below) from
    // the URL bar so a page refresh never replays a stale toast.
    var url = new URL(location.href);
    var changed = false;
    ["msg", "mk", "undo_status"].forEach(function (p) {
      if (url.searchParams.has(p)) { url.searchParams.delete(p); changed = true; }
    });
    if (changed && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);
    }
  })();

  // ---------- ?system=/?codes=/?hypothesis= prefill: scroll to the thing
  // the link was actually about -------------------------------------------
  // job.html already does the real work with no JS at all: the step 7
  // add-hypothesis <details> renders `open` and its matching <option>s
  // render `selected` straight off these same query params server-side,
  // and a matching step 5 code card / step 7 hypothesis card already
  // carries a highlight class. This only adds the one thing a plain GET
  // can't: bringing that element into view instead of leaving the tech to
  // scroll and find it themselves.
  (function scrollToPrefillTarget() {
    var params = new URLSearchParams(location.search);
    var hypId = params.get("hypothesis");
    var target = hypId ? document.getElementById("hyp-" + hypId) : null;
    if (!target && (params.has("system") || params.has("codes"))) {
      target = qs("#add-hypothesis", root);
    }
    if (target && target.scrollIntoView) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
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

  // ---------- R8: "Today 15:58" instead of a raw ISO timestamp -----------
  // Progressive enhancement only -- job.html's own text node is the raw
  // ISO timestamp (still correct, just not pretty) for a no-JS reader.
  (function humanizeTimestamps() {
    function fmt(iso) {
      var d = new Date((iso || "").replace(" ", "T"));
      if (isNaN(d.getTime())) return null;
      var now = new Date();
      var hh = String(d.getHours()).padStart ? String(d.getHours()).padStart(2, "0") : ("0" + d.getHours()).slice(-2);
      var mm = ("0" + d.getMinutes()).slice(-2);
      var time = hh + ":" + mm;
      var sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
      if (sameDay) return "Today " + time;
      var yest = new Date(now); yest.setDate(now.getDate() - 1);
      if (d.getFullYear() === yest.getFullYear() && d.getMonth() === yest.getMonth() && d.getDate() === yest.getDate()) {
        return "Yesterday " + time;
      }
      var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return d.getDate() + " " + months[d.getMonth()] + " " + time;
    }
    qsa(".ts-human", root).forEach(function (el) {
      var iso = el.getAttribute("data-iso-ts");
      var out = fmt(iso);
      if (out) el.textContent = out;
    });
  })();

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

    // R3: the tick button carries only a title tooltip and an aria-hidden
    // glyph -- no accessible name of its own. Stamp one from the row's own
    // text ("Mark <row text> done"/"...not done") at load, independent of
    // whether the result sheet below ever touches this row.
    qsa(".step-check", section).forEach(setCheckAriaLabel);

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

  function rowLabel(li) {
    var textEl = li.querySelector(".step-text");
    if (!textEl) return "";
    // First text node only -- excludes any .result-chip already appended.
    var node = textEl.childNodes[0];
    return node ? node.textContent.trim() : textEl.textContent.trim();
  }

  function setCheckAriaLabel(btn) {
    var li = btn.closest(".checklist-step");
    if (!li) return;
    var text = rowLabel(li);
    var done = btn.getAttribute("aria-pressed") === "true";
    btn.setAttribute("aria-label", "Mark " + text + (done ? " not done" : " done"));
  }

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

    var fromHyp = new URLSearchParams(location.search).get("hypothesis") || "";
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
    // R5: what pass/fail actually *means* for a leak/smoke-style test is
    // the opposite of most other checks -- Fail = a fault was found, which
    // *supports* a leak/fault hypothesis; Pass = clean, which *refutes* it.
    // Detected from the row's own wording (a heuristic, not a schema --
    // there is no structured test-type field anywhere in this app yet).
    function isLeakTest(stepText) { return /smoke|leak/i.test(stepText); }
    function resultMeaning(stepText, r) {
      var leak = isLeakTest(stepText);
      if (r === "pass") return leak ? "Pass — no leak" : "Pass — no fault found";
      if (r === "fail") return leak ? "Fail — leak/smoke found" : "Fail — fault found";
      return RESULT_LABEL[r];
    }
    // For pass/fail, the side of the hypothesis ledger this result lands
    // on by default -- fail supports a fault hypothesis, pass refutes it.
    // inconclusive/not_possible proves nothing either way, default "for"
    // only so the control has a valid starting value.
    function defaultSupports(r) { return r === "pass" ? "against" : "for"; }
    // A number+unit pulled straight out of the row's own text (e.g. "...at
    // 0.5 psi") -- the only place a spec/known-good band lives today;
    // shown as a hint under Measured value (R5), never invented.
    function specFromText(stepText) {
      var m = /(-?\d+(?:\.\d+)?)\s*(psi|kpa|bar|%|v|mv|a|ohm|mm|rpm)\b/i.exec(stepText || "");
      return m ? ("Spec: " + m[1] + " " + m[2]) : "";
    }

    // Item 2 of the 2026-10-08 follow-up: when several hypotheses are open,
    // the result sheet's own hypothesis picker guesses which one this row
    // is actually testing, in order --
    //   1. the hypothesis whose next_test (jobs_bridge._display_next_test,
    //      already on each entry in `hyps`) names this same row -- an
    //      exact match first, then a loose substring one (wording is
    //      transcribed from the same fault-tree step, but not guaranteed
    //      byte-identical);
    //   2. the one linked from "Do it now" (?hypothesis=, read into
    //      `fromHyp` above);
    //   3. none -- the picker then reads "Choose a hypothesis..." (never
    //      "(none)", which read as a status report rather than a prompt).
    function matchByNextTest(stepText) {
      var norm = function (s) { return (s || "").trim().toLowerCase(); };
      var text = norm(stepText);
      if (!text) return null;
      var exact = hyps.find(function (h) { return norm(h.next_test) === text; });
      if (exact) return exact;
      return hyps.find(function (h) {
        var nt = norm(h.next_test);
        return nt && (text.indexOf(nt) !== -1 || nt.indexOf(text) !== -1);
      }) || null;
    }

    function buildSheet(li, stepId, stepText) {
      var dlg = document.createElement("dialog");
      dlg.className = "job-confirm-modal result-sheet";
      var spec = specFromText(stepText);
      var nextTestMatch = matchByNextTest(stepText);
      var preselect = (nextTestMatch && nextTestMatch.id) || fromHyp || "";
      var html = '<p><b>Record a result</b></p><p class="small muted">' + stepText + '</p>' +
        '<div class="field"><label>Result</label><div class="result-radios">' +
        RESULTS.map(function (r) {
          return '<label><input type="radio" name="result" value="' + r + '" data-meaning="1"> '
            + resultMeaning(stepText, r) + '</label>';
        }).join("") + '</div></div>' +
        '<div class="field"><label>Measured value</label>' +
        '<input type="number" step="any" name="value" style="width:48%"> ' +
        '<input type="text" name="unit" placeholder="unit" style="width:40%"></div>' +
        (spec ? '<p class="small muted spec-line">' + spec + '</p>' : '') +
        '<div class="field"><label>Reason<span class="reason-required-mark" hidden> (required)</span></label>' +
        '<input type="text" name="reason" style="width:100%"></div>' +
        '<div class="field"><label>Supports/refutes which hypothesis?</label>' +
        '<select name="hypothesis_id" style="width:100%"><option value="">Choose a hypothesis&hellip;</option>' +
        hyps.map(function (h) {
          return '<option value="' + h.id + '"' + (h.id === preselect ? " selected" : "") + '>'
            + h.text.replace(/</g, "&lt;") + '</option>';
        }).join("") +
        '</select></div>' +
        '<div class="field"><label><input type="radio" name="supports" value="for" checked> for</label> ' +
        '<label><input type="radio" name="supports" value="against"> against</label>' +
        '<p class="small supports-warning" hidden></p></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">' +
        '<button type="button" class="btn" data-cancel>Cancel</button>' +
        '<button type="button" class="btn primary" data-save>Save result</button></div>';
      dlg.innerHTML = html;
      document.body.appendChild(dlg);

      var supportsOverridden = false;
      qsa('input[name="supports"]', dlg).forEach(function (r) {
        r.addEventListener("change", function () { supportsOverridden = true; checkSupportsWarning(); });
      });
      function checkSupportsWarning() {
        var result = (dlg.querySelector('input[name="result"]:checked') || {}).value;
        var supports = (dlg.querySelector('input[name="supports"]:checked') || {}).value;
        var warn = dlg.querySelector(".supports-warning");
        if (!result || !supports || !warn) return;
        var expected = defaultSupports(result);
        if (supportsOverridden && supports !== expected && (result === "pass" || result === "fail")) {
          warn.textContent = resultMeaning(stepText, result) + " usually counts \"" + expected
            + "\" the hypothesis -- you picked \"" + supports + "\".";
          warn.hidden = false;
        } else {
          warn.hidden = true;
        }
      }
      qsa('input[name="result"]', dlg).forEach(function (r) {
        r.addEventListener("change", function () {
          if (!supportsOverridden) {
            var want = defaultSupports(r.value);
            var target = dlg.querySelector('input[name="supports"][value="' + want + '"]');
            if (target) target.checked = true;
          }
          var reasonMark = dlg.querySelector(".reason-required-mark");
          if (reasonMark) reasonMark.hidden = (r.value === "pass");
          checkSupportsWarning();
        });
      });

      dlg.querySelector("[data-cancel]").addEventListener("click", function () { dlg.close(); dlg.remove(); });
      dlg.querySelector("[data-save]").addEventListener("click", function () {
        var result = (dlg.querySelector('input[name="result"]:checked') || {}).value;
        if (!result) { showToast("Pick a result first.", "err"); return; }
        var reasonVal = dlg.querySelector('input[name="reason"]').value.trim();
        if (result !== "pass" && !reasonVal) {
          showToast("A reason is required for " + RESULT_LABEL[result].toLowerCase() + ".", "err");
          return;
        }
        var body = {
          result: result,
          reason: reasonVal,
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
          .then(function (entry) {
            applyResultToRow(li, stepId, result, entry);
            refreshCounters(vin, stepId);
            showToast("Saved.", "ok");
            dlg.close(); dlg.remove();
          })
          .catch(function () { showToast("Could not save -- try again.", "err"); });
      });
      try { dlg.showModal(); } catch (e) { /* unsupported: no-op, row still works via the plain checkbox */ }
    }

    // R3: re-render the row itself from the server's own response --
    // tick box, aria-pressed/label, and a "Fail · 0.5 psi"-style chip --
    // rather than only appending a chip and leaving the box/label stale
    // until a reload.
    function applyResultToRow(li, stepId, result, entry) {
      var existing = li.querySelector(".result-chip");
      if (existing) existing.remove();
      var chip = document.createElement("span");
      chip.className = "result-chip result-chip-" + result;
      var label = RESULT_LABEL[result];
      if (entry && entry.value !== null && entry.value !== undefined && entry.value !== "") {
        label += " · " + entry.value + (entry.unit || "");
      }
      chip.textContent = label;
      var textEl = li.querySelector(".step-text");
      if (textEl) textEl.appendChild(chip);

      var done = !entry || entry.done !== false;
      li.classList.toggle("is-done", done);
      var check = li.querySelector(".step-check");
      if (check) {
        check.setAttribute("aria-pressed", done ? "true" : "false");
        var mark = check.querySelector("span[aria-hidden]");
        if (mark) mark.textContent = done ? "✓" : "";
        check.title = done ? "Mark not done" : "Mark done";
        setCheckAriaLabel(check);
        var doneInput = li.querySelector('input[name="done"]');
        if (doneInput) doneInput.value = done ? "0" : "1";
      }
    }

    // R3: the family's own progress-pill ("0/6") and step 6's own overall
    // "Not started/In progress/Complete N/M" line both go stale the moment
    // a result is saved -- re-fetch the dossier view (the same data these
    // numbers are rendered from) and patch both from it, no reload.
    function refreshCounters(vin, stepId) {
      fetch("/api/vehicles/" + encodeURIComponent(vin) + "/view", { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.open_work) return;
          var totalDone = 0, totalAll = 0;
          data.open_work.forEach(function (card) {
            if (card.progress) { totalDone += card.progress.done || 0; totalAll += card.progress.total || 0; }
          });
          // Family pill: find the open-work card that names this step,
          // then patch that one card's own .job-foot .progress-pill.
          var card = data.open_work.find(function (c) {
            return (c.steps || []).some(function (s) { return s.id === stepId; });
          });
          var rowLi = document.getElementById("fb-" + stepId) || qs('[data-fact="checklist|' + stepId + '"]', root);
          var cardEl = rowLi ? rowLi.closest(".job-card") : null;
          var foot = cardEl ? cardEl.querySelector(".job-foot .progress-pill") : null;
          if (foot && card && card.progress) {
            foot.textContent = card.progress.done + "/" + card.progress.total;
          }
          var statusEl = qs(".step6-status", section);
          if (statusEl && totalAll) {
            var state = totalDone >= totalAll ? "complete" : (totalDone > 0 ? "progress" : "not-started");
            statusEl.className = "step6-status step6-status-" + state;
            statusEl.textContent = (state === "complete" ? "Complete" : state === "progress" ? "In progress" : "Not started")
              + " " + totalDone + "/" + totalAll;
          }
        })
        .catch(function () {});
    }

    qsa(".checklist-step", section).forEach(function (li) {
      var fact = li.getAttribute("data-fact") || "";
      var stepId = fact.indexOf("checklist|") === 0 ? fact.slice("checklist|".length) : "";
      if (!stepId) return;
      var stepText = rowLabel(li) || stepId;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn small result-sheet-trigger";
      btn.textContent = "Record result";
      btn.addEventListener("click", function () { buildSheet(li, stepId, stepText); });
      li.appendChild(btn);
    });
  })();
})();
