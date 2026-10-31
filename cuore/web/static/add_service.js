/* Add Service (add_service.html). Talks to /api/car/identify, /api/car/create-service,
 * /add/art and /add/story. Nothing on this page contacts anything but this server.
 *
 * The logic that decides what the screen says (chips, title, rows, the five-step
 * strip) is in pure functions at the top, exported as window.AddService, so it can
 * be fed recorded events without a car. */
(function () {
  "use strict";

  // --- pure logic ---------------------------------------------------------------------------

  var SRC_READ = "read from the car", SRC_DECODED = "decoded from the VIN",
      SRC_TYPED = "typed in", SRC_NONE = "not found";
  var STEPS = [["vin", "VIN"], ["modules", "Modules"], ["software", "Software"],
               ["decode", "Decode"], ["story", "Story"]];

  function hasValue(f) { return !!(f && f.value !== null && f.value !== undefined && f.value !== ""); }

  /* The chip a field wears. A field with no value is UNKNOWN whatever its source says. */
  function chipFor(f) {
    if (!hasValue(f)) return { chip: "unknown", label: "Unknown", unverified: false };
    if (f.source === SRC_READ) return { chip: "read", label: "Read", unverified: false };
    if (f.source === SRC_DECODED) return { chip: "decoded", label: "Decoded", unverified: f.verified === false };
    if (f.source === SRC_TYPED) return { chip: "entered", label: "Entered", unverified: false };
    return { chip: "unknown", label: "Unknown", unverified: false };
  }

  function val(fields, k) { return hasValue(fields && fields[k]) ? fields[k].value : null; }

  /* Never an invented model: a make with no model reads "<make>, model not identified". */
  function titleFor(fields) {
    var make = val(fields, "make"), model = val(fields, "model"), year = val(fields, "model_year");
    if (make && model) return make + " " + model + (year ? " " + year : "");
    if (make) return make + ", model not identified";
    return "Car not identified";
  }

  function notFound(why) { return { value: null, source: SRC_NONE, detail: why }; }

  /* Rows of the card, in reading order. `editable` rows can be corrected by tapping. */
  function rowsFor(card, carRead) {
    var f = card.fields || {};
    var mods = card.modules || [];
    var answered = mods.filter(function (m) { return m.answered; }).length;
    var modRow;
    if (!carRead) modRow = notFound("the car was not read (VIN typed)");
    else if (!mods.length) modRow = f.modules_answered && hasValue(f.modules_answered) ? f.modules_answered
      : notFound((f.modules_answered && f.modules_answered.detail) || "no module was asked");
    else if (!answered) modRow = notFound("no module answered (" + mods.length + " asked)");
    else modRow = { value: answered + " of " + mods.length + " answered", source: SRC_READ,
                    detail: "module identity reads", verified: true };
    var sw = f.software_ids;
    if (!carRead) sw = notFound("the car was not read (VIN typed)");
    else if (!hasValue(sw)) sw = notFound((sw && sw.detail) || "no module reported a software number");
    return [
      { key: "make", label: "Make", f: f.make || notFound("no rule"), editable: true },
      { key: "model", label: "Model", f: f.model || notFound("no rule"), editable: true },
      { key: "model_year", label: "Year", f: f.model_year || notFound("no rule"), editable: true },
      { key: "engine", label: "Engine", f: f.engine || notFound("CUORE has no engine rule for this VIN yet"), editable: true },
      { key: "market", label: "Market", f: f.market || notFound("no rule"), editable: true },
      { key: "trim", label: "Trim", f: f.trim || notFound("CUORE has no trim rule for this VIN yet"), editable: true },
      { key: "vin", label: "VIN", f: f.vin || notFound("no VIN"), editable: false, mono: true },
      { key: "modules_answered", label: "Modules", f: modRow, editable: false },
      { key: "software_ids", label: "Software IDs", f: sw, editable: false, ids: true }
    ];
  }

  function freshLive() {
    var live = {};
    STEPS.forEach(function (s) { live[s[0]] = { state: "pending", why: "" }; });
    live.vin.state = "running";
    live.modules_list = [];
    return live;
  }

  /* One NDJSON event in, the step strip out. A step turns "ok" only when real data
   * arrived for it; "failed" always carries the reason. */
  function reduceLive(live, ev) {
    var next = JSON.parse(JSON.stringify(live));
    var k = ev && ev.event;
    if (k === "start") {
      next.vin.state = "running";
    } else if (k === "refused") {
      next.vin = { state: "failed", why: ev.reason || "the read was refused" };
      next.modules = { state: "failed", why: "no module was asked: " + next.vin.why };
      next.refused = true;
    } else if (k === "vin") {
      next.vin = ev.answered ? { state: "ok", why: "" }
        : { state: "failed", why: ev.reason || "the car did not report a VIN" };
      next.modules.state = "running";
    } else if (k === "module") {
      next.modules_list.push(ev);
      next.modules.state = "running";
    } else if (k === "done") {
      var card = ev.card || {}, f = card.fields || {}, mods = card.modules || next.modules_list;
      var answered = mods.filter(function (m) { return m.answered; }).length;
      if (!next.refused) {
        next.modules = answered ? { state: "ok", why: "" }
          : { state: "failed", why: mods.length ? "none of the " + mods.length + " modules answered"
              : (f.modules_answered && f.modules_answered.detail) || "no module was asked" };
      }
      next.software = hasValue(f.software_ids) ? { state: "ok", why: "" }
        : { state: "failed", why: (f.software_ids && f.software_ids.detail) || "no software number was read" };
      var decoded = ["make", "model", "model_year", "market"].some(function (n) {
        return hasValue(f[n]) && f[n].source === SRC_DECODED; });
      next.decode = decoded ? { state: "ok", why: "" }
        : { state: "failed", why: !card.vin ? "no VIN to decode" : (f.make && f.make.detail) || "the VIN could not be decoded" };
      next.done = true;
      next.card = card;
    }
    return next;
  }

  /* Split a streamed body into complete JSON lines; returns [events, leftover]. */
  function parseLines(buffer) {
    var parts = buffer.split("\n"), rest = parts.pop(), out = [];
    parts.forEach(function (p) { if (p.trim()) { try { out.push(JSON.parse(p)); } catch (e) { /* skip a torn line */ } } });
    return [out, rest];
  }

  function cleanVin(s) { return String(s || "").toUpperCase().replace(/[\s-]+/g, ""); }

  /* Live check while typing: length and characters only. The check digit needs the
   * backend (it knows where it is required) and is shown from its answer. */
  function vinProgress(raw) {
    var v = cleanVin(raw);
    var bad = []; v.split("").forEach(function (c) { if (!/[A-HJ-NPR-Z0-9]/.test(c) && bad.indexOf(c) < 0) bad.push(c); });
    var notes = [];
    if (bad.length) notes.push("Not allowed in a VIN: " + bad.join(" ") + (bad.some(function (c) { return "IOQ".indexOf(c) >= 0; }) ? " (I, O and Q are never used)" : ""));
    if (v.length > 17) notes.push("Too long by " + (v.length - 17));
    return { vin: v, length: v.length, bad: bad, notes: notes, ready: v.length === 17 && !bad.length };
  }

  // --- the Choose screen: pure logic --------------------------------------------------------
  // The pick list is a list, not evidence. What is picked is stored as "typed in", with the
  // detail "chosen from the list", and wins over the VIN decode; a disagreement is shown.

  var OTHER = "Other / not listed", CHOSEN_DETAIL = "chosen from the list";

  /* Year options, newest first: last_year (or next calendar year when null) down to first_year. */
  function yearsFor(model, thisYear) {
    var out = [];
    if (!model || typeof model.first_year !== "number") return out;
    var top = typeof model.last_year === "number" ? model.last_year : thisYear + 1;
    for (var y = top; y >= model.first_year; y--) out.push(y);
    return out;
  }

  function modelName(c) { return c.model === OTHER ? String(c.modelText || "").trim() : c.model; }
  function engineName(c) { return c.engine === OTHER ? String(c.engineText || "").trim() : c.engine; }

  /* Continue needs brand, model (and its text if "Other"), year and a valid VIN. Engine is optional. */
  function chooseReady(c, vinOk) {
    return !!(vinOk && c.brand && modelName(c) && c.year);
  }

  /* The fields the person picked, as card fields. An engine left at "Not sure" is not a field. */
  function choiceFields(c, at) {
    function f(v) { var o = { value: v, source: SRC_TYPED, detail: CHOSEN_DETAIL, verified: true }; if (at) o.at = at; return o; }
    var out = { make: f(c.brand), model: f(modelName(c)), model_year: f(parseInt(c.year, 10)) };
    if (engineName(c)) out.engine = f(engineName(c));
    return out;
  }

  function same(a, b) { return String(a).toLowerCase().replace(/[^a-z0-9]/g, "") === String(b).toLowerCase().replace(/[^a-z0-9]/g, ""); }

  /* One sentence naming both values when the VIN decode and the person's field disagree, else "". */
  function choiceConflict(decoded, fields) {
    var diffs = [];
    [["make", "Make"], ["model", "Model"], ["model_year", "Year"]].forEach(function (k) {
      var d = val(decoded, k[0]), c = val(fields, k[0]);
      if (d !== null && c !== null && !same(d, c)) diffs.push(k[1] + ": the VIN decodes to " + d + ", you chose " + c);
    });
    return diffs.length ? "The VIN and your choice disagree. " + diffs.join("; ") + ". CUORE keeps your choice." : "";
  }

  var api = { yearsFor: yearsFor, chooseReady: chooseReady, choiceFields: choiceFields, choiceConflict: choiceConflict,
              chipFor: chipFor, titleFor: titleFor, rowsFor: rowsFor, freshLive: freshLive,
              reduceLive: reduceLive, parseLines: parseLines, vinProgress: vinProgress, cleanVin: cleanVin };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.AddService = api;
  if (typeof document === "undefined" || !document.getElementById("as")) return;

  // --- page ---------------------------------------------------------------------------------

  var root = document.getElementById("as");
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }

  var state;
  function resetState() {
    state = { run: 0, vin: "", fields: {}, card: null, carRead: false, unit: "km", odo: "",
              reasonKey: "", story: null, decodeCache: {}, typedSeq: 0,
              choose: { brand: "", model: "", year: "", engine: "", modelText: "", engineText: "" },
              vinOk: false, chosen: false, decoded: null };
  }
  resetState();

  function show(name) {
    [].forEach.call(root.querySelectorAll(".as-screen"), function (s) { s.hidden = s.getAttribute("data-screen") !== name; });
    var h = root.querySelector('.as-screen[data-screen="' + name + '"] .as-h');
    if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
    window.scrollTo(0, 0);
  }

  function post(url, body) {
    return fetch(url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); });
  }
  function errText(res) {
    var b = res.body || {}, d = b.detail || b.error || "";
    if (typeof d !== "string") d = JSON.stringify(d);
    return d || ("the server answered " + res.status);
  }

  // --- S1 -----------------------------------------------------------------------------------

  var typeForm = $("as-typeform"), vinIn = $("as-vin"), vinState = $("as-vin-state"), vinGo = $("as-vin-go");

  function setVinState(box, parts) {
    clear(box);
    parts.forEach(function (p) { box.appendChild(el("span", p[0], p[1])); box.appendChild(document.createElement("br")); });
  }

  /* The live VIN check, shared by Type and Choose: characters while typing, then the
   * backend's answer (read_car false, so the car is never touched). setReady(true) only
   * for a VIN the backend accepts; its decode is kept for Continue. */
  function wireVin(input, box, setReady) {
    input.addEventListener("input", function () {
      var pos = input.selectionStart, before = input.value, p = vinProgress(before);
      var shown = before.toUpperCase().replace(/[\s-]+/g, "");
      if (shown !== before) { input.value = shown; try { input.setSelectionRange(pos, pos); } catch (e) { /* ignore */ } }
      setReady(false);
      var seq = ++state.typedSeq;
      var parts = [["", p.length + " of 17 characters"]];
      p.notes.forEach(function (n) { parts.push(["bad", n]); });
      if (!p.ready) { setVinState(box, parts); return; }
      parts.push(["", "Checking the VIN (this does not touch the car)..."]);
      setVinState(box, parts);
      post("/api/car/identify", { vin: p.vin, read_car: false }).then(function (res) {
        if (seq !== state.typedSeq) return;
        if (!res.ok || !res.body.card) { setVinState(box, [["bad", "Could not check this VIN: " + errText(res)]]); return; }
        var card = res.body.card, v = card.validation || {}, out = [];
        if (v.ok) { state.decodeCache[p.vin] = card; setReady(true); out.push(["good", "17 characters, no I, O or Q."]); }
        (v.errors || []).forEach(function (e) { out.push(["bad", e]); });
        (v.warnings || []).forEach(function (w) { out.push(["warn", "Warning: " + w]); });
        setVinState(box, out);
      }, function () { if (seq === state.typedSeq) setVinState(box, [["bad", "CUORE did not answer. Check that it is running."]]); });
    });
  }

  wireVin(vinIn, vinState, function (ok) { vinGo.disabled = !ok; });

  typeForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var card = state.decodeCache[cleanVin(vinIn.value)];
    if (card) enterCard(card, false);
  });

  root.addEventListener("click", function (e) {
    var t = e.target.closest("[data-act]");
    if (!t) return;
    var act = t.getAttribute("data-act");
    if (act === "plug") startLive();
    else if (act === "type") openType();
    else if (act === "choose") openChoose();
    else if (act === "back-find") show("find");
    else if (act === "restart") {
      resetState(); vinIn.value = ""; setVinState(vinState, []); vinGo.disabled = true; typeForm.hidden = true;
      $("as-cvin").value = ""; setVinState($("as-cvin-state"), []); $("as-c-modeltext").value = ""; $("as-c-enginetext").value = "";
      $("as-type").setAttribute("aria-expanded", "false"); show("find");
    }
    else if (act === "back-card") show("card");
    else if (act === "back-gaps") show("gaps");
  });

  function openType() {
    state.run++; // abandon a running read
    show("find");
    typeForm.hidden = false;
    $("as-type").setAttribute("aria-expanded", "true");
    vinIn.focus();
  }

  // --- S1c: Choose ----------------------------------------------------------------------------

  var cData = JSON.parse($("as-choices").textContent), cVin = $("as-cvin"), cGo = $("as-choose-go");

  function brandModels(name) {
    var b = cData.brands.filter(function (x) { return x.name === name; })[0];
    return b ? b.models : [];
  }
  function modelRec(c) { return brandModels(c.brand).filter(function (m) { return m.name === c.model; })[0] || null; }

  /* Rebuild one <select>: a prompt, then the options; keeps `current` if it is still there. */
  function fillSelect(sel, prompt, items, current) {
    clear(sel);
    var first = el("option", "", prompt); first.value = ""; sel.appendChild(first);
    items.forEach(function (it) { var o = el("option", "", String(it)); o.value = String(it); sel.appendChild(o); });
    sel.value = items.map(String).indexOf(String(current)) >= 0 ? String(current) : "";
  }

  function drawChoose() {
    var c = state.choose, rec = modelRec(c);
    fillSelect($("as-c-brand"), "Choose a brand", cData.brands.map(function (b) { return b.name; }), c.brand);
    fillSelect($("as-c-model"), "Choose a model", brandModels(c.brand).map(function (m) { return m.name; }), c.model);
    fillSelect($("as-c-year"), "Choose a year", yearsFor(rec, new Date().getFullYear()), c.year);
    fillSelect($("as-c-engine"), "Not sure", rec ? rec.engines : [], c.engine);
    $("as-c-model").disabled = !c.brand;
    $("as-c-year").disabled = !c.model;
    $("as-c-engine").disabled = !c.year;
    $("as-c-modeltext").hidden = c.model !== OTHER;
    $("as-c-enginetext").hidden = c.engine !== OTHER;
    cGo.disabled = !chooseReady(c, state.vinOk);
  }

  /* Changing one list clears every list after it. */
  [["brand", "as-c-brand", ["model", "year", "engine", "modelText", "engineText"]],
   ["model", "as-c-model", ["year", "engine", "modelText", "engineText"]],
   ["year", "as-c-year", ["engine", "engineText"]],
   ["engine", "as-c-engine", ["engineText"]]].forEach(function (d) {
    $(d[1]).addEventListener("change", function () {
      state.choose[d[0]] = $(d[1]).value;
      d[2].forEach(function (k) { state.choose[k] = ""; });
      $("as-c-modeltext").value = state.choose.modelText; $("as-c-enginetext").value = state.choose.engineText;
      drawChoose();
    });
  });
  [["modelText", "as-c-modeltext"], ["engineText", "as-c-enginetext"]].forEach(function (d) {
    $(d[1]).addEventListener("input", function () { state.choose[d[0]] = $(d[1]).value; drawChoose(); });
  });
  wireVin(cVin, $("as-cvin-state"), function (ok) { state.vinOk = ok; cGo.disabled = !chooseReady(state.choose, ok); });

  function openChoose() {
    state.run++; // abandon a running read
    drawChoose(); show("choose");
  }

  $("as-chooseform").addEventListener("submit", function (e) {
    e.preventDefault();
    var card = state.decodeCache[cleanVin(cVin.value)];
    if (card && chooseReady(state.choose, state.vinOk)) enterCard(card, false, state.choose);
  });

  // --- S2 -----------------------------------------------------------------------------------

  var failsEl = el("ul", "as-fails");
  $("as-steps").parentNode.insertBefore(failsEl, $("as-steps").nextSibling);

  function drawLive(live) {
    var ol = $("as-steps"); clear(ol); clear(failsEl);
    STEPS.forEach(function (s, i) {
      var st = live[s[0]], li = el("li", "as-step"), glyph = { ok: "✓", failed: "✕", running: "…" }[st.state] || String(i + 1);
      li.setAttribute("data-state", st.state);
      li.appendChild(el("span", "as-step-dot", glyph));
      li.appendChild(el("span", "as-step-name", s[1]));
      li.appendChild(el("span", "sr-only", st.state === "ok" ? "done" : st.state === "failed" ? "failed" : st.state === "running" ? "in progress" : "waiting"));
      ol.appendChild(li);
      if (st.state === "failed" && st.why) failsEl.appendChild(el("li", "", s[1] + ": " + st.why));
    });
    var mods = live.modules_list, answered = mods.filter(function (m) { return m.answered; }).length;
    var countEl = $("as-count"); countEl.hidden = !mods.length;
    countEl.textContent = mods.length ? answered + " answered" + (mods.length > answered ? ", " + (mods.length - answered) + " silent" : "") : "";
    var ul = $("as-mods");
    while (ul.children.length < mods.length) {
      var m = mods[ul.children.length], li2 = el("li", "as-mod");
      li2.setAttribute("data-answered", m.answered ? "true" : "false");
      li2.appendChild(el("span", "as-mod-code", m.code));
      li2.appendChild(el("span", "as-mod-name", m.name || ""));
      li2.appendChild(el("span", "as-chip", m.answered ? "answered" : "silent")).setAttribute("data-chip", m.answered ? "read" : "unknown");
      if (!m.answered) li2.appendChild(el("span", "as-mod-why", m.reason || "no reason given"));
      ul.appendChild(li2);
    }
  }

  function startLive() {
    var run = ++state.run, live = freshLive();
    state.live = live;
    clear($("as-mods")); $("as-live-msg").textContent = "Reading only. Nothing is cleared, written or changed.";
    clear($("as-live-actions"));
    drawArt($("as-live-art"), null, "The drawing appears once the model is known.");
    drawLive(live); show("live");

    function onEvent(ev) {
      if (run !== state.run) return;
      state.live = live = reduceLive(live, ev);
      drawLive(live);
      if (ev.event === "done") finishLive(run, live);
    }
    fetch("/api/car/identify", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vin: "", read_car: true, stream: true }) })
      .then(function (r) {
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(errText({ body: j, status: r.status })); });
        if (!r.body || !r.body.getReader) return r.text().then(function (t) { parseLines(t + "\n")[0].forEach(onEvent); });
        var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
        return (function pump() {
          return reader.read().then(function (chunk) {
            if (chunk.done) { parseLines(buf + "\n")[0].forEach(onEvent); return; }
            var res = parseLines(buf + dec.decode(chunk.value, { stream: true }));
            buf = res[1]; res[0].forEach(onEvent);
            return pump();
          });
        })();
      })
      .then(function () {
        if (run === state.run && !live.done) liveBroke(run, "the read ended before it finished");
      })
      .catch(function (err) { if (run === state.run && !live.done) liveBroke(run, err.message || "CUORE did not answer"); });
  }

  function liveBroke(run, why) {
    var live = state.live;
    STEPS.forEach(function (s) { if (live[s[0]].state === "running" || live[s[0]].state === "pending") live[s[0]] = { state: "failed", why: why }; });
    state.live = live; drawLive(live);
    $("as-live-msg").textContent = "The read did not finish.";
    liveActions(false);
  }

  function liveActions(canContinue) {
    var box = $("as-live-actions"); clear(box);
    var go = el("button", "as-go", canContinue ? "This is the car" : "Type the VIN instead");
    go.type = "button";
    go.addEventListener("click", function () { if (canContinue) enterCard(state.live.card, true); else openType(); });
    box.appendChild(go);
    var again = el("button", "as-sec", "Try the read again"); again.type = "button";
    again.addEventListener("click", startLive); box.appendChild(again);
    if (canContinue) { var t = el("button", "as-sec", "Type a VIN instead"); t.type = "button"; t.addEventListener("click", openType); box.appendChild(t); }
  }

  function finishLive(run, live) {
    var card = live.card || {};
    var refused = card.refused;
    drawArt($("as-live-art"), val(card.fields, "model"));
    var haveVin = hasValue(card.fields && card.fields.vin) && card.fields.vin.source === SRC_READ;
    $("as-live-msg").textContent = refused ? "The read was not started: " + refused
      : haveVin ? "Done. Check each step above, then continue." : "The car did not report a VIN.";
    liveActions(haveVin);
    if (haveVin) {
      live.story = { state: "running", why: "" }; drawLive(live);
      fetchStory(card.vin).then(function (s) {
        if (run !== state.run) return;
        live.story = s ? { state: "ok", why: "" } : { state: "failed", why: "CUORE's records could not be read" };
        state.story = s; drawLive(live);
      });
    } else {
      live.story = { state: "failed", why: "no VIN, so no records to look up" }; drawLive(live);
    }
  }

  // --- art, story ---------------------------------------------------------------------------

  var SVGNS = "http://www.w3.org/2000/svg";
  function drawArt(box, model, msg) {
    clear(box);
    if (!model) { box.appendChild(el("p", "as-noart", msg || "No drawing yet: the model is not identified.")); return; }
    fetch("/add/art?model=" + encodeURIComponent(model), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (art) {
        clear(box);
        if (!art) { box.appendChild(el("p", "as-noart", "No drawing yet for the " + model + ".")); return; }
        var svg = document.createElementNS(SVGNS, "svg");
        svg.setAttribute("viewBox", "0 0 860 360"); svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", model + ", side view");
        [["silhouette", "var(--surface-2)", null], ["ink", "var(--ink-2)", "evenodd"]].forEach(function (p) {
          if (!art[p[0]]) return;
          var path = document.createElementNS(SVGNS, "path");
          path.setAttribute("d", art[p[0]]); path.setAttribute("fill", p[1]);
          if (p[2]) path.setAttribute("fill-rule", p[2]);
          svg.appendChild(path);
        });
        box.appendChild(svg);
      }, function () { clear(box); box.appendChild(el("p", "as-noart", "No drawing yet for the " + model + ".")); });
  }

  function fetchStory(vin) {
    return fetch("/add/story?vin=" + encodeURIComponent(vin), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; }, function () { return null; });
  }

  function drawStory() {
    var box = $("as-story"), s = state.story; clear(box);
    if (!s) { box.hidden = true; return; } // no records answer: say nothing rather than guess
    box.hidden = false;
    box.appendChild(el("p", "as-label", "CUORE's records"));
    if (s.first_visit) { box.appendChild(el("p", "", "First visit. CUORE has no record of this car.")); return; }
    box.appendChild(el("p", "", "This car is on file."));
    if (s.last_visit) {
      var d = s.last_visit.at ? new Date(s.last_visit.at) : null;
      box.appendChild(el("p", "", "Last visit " + (d && !isNaN(d) ? d.toLocaleDateString() : "(date not recorded)") +
        (s.last_visit.reason ? ": " + s.last_visit.reason : ", no reason recorded") + "."));
    } else box.appendChild(el("p", "", "No visit is recorded."));
    var n = (s.open_jobs || []).length;
    box.appendChild(el("p", "", n ? n + " open job" + (n === 1 ? "" : "s") + (s.open_jobs[0].reason ? ": " + s.open_jobs[0].reason : "") + ". Opening a service will use the open job."
      : "No open job."));
  }

  // --- S3 -----------------------------------------------------------------------------------

  function enterCard(card, carRead, chosen) {
    state.card = card; state.carRead = carRead; state.vin = card.vin;
    state.fields = JSON.parse(JSON.stringify(card.fields || {}));
    state.chosen = !!chosen; state.decoded = chosen ? JSON.parse(JSON.stringify(card.fields || {})) : null;
    if (chosen) {
      var picked = choiceFields(chosen, new Date().toISOString());
      Object.keys(picked).forEach(function (k) { state.fields[k] = picked[k]; }); // the person's choice wins
    }
    state.editing = null;
    if (!carRead) { state.story = null; fetchStory(card.vin).then(function (s) { state.story = s; drawStory(); }); }
    $("as-card-note").textContent = carRead ? "Read from the car. Tap any field to correct it."
      : chosen ? "Chosen from the lists; the rest is decoded from the VIN. The car was not read. Tap any field to correct it."
      : "From the typed VIN. The car was not read. Tap any field to correct it.";
    drawCard(); show("card");
  }

  function currentCard() { return { fields: state.fields, modules: state.card ? state.card.modules : [] }; }

  function drawCard() {
    $("as-title").textContent = titleFor(state.fields);
    var warn = state.chosen ? choiceConflict(state.decoded, state.fields) : "";
    $("as-card-warn").textContent = warn; $("as-card-warn").hidden = !warn; // recomputed, so a correction clears it
    var model = val(state.fields, "model");
    drawArt($("as-card-art"), model);
    var unknownMake = !hasValue(state.fields.make) || state.pickingMake;
    $("as-make-picker").hidden = !unknownMake;
    var ul = $("as-fields"); clear(ul);
    rowsFor(currentCard(), state.carRead).forEach(function (r) {
      var li = el("li", r.ids || r.mono || state.editing === r.key ? "is-wide" : "");
      if (state.editing === r.key && r.key !== "make") { li.appendChild(editRow(r)); ul.appendChild(li); return; }
      var b = el("button", "as-field"); b.type = "button"; b.disabled = !r.editable;
      var c = chipFor(r.f);
      b.appendChild(el("span", "as-field-label", r.label));
      var v = el("span", "as-field-value" + (r.mono ? " is-vin" : "") + (c.chip === "unknown" ? " is-unknown" : ""));
      if (c.chip === "unknown") v.textContent = "Unknown";
      else if (r.ids) { var keys = Object.keys(r.f.value); keys.slice(0, 4).forEach(function (k) { v.appendChild(el("span", "", k + ": " + r.f.value[k])).appendChild(document.createElement("br")); });
        if (keys.length > 4) v.appendChild(el("span", "", "and " + (keys.length - 4) + " more")); }
      else v.textContent = String(r.f.value);
      b.appendChild(v);
      var col = el("span", "as-chipcol"), chip = el("span", "as-chip", c.label); chip.setAttribute("data-chip", c.chip);
      col.appendChild(chip);
      if (c.unverified) { var u = el("span", "as-chip unverified", "Unverified"); u.setAttribute("data-chip", "entered"); col.appendChild(u); }
      b.appendChild(col);
      // an unknown field says why on hover; the wall of "why" lines buried the card
      if (r.f.source === SRC_NONE) b.title = r.f.detail || "";
      else if (r.f.detail) b.appendChild(el("span", "as-field-detail", r.f.detail));
      if (r.editable) b.addEventListener("click", function () { startEdit(r.key); });
      li.appendChild(b); ul.appendChild(li);
    });
    drawStory();
  }

  function startEdit(key) {
    if (key === "make") { state.pickingMake = true; state.editing = null; drawCard(); $("as-make-picker").scrollIntoView({ block: "center" }); return; }
    state.editing = key; drawCard();
    var inp = root.querySelector(".as-edit"); if (inp) inp.focus();
  }

  function editRow(r) {
    var row = el("form", "as-edit-row"), id = "as-edit-" + r.key;
    var lab = el("label", "as-label", "Correct " + r.label.toLowerCase()); lab.setAttribute("for", id);
    var inp = el("input", "as-edit"); inp.id = id; inp.type = "text"; inp.autocomplete = "off";
    if (r.key === "model_year") { inp.inputMode = "numeric"; inp.maxLength = 4; }
    if (hasValue(r.f)) inp.value = String(r.f.value);
    var save = el("button", "as-sec as-save", "Save"); save.type = "submit";
    var cancel = el("button", "as-sec", "Cancel"); cancel.type = "button";
    cancel.addEventListener("click", function () { state.editing = null; drawCard(); });
    row.appendChild(lab); row.appendChild(inp); row.appendChild(save); row.appendChild(cancel);
    row.addEventListener("submit", function (e) {
      e.preventDefault();
      var raw = inp.value.trim();
      if (!raw) { state.editing = null; drawCard(); return; } // an empty entry changes nothing
      var v = raw;
      if (r.key === "model_year") {
        v = parseInt(raw, 10);
        if (!/^\d{4}$/.test(raw) || v < 1950 || v > new Date().getFullYear() + 2) { inp.setCustomValidity("Four digits, for example 2018"); inp.reportValidity(); return; }
      }
      setEntered(r.key, v);
    });
    return row;
  }

  function setEntered(key, v) {
    state.fields[key] = { value: v, source: SRC_TYPED, at: new Date().toISOString(),
                          detail: "entered by the technician", verified: true };
    state.editing = null; state.pickingMake = false; drawCard();
  }

  [].forEach.call(document.querySelectorAll("#as-make-tiles [data-make]"), function (b) {
    b.addEventListener("click", function () { setEntered("make", b.getAttribute("data-make")); });
  });
  $("as-card-next").addEventListener("click", function () { show("gaps"); drawGaps(); });

  // --- S4 -----------------------------------------------------------------------------------

  var odo = $("as-odo");
  odo.addEventListener("input", function () { odo.value = odo.value.replace(/\D+/g, "").slice(0, 7); state.odo = odo.value; drawGaps(); });
  [].forEach.call(root.querySelectorAll(".as-unit-b"), function (b) {
    b.addEventListener("click", function () {
      state.unit = b.getAttribute("data-unit");
      [].forEach.call(root.querySelectorAll(".as-unit-b"), function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
    });
  });
  [].forEach.call(root.querySelectorAll(".as-reason"), function (b) {
    b.addEventListener("click", function () {
      var k = b.getAttribute("data-reason"); state.reasonKey = state.reasonKey === k ? "" : k;
      [].forEach.call(root.querySelectorAll(".as-reason"), function (o) { o.setAttribute("aria-pressed", o === b && state.reasonKey ? "true" : "false"); });
    });
  });
  function drawGaps() {
    $("as-odo-note").textContent = state.odo ? "" : "You can skip this. The job will be marked odometer not recorded.";
  }
  $("as-gaps-next").addEventListener("click", function () { drawSummary(); show("open"); });

  // --- S5 -----------------------------------------------------------------------------------

  function reasonText() {
    var free = $("as-why").value.trim();
    var tile = state.reasonKey ? root.querySelector('.as-reason[data-reason="' + state.reasonKey + '"]').getAttribute("data-reason") : "";
    return [tile, free].filter(Boolean).join(": ");
  }

  function sumRow(ul, k, v, flag) {
    var li = el("li"); li.appendChild(el("span", "k", k)); li.appendChild(el("span", flag ? "flag" : "", v)); ul.appendChild(li);
  }

  function drawSummary() {
    var ul = $("as-summary"); clear(ul);
    sumRow(ul, "Car", titleFor(state.fields));
    sumRow(ul, "VIN", state.vin);
    sumRow(ul, "Odometer", state.odo ? Number(state.odo).toLocaleString() + " " + state.unit : "not recorded", !state.odo);
    sumRow(ul, "Reason", reasonText() || "not given", !reasonText());
    $("as-open-err").hidden = true;
  }

  $("as-open-go").addEventListener("click", function () {
    var btn = $("as-open-go"); btn.disabled = true;
    var body = { fields: state.fields, reason: reasonText(), odometer: state.odo ? Number(state.odo) : null, unit: state.unit };
    post("/api/car/create-service", body).then(function (res) {
      btn.disabled = false;
      if (!res.ok) { var e = $("as-open-err"); e.textContent = "The job was not opened: " + errText(res); e.hidden = false; return; }
      drawDone(res.body);
    }, function () {
      btn.disabled = false; var e = $("as-open-err");
      e.textContent = "CUORE did not answer, so the job was not opened. Nothing was changed."; e.hidden = false;
    });
  });

  function drawDone(r) {
    var existing = r.existing_car, created = r.created, reusedJob = r.already_open;
    $("as-done-h").textContent = existing ? "Existing car opened" : "Job opened";
    $("as-done-msg").textContent = !existing ? "A new car was added and its job opened."
      : reusedJob ? "This car was already on file and a job was already open. The existing car and job were opened. No duplicate was made."
      : "This car was already on file. The existing car was opened and a new job was added. No duplicate car was made.";
    var ul = $("as-done-list"); clear(ul);
    (r.warnings || []).forEach(function (w) { sumRow(ul, "Warning", w, true); });
    if (r.odometer_missing) sumRow(ul, "Odometer", "not recorded", true);
    else if (r.odometer) sumRow(ul, "Odometer", Number(r.odometer.value).toLocaleString() + " " + r.odometer.unit);
    var href = "/v/" + encodeURIComponent(r.vin) + "/job";
    $("as-done-link").setAttribute("href", href);
    show("done");
    if (created && !existing) setTimeout(function () { if (!$("as-done-link").closest(".as-screen").hidden) window.location.assign(href); }, 1500);
  }
})();
