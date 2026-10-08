/* Mechanic feedback: attaches a 44px "..." control to every element with
 * data-fact="<section>|<item>", opening an inline panel (kind, text,
 * optional author, a thread view, and -- once a row exists -- a link into
 * the media-attach flow) that posts JSON to the API feedback.py already
 * serves. The whole-page FAB opens _feedback_panel.html's plain form (the
 * no-JS path), enhanced here only to remember the author field and to tuck
 * it out of the way until tapped.
 *
 * Mirrors cuore.js's own style: one IIFE, defensive against missing
 * elements, never throws past its own handlers.
 */
(function () {
  "use strict";

  var AUTHOR_KEY = "cuore_feedback_author";

  var KIND_ORDER = ["correction", "question", "confirm", "input", "disagree"];
  var KIND_LABELS = {
    correction: "Correct", question: "Ask", confirm: "Confirm",
    input: "Add input", disagree: "Disagree"
  };

  function vinOf() {
    return document.body.getAttribute("data-vin") || "";
  }

  function rememberedAuthor() {
    try { return localStorage.getItem(AUTHOR_KEY) || ""; } catch (e) { return ""; }
  }
  function rememberAuthor(name) {
    try { if (name) { localStorage.setItem(AUTHOR_KEY, name); } } catch (e) { /* ignore */ }
  }

  function fillAuthors() {
    var a = rememberedAuthor();
    if (!a) return;
    var inputs = document.querySelectorAll("[data-feedback-author]");
    for (var i = 0; i < inputs.length; i++) {
      if (!inputs[i].value) inputs[i].value = a;
    }
  }

  function labelOf(el) {
    var t = (el.textContent || "").replace(/\s+/g, " ").trim();
    return t.slice(0, 200);
  }

  function parseFact(raw) {
    var parts = (raw || "").split("|");
    return { section: (parts[0] || "").trim(), item: (parts.slice(1).join("|") || "").trim() };
  }

  function badgeText(counts) {
    if (!counts) return "";
    var bits = [];
    if (counts.open) bits.push(counts.open + " open");
    if (counts.answered) bits.push(counts.answered + " answered");
    if (counts.confirms) bits.push(counts.confirms + " confirmed");
    if (counts.corrections) bits.push(counts.corrections + (counts.corrections === 1 ? " correction" : " corrections"));
    return bits.join(", ");
  }

  // One cached fetch of the whole vehicle's feedback, used only to build a
  // per-fact thread view on demand -- the counts endpoint gives tallies,
  // not the rows themselves, and the API has no per-target filter.
  var allFeedbackPromise = null;
  function allFeedback(vin) {
    if (!allFeedbackPromise) {
      allFeedbackPromise = fetch("/api/vehicles/" + encodeURIComponent(vin) + "/feedback")
        .then(function (r) { return r.ok ? r.json() : { feedback: [] }; })
        .catch(function () { return { feedback: [] }; });
    }
    return allFeedbackPromise;
  }

  function renderThread(container, vin, section, item) {
    container.textContent = "Loading...";
    allFeedback(vin).then(function (data) {
      var rows = (data.feedback || []).filter(function (f) {
        var t = f.target || {};
        return t.page === location.pathname && t.section === section && t.item === item;
      });
      container.textContent = "";
      if (!rows.length) {
        var none = document.createElement("div");
        none.className = "small muted";
        none.textContent = "Nothing on this fact yet.";
        container.appendChild(none);
        return;
      }
      rows.forEach(function (row) {
        var r = document.createElement("div");
        r.className = "feedback-thread-row";
        var head = document.createElement("div");
        head.innerHTML = "";
        head.textContent = (KIND_LABELS[row.kind] || row.kind) + " — " +
          (row.author || "technician") + " — " + (row.at || "") + " — " + row.status;
        r.appendChild(head);
        if (row.text) {
          var txt = document.createElement("div");
          txt.textContent = row.text;
          r.appendChild(txt);
        }
        if (row.answer && row.answer.text) {
          var ans = document.createElement("div");
          ans.className = "feedback-thread-answer";
          ans.textContent = row.answer.text + " — " + (row.answer.by || "");
          r.appendChild(ans);
        }
        container.appendChild(r);
      });
    });
  }

  function buildPanel(vin, section, item, label, badgeEl) {
    var panel = document.createElement("div");
    panel.className = "feedback-inline-panel";

    var kinds = document.createElement("div");
    kinds.className = "feedback-kinds";
    KIND_ORDER.forEach(function (k, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "feedback-kind-btn";
      btn.textContent = KIND_LABELS[k];
      btn.setAttribute("data-kind", k);
      btn.setAttribute("aria-pressed", i === 0 ? "true" : "false");
      btn.addEventListener("click", function () {
        var all = kinds.querySelectorAll("button");
        for (var j = 0; j < all.length; j++) all[j].setAttribute("aria-pressed", "false");
        btn.setAttribute("aria-pressed", "true");
      });
      kinds.appendChild(btn);
    });
    panel.appendChild(kinds);

    var textarea = document.createElement("textarea");
    textarea.className = "feedback-text";
    textarea.maxLength = 4000;
    textarea.placeholder = "What's wrong, or what are you asking?";
    panel.appendChild(textarea);

    var author = document.createElement("input");
    author.type = "text";
    author.className = "feedback-author";
    author.placeholder = "Your name (optional)";
    author.setAttribute("data-feedback-author", "1");
    author.value = rememberedAuthor();
    panel.appendChild(author);

    var status = document.createElement("div");
    status.className = "feedback-status small muted";
    panel.appendChild(status);

    var actions = document.createElement("div");
    actions.className = "feedback-actions";
    var submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.className = "btn primary";
    submitBtn.textContent = "Send";
    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn";
    cancelBtn.textContent = "Close";
    actions.appendChild(submitBtn);
    actions.appendChild(cancelBtn);
    panel.appendChild(actions);

    var threadToggle = document.createElement("button");
    threadToggle.type = "button";
    threadToggle.className = "feedback-thread-toggle";
    threadToggle.textContent = "Show thread";
    var thread = document.createElement("div");
    thread.className = "feedback-thread";
    thread.hidden = true;
    threadToggle.addEventListener("click", function () {
      thread.hidden = !thread.hidden;
      threadToggle.textContent = thread.hidden ? "Show thread" : "Hide thread";
      if (!thread.hidden) renderThread(thread, vin, section, item);
    });
    panel.appendChild(threadToggle);
    panel.appendChild(thread);

    cancelBtn.addEventListener("click", function () { panel.remove(); });

    submitBtn.addEventListener("click", function () {
      var pressed = kinds.querySelector('button[aria-pressed="true"]');
      var kind = pressed ? pressed.getAttribute("data-kind") : "question";
      var authorName = author.value.trim();
      rememberAuthor(authorName);
      submitBtn.disabled = true;
      status.textContent = "Sending...";
      fetch("/api/vehicles/" + encodeURIComponent(vin) + "/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: kind,
          target: { page: location.pathname, section: section, item: item, label: label },
          text: textarea.value.trim(),
          author: authorName || "technician"
        })
      }).then(function (resp) {
        if (!resp.ok) throw new Error("feedback add failed");
        return resp.json();
      }).then(function (row) {
        status.textContent = "Sent. Thanks.";
        submitBtn.disabled = true;
        submitBtn.hidden = true;
        var photo = document.createElement("a");
        photo.className = "small";
        photo.href = "/v/" + encodeURIComponent(vin) + "/media?target_kind=feedback&target_id=" +
          encodeURIComponent(row.id);
        photo.textContent = "Add a photo →";
        panel.insertBefore(photo, threadToggle);
        if (badgeEl) {
          badgeEl.setAttribute("data-has-feedback", "1");
        }
        if (!thread.hidden) renderThread(thread, vin, section, item);
      }).catch(function () {
        status.textContent = "Could not send -- try the page form instead.";
        submitBtn.disabled = false;
      });
    });

    return panel;
  }

  function wireFacts(vin) {
    var elements = document.querySelectorAll("[data-fact]");
    if (!elements.length) return;

    var keys = [];
    for (var i = 0; i < elements.length; i++) {
      var f = parseFact(elements[i].getAttribute("data-fact"));
      keys.push(location.pathname + "|" + f.section + "|" + f.item);
    }
    var uniqueKeys = keys.filter(function (k, idx) { return keys.indexOf(k) === idx; });

    var countsMap = {};
    var countsReady = uniqueKeys.length
      ? fetch("/api/vehicles/" + encodeURIComponent(vin) + "/feedback/counts?targets=" +
              encodeURIComponent(uniqueKeys.join(",")))
          .then(function (r) { return r.ok ? r.json() : { counts: {} }; })
          .then(function (d) { countsMap = d.counts || {}; })
          .catch(function () { countsMap = {}; })
      : Promise.resolve();

    countsReady.then(function () {
      elements.forEach(function (el) {
        var f = parseFact(el.getAttribute("data-fact"));
        var key = location.pathname + "|" + f.section + "|" + f.item;
        var label = el.getAttribute("data-fact-label") || labelOf(el);

        // Where the control (and its panel) actually attaches: a <tr> can
        // only contain <td>/<th>, so land in its last cell rather than
        // appending a non-cell child straight into the row. Everything
        // else just gets the control appended as its own last child.
        var mount = el.tagName === "TR" ? (el.querySelector("td:last-child") || el) : el;

        var wrap = document.createElement("span");
        wrap.className = "feedback-affordance-wrap";

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "feedback-affordance";
        btn.textContent = "…";
        btn.title = "Ask or correct this";
        btn.setAttribute("aria-label", "Ask or correct: " + label);

        var counts = countsMap[key];
        if (counts && (counts.open || counts.answered || counts.confirms || counts.corrections)) {
          btn.setAttribute("data-has-feedback", "1");
          var badge = document.createElement("span");
          badge.className = "feedback-badge";
          badge.textContent = badgeText(counts);
          wrap.appendChild(badge);
        }
        wrap.appendChild(btn);

        var panel = null;
        btn.addEventListener("click", function () {
          if (panel) { panel.remove(); panel = null; return; }
          panel = buildPanel(vin, f.section, f.item, label, btn);
          mount.appendChild(panel);
        });

        mount.appendChild(wrap);
      });
    });
  }

  function wireFab() {
    var fab = document.getElementById("feedback-fab");
    var pagePanel = document.getElementById("feedback-page-panel");
    if (!fab || !pagePanel) return;
    fab.addEventListener("click", function () {
      pagePanel.open = true;
      pagePanel.scrollIntoView({ block: "end", behavior: "smooth" });
      var ta = pagePanel.querySelector("textarea");
      if (ta) ta.focus();
    });
  }

  function wirePageForm() {
    var form = document.querySelector(".feedback-form");
    if (!form) return;
    form.addEventListener("submit", function () {
      var a = form.querySelector("[data-feedback-author]");
      if (a && a.value.trim()) rememberAuthor(a.value.trim());
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var vin = vinOf();
    if (!vin) return;
    fillAuthors();
    wireFacts(vin);
    wireFab();
    wirePageForm();
  });
})();
