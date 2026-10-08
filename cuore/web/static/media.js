/* Media gallery page + the attach strip's camera/file picker.
 *
 * Everything here is additive, same rule as cuore.js: the upload form is a
 * plain multipart POST to /v/{vin}/media and works with scripting off; this
 * only adds a per-file progress bar on top of that same POST (via XHR, for
 * the upload-progress event fetch() cannot give), and the tap-to-view
 * dialog, which is inherently a scripting feature (<dialog> needs it to
 * open) -- its tile is a plain <a> to the original file, so a no-JS visit
 * still gets *something* on tap rather than nothing.
 */
(function () {
  "use strict";

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ---------------------------------------------------------------------
  // Upload: drag-and-drop onto the dropzone, then XHR with per-file
  // progress. On completion, navigate to xhr.responseURL -- the plain POST
  // handler always redirects (303) with a flash, and XHR follows that
  // transparently, so responseURL is already the right place to land.
  function wireUpload() {
    var form = qs("[data-media-upload]");
    if (!form) return;
    var zone = qs("[data-dropzone]", form);
    var input = qs('input[type="file"]', form);
    var list = qs("#media-upload-progress");

    if (zone && window.DataTransfer) {
      ["dragenter", "dragover"].forEach(function (evt) {
        zone.addEventListener(evt, function (ev) {
          ev.preventDefault();
          zone.classList.add("is-dragover");
        });
      });
      ["dragleave", "dragend", "drop"].forEach(function (evt) {
        zone.addEventListener(evt, function () { zone.classList.remove("is-dragover"); });
      });
      zone.addEventListener("drop", function (ev) {
        ev.preventDefault();
        var dropped = ev.dataTransfer && ev.dataTransfer.files;
        if (dropped && dropped.length) input.files = dropped;
      });
    }

    if (!window.XMLHttpRequest || !window.FormData) return; // plain submit still works

    form.addEventListener("submit", function (ev) {
      var files = input.files;
      if (!files || !files.length) return; // let the browser report "choose a file"
      ev.preventDefault();

      if (list) {
        list.hidden = false;
        list.innerHTML = "";
        for (var i = 0; i < files.length; i++) {
          var li = document.createElement("li");
          li.textContent = files[i].name;
          var bar = document.createElement("div");
          bar.className = "bar";
          var fill = document.createElement("span");
          bar.appendChild(fill);
          li.appendChild(bar);
          list.appendChild(li);
        }
      }

      var xhr = new XMLHttpRequest();
      xhr.open("POST", form.action, true);
      xhr.upload.addEventListener("progress", function (ev2) {
        if (!list || !ev2.lengthComputable) return;
        var pct = Math.round((ev2.loaded / ev2.total) * 100);
        qsa("li .bar > span", list).forEach(function (fill) { fill.style.width = pct + "%"; });
      });
      xhr.onload = function () {
        if (list) {
          var done = xhr.status >= 200 && xhr.status < 400;
          qsa("li", list).forEach(function (li) {
            li.classList.add(done ? "is-done" : "is-error");
          });
        }
        window.location.href = xhr.responseURL || form.action;
      };
      xhr.onerror = function () { form.submit(); }; // fall back to a plain submit
      xhr.send(new FormData(form));
    });
  }

  // ---------------------------------------------------------------------
  // The tap-to-view dialog on the gallery grid.
  function wireDialog() {
    var dialog = qs("#media-dialog");
    var grid = qs("#media-grid");
    if (!dialog || !grid || typeof dialog.showModal !== "function") return;

    var view = qs("#media-dialog-view", dialog);
    var meta = qs("#media-dialog-meta", dialog);
    var captionInput = qs("#media-dialog-caption", dialog);
    var tagsInput = qs("#media-dialog-tags", dialog);
    var msg = qs("#media-dialog-msg", dialog);
    var saveBtn = qs("#media-dialog-save", dialog);
    var hideBtn = qs("#media-dialog-hide", dialog);
    var originalLink = qs("#media-dialog-original", dialog);
    var current = null;

    function showMsg(text) {
      if (!msg) return;
      msg.textContent = text;
      msg.hidden = !text;
    }

    function openFor(tile) {
      var raw = tile.getAttribute("data-media-item");
      if (!raw) return;
      try { current = JSON.parse(raw); } catch (e) { return; }
      var fileUrl = "/api/media/" + encodeURIComponent(current.id) + "/file";
      view.innerHTML = "";
      if (current.kind === "video") {
        var video = document.createElement("video");
        video.src = fileUrl; video.controls = true;
        view.appendChild(video);
      } else {
        var img = document.createElement("img");
        img.src = fileUrl; img.alt = current.caption || current.filename || "";
        view.appendChild(img);
      }
      meta.textContent = (current.captured_at || current.uploaded_at || "") +
        (current.target_kind ? " · " + current.target_kind +
          (current.target_id ? ": " + current.target_id : "") : "");
      captionInput.value = current.caption || "";
      tagsInput.value = (current.tags || []).join(", ");
      originalLink.href = fileUrl;
      showMsg("");
      dialog.showModal();
    }

    grid.addEventListener("click", function (ev) {
      var tile = ev.target.closest(".media-tile");
      if (!tile) return;
      ev.preventDefault();
      openFor(tile);
    });

    function patch(body, onDone) {
      if (!current || !window.fetch) { showMsg("not available offline"); return; }
      fetch("/api/media/" + encodeURIComponent(current.id), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function (resp) {
        if (!resp.ok) throw new Error("update failed");
        onDone();
      }).catch(function () {
        showMsg("the media API is not available yet -- edit did not save");
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        var tags = tagsInput.value.split(",").map(function (t) { return t.trim(); }).filter(Boolean);
        patch({ caption: captionInput.value, tags: tags }, function () { showMsg("saved"); });
      });
    }
    if (hideBtn) {
      hideBtn.addEventListener("click", function () {
        if (!current || !window.fetch) { showMsg("not available offline"); return; }
        fetch("/api/media/" + encodeURIComponent(current.id) + "/hide", { method: "POST" })
          .then(function (resp) {
            if (!resp.ok) throw new Error("hide failed");
            var tile = grid.querySelector('[data-media-id="' + current.id + '"]');
            if (tile) tile.remove();
            dialog.close();
          }).catch(function () {
            showMsg("the media API is not available yet -- hide did not save");
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireUpload();
    wireDialog();
  });
})();
