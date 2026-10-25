(function () {
  "use strict";
  var box = document.getElementById("ask-claude");
  if (!box) return;
  var $ = function (id) { return document.getElementById(id); };
  var prompt = $("ac-prompt"), msg = $("ac-msg");
  var head = prompt.getAttribute("data-head") || "", tail = prompt.getAttribute("data-tail") || "";

  function tech() {
    var o = $("ac-observed").value.trim() || "(left blank)";
    var q = $("ac-question").value.trim() || "(left blank)";
    return "\n## Tech inputs (from the technician, not CUORE readings)\n### What did you observe?\n" +
      o + "\n\n### What do you want to know?\n" + q + "\n";
  }
  function merged() { return head + tech() + tail; }
  function refresh() { prompt.value = merged(); }
  $("ac-observed").addEventListener("input", refresh);
  $("ac-question").addEventListener("input", refresh);
  refresh();

  function say(t) { msg.textContent = t; }
  function fallbackCopy() {
    prompt.focus(); prompt.select();
    try { return document.execCommand("copy"); } catch (e) { return false; }
  }
  $("ac-copy").addEventListener("click", function () {
    refresh();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(prompt.value).then(
        function () { say("Copied."); },
        function () { say(fallbackCopy() ? "Copied." : "Select the text below and copy it."); });
    } else {
      say(fallbackCopy() ? "Copied." : "Select the text below and copy it.");
    }
  });

  var run = $("ac-run");
  if (!run) return;
  var base = "/v/" + box.getAttribute("data-vin") + "/code/" + box.getAttribute("data-code") + "/ask-claude/";
  run.addEventListener("click", function () {
    run.disabled = true; say("Starting...");
    var body = new URLSearchParams({ observed: $("ac-observed").value, question: $("ac-question").value });
    fetch(base + "run", { method: "POST", body: body })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (r) {
        if (!r.ok) { say(r.j.error || "Could not start."); run.disabled = false; return; }
        say("Claude is working (up to 5 minutes)...");
        poll(r.j.job_id);
      })
      .catch(function () { say("Request failed."); run.disabled = false; });
  });
  function poll(id) {
    fetch(base + "status/" + encodeURIComponent(id)).then(function (r) { return r.json(); }).then(function (j) {
      if (j.state === "running") { setTimeout(function () { poll(id); }, 3000); return; }
      run.disabled = false;
      if (j.state === "done") {
        $("ac-answer").textContent = j.answer;      // textContent: never parsed as HTML
        $("ac-answer-box").hidden = false;
        $("ac-save-text").value = j.answer;
        say("Done. Review it, then save it to this code if useful.");
      } else { say(j.error || "Failed."); }
    }).catch(function () { say("Lost contact with the server."); run.disabled = false; });
  }
})();
