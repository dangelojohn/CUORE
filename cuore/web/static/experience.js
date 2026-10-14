/* Driver/mechanic-added "Others' experience" links: wires the
 * "+ Add what you found" form and each row's Edit/Delete/Flag/Worked
 * buttons that _experience.html renders as plain HTML, to the
 * /api/experience/{vin}/inputs round-trip cuore/api/experience.py serves.
 *
 * Mirrors feedback.js's own style (one IIFE, vin read off
 * document.body.dataset.vin, defensive against missing elements, a
 * remembered name instead of a remembered author) -- see that file for
 * the precedent. Every `_experience.html` card on the page is wired
 * independently (a page can include it more than once, e.g. one per
 * system row), scoped by the nearest [data-exp-card] ancestor.
 */
(function () {
  "use strict";

  var NAME_KEY = "cuore_experience_finder_name";

  function vinOf(card) {
    // A card's own [data-vin] wins (the mobile "Everything else" entry
    // point has no vin on <body> -- see m_home.html's additive block --
    // and a desktop page that happens to know its vin can set it here
    // too); body's data-vin (feedback.js's own convention) is the
    // fallback every other desktop page relies on.
    if (card) {
      var own = card.getAttribute("data-vin");
      if (own) return own;
    }
    return document.body.getAttribute("data-vin") || "";
  }

  function rememberedName() {
    try { return localStorage.getItem(NAME_KEY) || ""; } catch (e) { return ""; }
  }
  function rememberName(name) {
    try { if (name) { localStorage.setItem(NAME_KEY, name); } } catch (e) { /* ignore */ }
  }

  function apiBase(vin) {
    return "/api/experience/" + encodeURIComponent(vin) + "/inputs";
  }

  function roleLabel(role) {
    return { cuore: "CUORE curated", mechanic: "Mechanic", driver: "Driver", owner: "Owner" }[role] || "Owner";
  }

  function setStatus(card, text) {
    var el = card.querySelector("[data-exp-add-status]");
    if (el) el.textContent = text;
  }

  // -- row rendering (used both for a freshly-added row and a post-edit
  // refresh) -------------------------------------------------------------
  function buildRow(l) {
    var row = document.createElement("div");
    row.className = "exp-row";
    row.setAttribute("data-exp-row", "");
    row.setAttribute("data-exp-id", l.id);
    row.setAttribute("data-exp-curated", l.curated ? "true" : "false");

    var main = document.createElement("div");
    main.className = "exp-main";

    var a = document.createElement("a");
    a.href = l.url; a.target = "_blank"; a.rel = "noopener";
    a.textContent = l.title || l.url;
    main.appendChild(a);

    var attrib = document.createElement("div");
    attrib.className = "small muted exp-attrib";
    var role = (l.found_by || {}).role;
    var bits = ["Found by " + roleLabel(role)];
    if ((l.found_by || {}).name) bits.push((l.found_by || {}).name);
    if (l.found_at) bits.push(String(l.found_at).slice(0, 10));
    attrib.textContent = bits.join(" · ");
    main.appendChild(attrib);

    if (l.note) {
      var note = document.createElement("div");
      note.className = "small exp-note";
      note.setAttribute("data-exp-note", "");
      note.textContent = l.note;
      main.appendChild(note);
    }

    row.appendChild(main);

    var chip = document.createElement("span");
    chip.className = "chip plain";
    chip.setAttribute("data-exp-role-chip", "");
    chip.textContent = roleLabel(role);
    row.appendChild(chip);

    var actions = document.createElement("div");
    actions.className = "exp-row-actions";
    if (!l.curated) {
      var editBtn = document.createElement("button");
      editBtn.type = "button"; editBtn.className = "btn small";
      editBtn.textContent = "Edit"; editBtn.setAttribute("data-exp-edit", l.id);
      actions.appendChild(editBtn);
      var delBtn = document.createElement("button");
      delBtn.type = "button"; delBtn.className = "btn small";
      delBtn.textContent = "Delete"; delBtn.setAttribute("data-exp-delete", l.id);
      actions.appendChild(delBtn);
    } else {
      var flagBtn = document.createElement("button");
      flagBtn.type = "button"; flagBtn.className = "btn small";
      flagBtn.textContent = "Flag as wrong/outdated"; flagBtn.setAttribute("data-exp-flag", l.id);
      actions.appendChild(flagBtn);
    }
    var workedBtn = document.createElement("button");
    workedBtn.type = "button"; workedBtn.className = "btn small";
    workedBtn.textContent = "Worked on this car?"; workedBtn.setAttribute("data-exp-worked", l.id);
    actions.appendChild(workedBtn);
    row.appendChild(actions);

    return row;
  }

  // -- "+ Add what you found" form ---------------------------------------
  function wireRolePicker(form) {
    var picker = form.querySelector("[data-exp-role-picker]");
    if (!picker) return;
    var hidden = picker.querySelector('input[name="role"]');
    var chips = picker.querySelectorAll("[data-role-chip]");
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        chips.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
        chip.setAttribute("aria-pressed", "true");
        if (hidden) hidden.value = chip.getAttribute("data-role-chip");
      });
    });
  }

  function wireAddForm(card, vin) {
    var form = card.querySelector("[data-exp-add-form]");
    if (!form) return;
    wireRolePicker(form);

    var nameInput = form.querySelector("[data-exp-name]");
    if (nameInput && !nameInput.value) nameInput.value = rememberedName();

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var fd = new FormData(form);
      var role = String(fd.get("role") || "mechanic");
      var name = String(fd.get("name") || "").trim();
      rememberName(name);
      var payload = {
        scope: {
          code: String(fd.get("scope_code") || "").trim(),
          family: String(fd.get("scope_family") || "").trim(),
          job: String(fd.get("scope_job") || "").trim()
        },
        url: String(fd.get("url") || "").trim(),
        title: String(fd.get("title") || "").trim(),
        kind: String(fd.get("kind") || "note"),
        role: role,
        name: name,
        note: String(fd.get("note") || "").trim(),
        rating: String(fd.get("rating") || "unsure"),
        confirm_duplicate: form.getAttribute("data-exp-confirm-dup") === "1"
      };
      setStatus(card, "Saving…");
      fetch(apiBase(vin), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (data.duplicate) {
          var existing = data.existing || {};
          setStatus(card, "Already on file — found by " + roleLabel((existing.found_by || {}).role) +
            (existing.found_by && existing.found_by.name ? " (" + existing.found_by.name + ")" : "") +
            ". Submit again to add anyway.");
          form.setAttribute("data-exp-confirm-dup", "1");
          return;
        }
        form.removeAttribute("data-exp-confirm-dup");
        var list = card.querySelector("[data-exp-list]");
        if (list) list.insertBefore(buildRow(data), list.firstChild);
        setStatus(card, "Saved. Thanks.");
        form.reset();
        if (nameInput) nameInput.value = name;
      }).catch(function () {
        setStatus(card, "Could not save — try again.");
      });
    });
  }

  // -- per-row actions: edit / delete / flag / worked ---------------------
  function wireRowActions(card, vin) {
    card.addEventListener("click", function (ev) {
      var target = ev.target;
      if (!(target instanceof Element)) return;

      var editId = target.getAttribute && target.getAttribute("data-exp-edit");
      if (editId) {
        var row = target.closest("[data-exp-row]");
        var noteEl = row && row.querySelector("[data-exp-note]");
        var current = noteEl ? noteEl.textContent : "";
        var next = window.prompt("Edit note:", current);
        if (next === null) return;
        fetch(apiBase(vin) + "/" + encodeURIComponent(editId), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ by_role: "mechanic", note: next })
        }).then(function (r) { return r.json(); }).then(function () {
          if (noteEl) noteEl.textContent = next;
        });
        return;
      }

      var delId = target.getAttribute && target.getAttribute("data-exp-delete");
      if (delId) {
        var delRow = target.closest("[data-exp-row]");
        fetch(apiBase(vin) + "/" + encodeURIComponent(delId), { method: "DELETE" })
          .then(function (r) { return r.json(); })
          .then(function () {
            if (!delRow) return;
            delRow.hidden = true;
            var undo = document.createElement("div");
            undo.className = "small exp-undo";
            var link = document.createElement("a");
            link.href = "#"; link.textContent = "Deleted. Undo?";
            link.addEventListener("click", function (e) {
              e.preventDefault();
              fetch(apiBase(vin) + "/" + encodeURIComponent(delId) + "/restore", { method: "POST" })
                .then(function () { delRow.hidden = false; undo.remove(); });
            });
            undo.appendChild(link);
            delRow.insertAdjacentElement("afterend", undo);
          });
        return;
      }

      var flagId = target.getAttribute && target.getAttribute("data-exp-flag");
      if (flagId) {
        var reason = window.prompt('Flag as "wrong" or "outdated"? (type one)', "wrong");
        if (!reason) return;
        var flagKind = reason.trim().toLowerCase() === "outdated" ? "outdated" : "wrong";
        fetch("/api/experience/links/" + encodeURIComponent(flagId) + "/flag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ by_role: "mechanic", flag_kind: flagKind, note: "" })
        }).then(function () { target.textContent = "Flagged — thanks"; target.disabled = true; });
        return;
      }

      var workedId = target.getAttribute && target.getAttribute("data-exp-worked");
      if (workedId) {
        fetch("/api/experience/links/" + encodeURIComponent(workedId) + "/worked", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ by_role: "mechanic" })
        }).then(function () { target.textContent = "Marked worked on this car"; target.disabled = true; });
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var cards = document.querySelectorAll("[data-exp-card]");
    cards.forEach(function (card) {
      var vin = vinOf(card);
      if (!vin) return;
      wireAddForm(card, vin);
      wireRowActions(card, vin);
    });
  });
})();
