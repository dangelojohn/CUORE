/* Tools page. Vanilla JS, no CDN. Tries the real /api/tools/* endpoints
 * first; falls back to the fixture catalogue embedded in the page (see
 * cuore/web/tools_routes.py) on a 404 -- that backend lands separately. */
(function () {
  "use strict";

  function safeStorage() {
    try {
      var k = "__cuore_tools_probe__";
      window.localStorage.setItem(k, "1");
      window.localStorage.removeItem(k);
      return window.localStorage;
    } catch (e) { return null; }
  }
  var storage = safeStorage();

  function readFixture() {
    var el = document.getElementById("tools-catalogue-fixture");
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function allTools(catalogue) {
    var out = [];
    (catalogue.groups || []).forEach(function (g) {
      (g.tools || []).forEach(function (t) { out.push(t); });
    });
    return out;
  }

  function findTool(catalogue, id) {
    return allTools(catalogue).find(function (t) { return t.id === id; });
  }

  // ---------------------------------------------------------------------
  // status strip

  function renderStatus(state) {
    var el = document.getElementById("t-status");
    var parts = [];
    if (state.active_vin) {
      parts.push('<span class="t-fact">vehicle: <b>' +
        esc(state.vehicle_name || ("..." + state.active_vin.slice(-6))) + "</b></span>");
    } else {
      parts.push('<span class="t-fact">vehicle: <a href="/">pick a vehicle</a></span>');
    }
    parts.push('<span class="t-fact">car: ' +
      (state.port ? "connected on " + esc(state.port) : '<a href="/live">not connected</a>') + "</span>");
    parts.push('<span class="t-fact">MultiEcuScan: ' + esc(state.mes_state || "unknown") + "</span>");
    parts.push('<span class="t-fact">cable: ' +
      (state.cable && state.cable !== "none" ? esc(state.cable) : '<a href="/live">none declared</a>') + "</span>");
    parts.push('<span class="t-fact">buses verified: ' +
      (state.buses_verified || 0) + "/" + (state.buses_total || 0) + "</span>");
    if (state.lock_holder && state.lock_holder !== "cuore") {
      parts.push('<span class="t-fact">held by ' + esc(state.lock_holder) + "</span>");
    }
    el.innerHTML = parts.join("");
  }

  // ---------------------------------------------------------------------
  // suggested row

  function renderSuggested(catalogue, ids) {
    var wrap = document.getElementById("t-suggested");
    var row = document.getElementById("t-suggested-row");
    row.innerHTML = "";
    var tools = (ids || []).map(function (id) { return findTool(catalogue, id); })
      .filter(Boolean).slice(0, 3);
    if (!tools.length) { wrap.hidden = true; return; }
    tools.forEach(function (t) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "t-suggest-btn";
      b.innerHTML = '<span class="n">' + esc(t.name) + '</span><span class="w">' + esc(t.what) + "</span>";
      b.addEventListener("click", function () {
        var card = document.querySelector('[data-tool-id="' + cssEscape(t.id) + '"]');
        if (card) {
          card.closest("details.t-group").open = true;
          card.scrollIntoView({ block: "center", behavior: "smooth" });
          var runBtn = card.querySelector(".t-run");
          if (runBtn && !runBtn.disabled) runBtn.click();
        }
      });
      row.appendChild(b);
    });
    wrap.hidden = false;
  }

  function cssEscape(s) {
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) { return "\\" + c; });
  }

  function suggestFallback(catalogue) {
    var state = catalogue.state || {};
    var pool = allTools(catalogue);
    if (!state.active_vin) {
      var pick = pool.find(function (t) { return t.id === "GET /api/live/status"; });
      return pick ? [pick.id] : [];
    }
    return pool.filter(function (t) { return t.run === "one_tap" && t.enabled; })
      .slice(0, 3).map(function (t) { return t.id; });
  }

  // ---------------------------------------------------------------------
  // tool cards

  function inputKey(toolId) { return "cuore-tools-input-" + toolId; }

  function loadSaved(toolId) {
    if (!storage) return {};
    try { return JSON.parse(storage.getItem(inputKey(toolId)) || "{}"); } catch (e) { return {}; }
  }
  function saveInputs(toolId, values) {
    if (!storage) return;
    try { storage.setItem(inputKey(toolId), JSON.stringify(values)); } catch (e) { /* ignore */ }
  }

  function buildForm(tool) {
    var saved = loadSaved(tool.id);
    var form = document.createElement("div");
    form.className = "t-form";
    tool.inputs.forEach(function (inp) {
      var field = document.createElement("div");
      field.className = "t-field";
      var label = document.createElement("label");
      label.textContent = inp.label + (inp.required ? " *" : "");
      field.appendChild(label);
      var value = saved[inp.name] != null ? saved[inp.name] : inp.default;
      if (inp.choices && inp.choices.length) {
        var row = document.createElement("div");
        row.className = "t-choice-row";
        inp.choices.forEach(function (c) {
          var btn = document.createElement("button");
          btn.type = "button"; btn.className = "t-choice-btn";
          btn.textContent = c.label; btn.dataset.value = c.value;
          if (c.value === value) btn.classList.add("on");
          btn.addEventListener("click", function () {
            row.querySelectorAll(".t-choice-btn").forEach(function (x) { x.classList.remove("on"); });
            btn.classList.add("on");
            row.dataset.value = c.value;
          });
          row.appendChild(btn);
        });
        row.dataset.value = value || "";
        row.dataset.inputName = inp.name;
        field.appendChild(row);
      } else {
        var input = document.createElement("input");
        input.type = inp.type === "number" ? "number" : "text";
        input.value = value != null ? value : "";
        input.dataset.inputName = inp.name;
        if (inp.help) input.title = inp.help;
        field.appendChild(input);
      }
      form.appendChild(field);
    });
    return form;
  }

  function collectForm(form) {
    var out = {};
    form.querySelectorAll("[data-input-name]").forEach(function (el) {
      out[el.dataset.inputName] = el.value;
    });
    form.querySelectorAll(".t-choice-row[data-input-name]").forEach(function (row) {
      out[row.dataset.inputName] = row.dataset.value;
    });
    return out;
  }

  function buildUrl(tool, values) {
    var path = tool.path;
    var query = [];
    (tool.inputs || []).forEach(function (inp) {
      var v = values[inp.name];
      if (v == null || v === "") return;
      if (inp.in === "path") path = path.replace("{" + inp.name + "}", encodeURIComponent(v));
      else if (inp.in === "query") query.push(encodeURIComponent(inp.name) + "=" + encodeURIComponent(v));
    });
    var url = path;
    if (query.length) url += (url.indexOf("?") >= 0 ? "&" : "?") + query.join("&");
    return url;
  }

  function bodyOf(tool, values) {
    var body = {};
    var any = false;
    (tool.inputs || []).forEach(function (inp) {
      if (inp.in === "body" && values[inp.name] != null && values[inp.name] !== "") {
        body[inp.name] = values[inp.name]; any = true;
      }
    });
    return any ? body : null;
  }

  function renderShapeFallback(raw) {
    return { kind: "text", title: "Result", columns: null, rows: null,
             summary: "Done -- see raw JSON below.", _raw: raw };
  }

  function renderShaped(container, shaped, raw, ok) {
    var box = document.createElement("div");
    box.className = "t-result" + (ok ? "" : " is-error");
    var head = document.createElement("div");
    head.className = "t-result-head";
    var ts = document.createElement("span");
    ts.className = "t-ts"; ts.textContent = new Date().toLocaleTimeString();
    var copyBtn = document.createElement("button");
    copyBtn.type = "button"; copyBtn.className = "t-copy"; copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", function () {
      var text = JSON.stringify(raw, null, 2);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
      } else fallbackCopy(text);
      copyBtn.textContent = "Copied";
      setTimeout(function () { copyBtn.textContent = "Copy"; }, 1200);
    });
    head.appendChild(ts); head.appendChild(copyBtn);
    box.appendChild(head);

    if (!ok) {
      var err = document.createElement("p");
      err.textContent = (raw && raw.status ? raw.status + ": " : "") +
        (raw && (raw.detail || raw.error) ? (raw.detail || raw.error) : "request failed");
      box.appendChild(err);
    } else if (shaped.kind === "kv" && shaped.rows) {
      var kv = document.createElement("div"); kv.className = "t-kv";
      shaped.rows.forEach(function (r) {
        var k = document.createElement("div"); k.className = "k"; k.textContent = r[0];
        var v = document.createElement("div"); v.textContent = r[1];
        kv.appendChild(k); kv.appendChild(v);
      });
      box.appendChild(kv);
    } else if (shaped.kind === "table" && shaped.rows) {
      box.appendChild(renderTable(shaped.columns || [], shaped.rows));
    } else if (shaped.kind === "codes" && shaped.rows) {
      var cwrap = document.createElement("div");
      shaped.rows.forEach(function (r) {
        var row = document.createElement("div"); row.className = "t-codes-row";
        var code = document.createElement("a");
        code.href = "/v/" + encodeURIComponent((raw && raw.vin) || "") + "/code/" + encodeURIComponent(r.code || "");
        code.textContent = r.code || "";
        var status = document.createElement("span"); status.textContent = r.status || "";
        row.appendChild(code); row.appendChild(status);
        cwrap.appendChild(row);
      });
      box.appendChild(cwrap);
    } else if (shaped.kind === "readiness" && shaped.rows) {
      var rwrap = document.createElement("div");
      shaped.rows.forEach(function (r) {
        var row = document.createElement("div"); row.className = "t-readiness-row";
        var name = document.createElement("span"); name.textContent = r.name || "";
        var mark = document.createElement("span");
        mark.className = r.complete ? "t-tick" : "t-cross";
        mark.textContent = r.complete ? "✓ complete" : "✗ not complete";
        row.appendChild(name); row.appendChild(mark);
        rwrap.appendChild(row);
      });
      box.appendChild(rwrap);
      if (shaped.summary) {
        var s = document.createElement("p"); s.className = "small muted"; s.textContent = shaped.summary;
        box.appendChild(s);
      }
    } else {
      var p = document.createElement("p");
      p.textContent = shaped.summary || "Done.";
      box.appendChild(p);
    }

    var raw_el = document.createElement("details"); raw_el.className = "t-raw";
    var sum = document.createElement("summary"); sum.textContent = "Raw";
    var pre = document.createElement("pre"); pre.textContent = JSON.stringify(raw, null, 2);
    raw_el.appendChild(sum); raw_el.appendChild(pre);
    box.appendChild(raw_el);

    container.insertBefore(box, container.firstChild);
  }

  function renderTable(columns, rows) {
    var wrap = document.createElement("div"); wrap.className = "tw";
    var table = document.createElement("table");
    if (columns && columns.length) {
      var thead = document.createElement("thead"); var tr = document.createElement("tr");
      columns.forEach(function (c) { var th = document.createElement("th"); th.textContent = c; tr.appendChild(th); });
      thead.appendChild(tr); table.appendChild(thead);
    }
    var tbody = document.createElement("tbody");
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      var cells = Array.isArray(r) ? r : Object.values(r);
      cells.forEach(function (c) { var td = document.createElement("td"); td.textContent = c; tr.appendChild(td); });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody); wrap.appendChild(table);
    return wrap;
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  function runTool(tool, values, resultsEl, btn) {
    var url = buildUrl(tool, values);
    var body = bodyOf(tool, values);
    var opts = { method: tool.method };
    if (body) { opts.headers = { "Content-Type": "application/json" }; opts.body = JSON.stringify(body); }
    var spinner = document.createElement("span"); spinner.className = "t-spinner";
    var label = btn.textContent;
    btn.disabled = true; btn.textContent = ""; btn.appendChild(spinner);
    btn.appendChild(document.createTextNode(" Running..."));

    return fetch(url, opts).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (raw) {
        return { ok: resp.ok, raw: raw, status: resp.status };
      });
    }).catch(function (e) {
      return { ok: false, raw: { error: "NetworkError", detail: String(e) } };
    }).then(function (result) {
      btn.disabled = false; btn.textContent = label;
      if (!result.ok) {
        renderShaped(resultsEl, null, Object.assign({ status: result.status }, result.raw), false);
        return result;
      }
      return fetch("/api/tools/shape", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_id: tool.id, payload: result.raw }),
      }).then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .catch(function () { return renderShapeFallback(result.raw); })
        .then(function (shaped) { renderShaped(resultsEl, shaped, result.raw, true); });
    });
  }

  function renderCard(tool) {
    var card = document.createElement("div");
    card.className = "t-card";
    card.dataset.toolId = tool.id;
    card.dataset.search = (tool.name + " " + tool.what + " " + (tool.synonyms || []).join(" ")).toLowerCase();

    var h = document.createElement("h3"); h.textContent = tool.name; card.appendChild(h);
    var what = document.createElement("p"); what.className = "t-what"; what.textContent = tool.what; card.appendChild(what);
    var when = document.createElement("p"); when.className = "t-when"; when.textContent = tool.when; card.appendChild(when);

    var chips = document.createElement("div"); chips.className = "t-chips";
    (tool.needs || []).forEach(function (n) {
      var c = document.createElement("span"); c.className = "t-chip"; c.textContent = "needs " + n; chips.appendChild(c);
    });
    var riskChip = document.createElement("span");
    riskChip.className = "t-chip risk-" + String(tool.risk).replace(/\s+/g, "-");
    riskChip.textContent = tool.risk; chips.appendChild(riskChip);
    card.appendChild(chips);

    if (tool.run === "not_from_here") {
      var explain = document.createElement("div"); explain.className = "t-writes-explain";
      explain.textContent = tool.disabled_reason || "Not runnable from this page.";
      if (tool.consent_phrase) {
        var cp = document.createElement("span"); cp.className = "t-consent";
        cp.textContent = '"' + tool.consent_phrase + '"';
        explain.appendChild(cp);
      }
      card.appendChild(explain);
      return card;
    }

    var form = null;
    if (tool.run === "form" && tool.inputs && tool.inputs.length) {
      form = buildForm(tool);
      card.appendChild(form);
    }

    var runBtn = document.createElement("button");
    runBtn.type = "button"; runBtn.className = "t-run"; runBtn.textContent = "Run";
    runBtn.disabled = !tool.enabled;
    card.appendChild(runBtn);

    if (!tool.enabled) {
      var reason = document.createElement("p"); reason.className = "t-disabled-reason";
      reason.textContent = tool.disabled_reason || "not available right now";
      card.appendChild(reason);
    }

    var results = document.createElement("div"); results.className = "t-results";
    card.appendChild(results);

    runBtn.addEventListener("click", function () {
      var values = form ? collectForm(form) : {};
      if (form) saveInputs(tool.id, values);
      runTool(tool, values, results, runBtn);
    });

    return card;
  }

  function renderGroups(catalogue) {
    var wrap = document.getElementById("t-groups");
    wrap.innerHTML = "";
    (catalogue.groups || []).forEach(function (g) {
      var details = document.createElement("details");
      details.className = "t-group" + (g.id === "writes" ? " t-writes" : "");
      details.dataset.groupId = g.id;
      if (g.id === "read") details.open = true;
      var summary = document.createElement("summary");
      summary.innerHTML = esc(g.title) + ' <span class="t-group-blurb">' + esc(g.blurb) + "</span>";
      details.appendChild(summary);
      var body = document.createElement("div"); body.className = "t-group-body";
      g.tools.forEach(function (t) { body.appendChild(renderCard(t)); });
      details.appendChild(body);
      wrap.appendChild(details);
    });
  }

  // ---------------------------------------------------------------------
  // search

  function wireSearch() {
    var box = document.getElementById("t-search");
    box.addEventListener("input", function () {
      var needle = box.value.trim().toLowerCase();
      document.querySelectorAll(".t-card").forEach(function (card) {
        var match = !needle || (card.dataset.search || "").indexOf(needle) !== -1;
        card.classList.toggle("t-no-match", !match);
      });
      document.querySelectorAll(".t-group").forEach(function (group) {
        var anyVisible = group.querySelectorAll(".t-card:not(.t-no-match)").length > 0;
        group.classList.toggle("t-no-match", needle !== "" && !anyVisible);
        if (needle) group.open = anyVisible;
      });
    });
  }

  // ---------------------------------------------------------------------
  // workflows

  function renderWorkflows(catalogue) {
    var wrap = document.getElementById("t-workflows");
    wrap.innerHTML = "";
    (catalogue.workflows || []).forEach(function (wf) {
      var el = document.createElement("div"); el.className = "t-wf";
      var h = document.createElement("h3"); h.textContent = wf.title; el.appendChild(h);
      var blurb = document.createElement("p"); blurb.className = "t-what"; blurb.textContent = wf.blurb; el.appendChild(blurb);
      var stepsEl = document.createElement("div"); stepsEl.className = "t-wf-steps";
      var state = wf.steps.map(function () { return "idle"; });
      wf.steps.forEach(function (s, i) {
        var row = document.createElement("div"); row.className = "t-wf-step";
        var badge = document.createElement("span"); badge.className = "t-wf-badge"; badge.textContent = "idle";
        var label = document.createElement("span"); label.textContent = s.label;
        row.appendChild(badge); row.appendChild(label);
        stepsEl.appendChild(row);
      });
      el.appendChild(stepsEl);
      var results = document.createElement("div"); results.className = "t-results"; el.appendChild(results);

      var controls = document.createElement("div"); controls.className = "t-wf-controls";
      var startBtn = document.createElement("button"); startBtn.textContent = "Start"; startBtn.className = "primary";
      var paused = { value: false };
      var running = { value: false };

      function setBadge(i, text) {
        stepsEl.children[i].querySelector(".t-wf-badge").textContent = text;
        stepsEl.children[i].querySelector(".t-wf-badge").className = "t-wf-badge " + text;
      }

      function runFrom(i) {
        if (i >= wf.steps.length) { running.value = false; return; }
        if (paused.value) { running.value = false; return; }
        var step = wf.steps[i];
        var tool = findTool(catalogue, step.tool_id);
        if (!tool) { setBadge(i, "skipped"); runFrom(i + 1); return; }
        setBadge(i, "running");
        var values = {};
        (tool.inputs || []).forEach(function (inp) { values[inp.name] = inp.default; });
        var fakeBtn = document.createElement("button"); // runTool only mutates this scratch button
        runTool(tool, values, results, fakeBtn).then(function (result) {
          var ok = result && result.ok !== false;
          setBadge(i, ok ? "ok" : "failed");
          if (!ok && step.stop_on_fail) { running.value = false; return; }
          runFrom(i + 1);
        });
      }

      startBtn.addEventListener("click", function () {
        if (running.value) return;
        running.value = true; paused.value = false;
        wf.steps.forEach(function (_, i) { setBadge(i, "idle"); });
        runFrom(0);
      });

      var pauseBtn = document.createElement("button"); pauseBtn.textContent = "Pause";
      pauseBtn.addEventListener("click", function () { paused.value = true; });

      controls.appendChild(startBtn); controls.appendChild(pauseBtn);
      el.appendChild(controls);
      wrap.appendChild(el);
    });
  }

  // ---------------------------------------------------------------------

  function init() {
    var app = document.getElementById("tools-app");
    var vin = app.dataset.vin || "";
    var fixture = readFixture();

    fetch("/api/tools/catalogue?vin=" + encodeURIComponent(vin))
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .catch(function () { return fixture; })
      .then(function (catalogue) {
        if (!catalogue) return;
        renderStatus(catalogue.state || {});
        renderWorkflows(catalogue);
        renderGroups(catalogue);
        wireSearch();

        fetch("/api/tools/suggest")
          .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
          .catch(function () { return suggestFallback(catalogue); })
          .then(function (ids) { renderSuggested(catalogue, ids); });
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
