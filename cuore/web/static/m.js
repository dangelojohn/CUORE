/* "Tell CUORE" mobile page. Small, no framework, additive only -- every
 * form here is a plain <form method="post"> that already works with
 * scripting off (see owner_routes.py's own docstring); everything below
 * is either a convenience (chip-fills-input, inline photo preview) or the
 * one feature that genuinely needs JS: Snap & fill's client-side call to
 * POST /api/vision/{vin}/read. A 404/network error/`available:false` from
 * that endpoint is treated identically -- the Continue button underneath
 * always still works, uploading the same photo through the same plain
 * POST this script never intercepts.
 */
(function () {
  "use strict";

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ---------------------------------------------------------------------
  // Intro overlay: dismiss on tap already works with no JS at all (the
  // checkbox/label trick _intro.html itself uses) -- this only adds a
  // tap-anywhere-on-the-page escape hatch so a long first paint doesn't
  // feel stuck, matching the main app's own overlay behaviour.
  function wireIntroDismiss() {
    var toggle = qs("#intro-dismiss");
    if (!toggle) return;
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") toggle.checked = true;
    });
  }

  // ---------------------------------------------------------------------
  // Chip fills a nearby text input (remembered free-text fields, and the
  // fill-up form's station chip row) -- one tap, no typing.
  function wireFillChips() {
    qsa("[data-fill-chip]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var targetId = btn.getAttribute("data-fill-chip");
        var input = document.getElementById(targetId);
        if (!input) return;
        input.value = btn.textContent;
        var row = btn.closest(".m-chips");
        if (row) qsa(".m-chip", row).forEach(function (c) { c.classList.remove("is-selected"); });
        btn.classList.add("is-selected");
      });
    });
  }

  // ---------------------------------------------------------------------
  // Camera tile: inline preview via FileReader. Plain degrade with no JS
  // is just "no preview, the file still rides along with the form".
  function wirePhotoPreview() {
    qsa("[data-photo-input]").forEach(function (input) {
      input.addEventListener("change", function () {
        var file = input.files && input.files[0];
        var tile = input.previousElementSibling; // the <label class="m-camera-tile">
        var preview = tile ? qs(".m-camera-preview", tile) : null;
        var text = tile ? qs(".m-camera-text", tile) : null;
        if (!file || !window.FileReader) return;
        var reader = new FileReader();
        reader.onload = function () {
          if (preview) { preview.src = reader.result; preview.hidden = false; }
          if (text) text.textContent = "Photo attached";
        };
        reader.readAsDataURL(file);
      });
    });
  }

  // ---------------------------------------------------------------------
  // Snap & fill: on photo selection, try the vision read in the background.
  // Success (available + fields or a suggested kind) navigates straight to
  // that kind's prefilled form; anything else just reports the fallback
  // note and leaves the plain Continue button to carry on normally.
  function status(el, text) {
    if (!el) return;
    el.textContent = text;
    el.hidden = !text;
  }

  function currentHint(form) {
    var checked = qs('input[name="hint"]:checked', form);
    return checked ? checked.value : "other";
  }

  function wireSnap() {
    var form = qs("[data-snap-form]");
    if (!form || !window.fetch || !window.FormData) return;
    var input = qs("[data-photo-input]", form);
    var statusEl = qs("[data-snap-status]", form);
    var vin = form.getAttribute("data-vin");
    if (!input || !vin) return;

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var hint = currentHint(form);
      status(statusEl, "Reading photo…");

      var mediaId = null;
      var uploadBody = new FormData();
      uploadBody.append("file", file);
      uploadBody.append("note", "snap: " + hint);

      var uploadP = fetch("/api/vehicles/" + encodeURIComponent(vin) + "/media", {
        method: "POST", body: uploadBody,
      }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (j && j.media && j.media[0]) mediaId = j.media[0].id;
      }).catch(function () { /* media upload is best-effort for this preview path */ });

      var readBody = new FormData();
      readBody.append("file", file);
      readBody.append("hint", hint);

      Promise.all([
        uploadP,
        fetch("/api/vision/" + encodeURIComponent(vin) + "/read", { method: "POST", body: readBody })
          .then(function (r) { return r.ok ? r.json() : null; })
          .catch(function () { return null; }),
      ]).then(function (results) {
        var read = results[1];
        if (!read || !read.available) {
          status(statusEl, (read && read.note) ||
                "Automatic reading is not set up on this CUORE; fill in by hand.");
          return;
        }
        var target = read.suggested_kind || null;
        var fields = read.fields || {};
        var haveAnyField = Object.keys(fields).some(function (k) {
          return fields[k] && fields[k].value !== null && fields[k].value !== undefined && fields[k].value !== "";
        });
        if (!target && !haveAnyField) {
          status(statusEl, read.note || "Nothing usable read from that photo; fill in by hand.");
          return;
        }

        var params = new URLSearchParams();
        if (mediaId) params.set("media_id", mediaId);
        params.set("hint", hint);
        Object.keys(fields).forEach(function (key) {
          var f = fields[key];
          if (f && f.value !== null && f.value !== undefined && f.value !== "") {
            params.set(key, f.value);
            params.set("source_" + key, "photo");
          }
        });

        status(statusEl, "Read from photo — opening the form…");
        if (target && target.indexOf("/") !== -1) {
          var parts = target.split("/");
          location.href = "/m/" + encodeURIComponent(vin) + "/add/" + parts[0] + "/" + parts[1]
            + "?" + params.toString();
        } else {
          // No single kind to jump to (e.g. a bare odometer reading) --
          // land on the category/all-categories picker with the read
          // value(s) carried forward instead of discarding them.
          location.href = "/m/" + encodeURIComponent(vin) + "/add?" + params.toString();
        }
      });
    });
  }

  wireIntroDismiss();
  wireFillChips();
  wirePhotoPreview();
  wireSnap();
})();
