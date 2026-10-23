// "Export for AlfaCore" button (templates/_export_panel.html).
// POSTs to /api/export/{scan|job}/<id>?vin=..., then shows the saved path and a
// download link. The server only builds a file under its exports folder.
(function () {
  "use strict";

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }

  document.querySelectorAll("[data-export]").forEach(function (box) {
    var btn = box.querySelector("[data-export-btn]");
    var out = box.querySelector("[data-export-result]");
    if (!btn || !out) return;
    var token = new URLSearchParams(location.search).get("token");
    var tokenQ = token ? "&token=" + encodeURIComponent(token) : "";

    btn.addEventListener("click", function () {
      btn.disabled = true;
      out.hidden = false;
      out.textContent = "Exporting...";
      fetch(box.dataset.exportUrl + tokenQ, {method: "POST", credentials: "same-origin"})
        .then(function (r) {
          return r.json().then(function (j) { return {ok: r.ok, body: j}; });
        })
        .then(function (res) {
          if (!res.ok) {
            out.innerHTML = "<strong>Not exported:</strong> " +
              esc(res.body.detail || res.body.error || "unknown error");
            return;
          }
          var b = res.body;
          var warn = (b.warnings || []).map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("");
          out.innerHTML =
            "<p><strong>Saved</strong> (" + b.bytes + " bytes, " + b.files.length + " files)<br>" +
            "<span class=\"mono\">" + esc(b.path) + "</span></p>" +
            "<p><a class=\"btn small\" href=\"/api/export/download?path=" +
            encodeURIComponent(b.path) + tokenQ + "\">Download " + esc(b.filename) + "</a></p>" +
            (warn ? "<p>Check before carrying it:</p><ul>" + warn + "</ul>" : "");
        })
        .catch(function (e) { out.textContent = "Export failed: " + e; })
        .then(function () { btn.disabled = false; });
    });
  });
})();
