/* Wiggle test: show seconds since the last mark so the tech can see the press
   registered. Progressive enhancement only; the form works as a plain POST.
   Never contacts the car. */
(function () {
  var form = document.querySelector("[data-pd-wiggle]");
  if (!form) return;
  var last = null;
  try { last = Number(sessionStorage.getItem("pd-wiggle-last") || "") || null; } catch (e) { last = null; }
  var out = document.createElement("p");
  out.className = "small muted";
  form.parentNode.insertBefore(out, form.nextSibling);
  form.addEventListener("submit", function () {
    try { sessionStorage.setItem("pd-wiggle-last", String(Date.now())); } catch (e) {}
  });
  function tick() {
    out.textContent = last ? "Last mark pressed " + Math.round((Date.now() - last) / 1000) + " s ago (this browser)." : "";
  }
  tick();
  setInterval(tick, 1000);
})();
