/* Electrical page progressive enhancement (cuore/web/templates/electrical.html).
 * Everything here is optional: the page is fully server-rendered and works
 * with this file blocked. No libraries, no network.
 *   1. Junior / expert toggle, remembered per viewer in localStorage.
 *   2. Find on car: live filter + pulse, Enter scrolls to the first card.
 *   3. Diagram pinch-zoom, drag-pan, double-tap / Reset button.
 */
(function () {
  'use strict';
  var page = document.getElementById('elec-page');
  if (!page) { return; }

  var reduced = false;
  try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { /* default motion */ }

  /* ---- 1. junior / expert ------------------------------------------- */
  var KEY = 'cuore.electrical.mode';
  function stored() { try { return window.localStorage.getItem(KEY); } catch (e) { return null; } }
  function remember(v) { try { window.localStorage.setItem(KEY, v); } catch (e) { /* storage blocked */ } }

  var modeBox = document.getElementById('elec-mode');
  function applyMode(mode) {
    page.setAttribute('data-mode', mode);
    var junior = mode === 'junior';
    var folds = page.querySelectorAll('details.elec-hint, details.elec-safety');
    for (var i = 0; i < folds.length; i++) { folds[i].open = junior; }
    if (modeBox) {
      var btns = modeBox.querySelectorAll('button[data-mode]');
      for (var j = 0; j < btns.length; j++) {
        btns[j].setAttribute('aria-pressed', btns[j].getAttribute('data-mode') === mode ? 'true' : 'false');
      }
    }
  }
  if (modeBox) {
    modeBox.hidden = false;
    modeBox.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('button[data-mode]') : null;
      if (!b) { return; }
      var m = b.getAttribute('data-mode');
      remember(m);
      applyMode(m);
    });
  }
  var saved = stored();
  applyMode(saved === 'expert' ? 'expert' : 'junior');

  /* ---- 2. find on car ------------------------------------------------ */
  var form = document.getElementById('elec-find');
  var input = document.getElementById('elec-find-input');
  var count = document.getElementById('elec-find-count');
  var nodes = page.querySelectorAll('.el-node');
  var cards = page.querySelectorAll('.elec-card');

  function runFind(q) {
    q = (q || '').trim().toLowerCase();
    var n = 0, i;
    for (i = 0; i < nodes.length; i++) {
      var hit = q !== '' && (nodes[i].getAttribute('data-search') || '').indexOf(q) !== -1;
      nodes[i].classList.toggle('el-match', hit);
      nodes[i].classList.toggle('el-fade', q !== '' && !hit);
      if (hit) { n++; }
    }
    for (i = 0; i < cards.length; i++) {
      var ch = q === '' || (cards[i].getAttribute('data-search') || '').indexOf(q) !== -1;
      cards[i].hidden = !ch;
      cards[i].classList.toggle('el-match', q !== '' && ch);
    }
    if (count) { count.textContent = q === '' ? '' : n + ' on the diagram'; }
  }
  function goFirst() {
    var first = page.querySelector('.elec-card.el-match:not([hidden])');
    if (first) {
      first.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
      if (history && history.replaceState) { history.replaceState(null, '', '#' + first.id); }
    }
  }
  if (form && input) {
    input.addEventListener('input', function () { runFind(input.value); });
    form.addEventListener('submit', function (ev) { ev.preventDefault(); runFind(input.value); goFirst(); });
    if (input.value) { runFind(input.value); }
  }

  /* ---- 3. pinch-zoom + pan ------------------------------------------- */
  var box = document.getElementById('elec-diagram');
  var view = document.getElementById('elec-zoom-view');
  var tools = document.getElementById('elec-zoom-tools');
  if (!box || !view || !window.PointerEvent) { return; }
  box.classList.add('zoomable');
  if (tools) { tools.hidden = false; }

  var scale = 1, tx = 0, ty = 0, MIN = 1, MAX = 5;
  var pts = {}, lastDist = 0, lastMid = null, lastTap = 0, moved = 0;

  function clamp() {
    var w = box.clientWidth, h = view.offsetHeight;
    scale = Math.min(MAX, Math.max(MIN, scale));
    tx = Math.min(0, Math.max(w * (1 - scale), tx));
    ty = Math.min(0, Math.max(h * (1 - scale), ty));
  }
  function paint() {
    clamp();
    view.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
    box.classList.toggle('zoomed', scale > 1.001);
  }
  function zoomAt(factor, cx, cy) {
    var ns = Math.min(MAX, Math.max(MIN, scale * factor));
    var k = ns / scale;
    tx = cx - (cx - tx) * k;
    ty = cy - (cy - ty) * k;
    scale = ns;
    paint();
  }
  function reset() { scale = 1; tx = 0; ty = 0; paint(); }
  function local(ev) {
    var r = box.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }
  function pair() {
    var ids = Object.keys(pts);
    if (ids.length < 2) { return null; }
    var a = pts[ids[0]], b = pts[ids[1]];
    return { d: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  }

  box.addEventListener('pointerdown', function (ev) {
    if (ev.target.closest && ev.target.closest('.elec-zoom-tools')) { return; }
    pts[ev.pointerId] = local(ev);
    moved = 0;
    var p = pair();
    if (p) { lastDist = p.d; lastMid = { x: p.x, y: p.y }; }
  });
  box.addEventListener('pointermove', function (ev) {
    if (!pts[ev.pointerId]) { return; }
    var prev = pts[ev.pointerId], cur = local(ev);
    pts[ev.pointerId] = cur;
    var p = pair();
    if (p || scale > 1.001) {  // capture only once a drag/pinch starts, so taps on nodes still click
      try { box.setPointerCapture(ev.pointerId); } catch (e) { /* not capturable */ }
    }
    if (p) {
      if (lastDist) { zoomAt(p.d / lastDist, p.x, p.y); }
      if (lastMid) { tx += p.x - lastMid.x; ty += p.y - lastMid.y; paint(); }
      lastDist = p.d; lastMid = { x: p.x, y: p.y };
      moved = 99;
    } else if (scale > 1.001) {
      tx += cur.x - prev.x; ty += cur.y - prev.y;
      moved += Math.abs(cur.x - prev.x) + Math.abs(cur.y - prev.y);
      paint();
    }
  });
  function up(ev) {
    var wasPinch = Object.keys(pts).length > 1;
    delete pts[ev.pointerId];
    lastDist = 0; lastMid = null;
    if (ev.type === 'pointerup' && !wasPinch && moved < 8) {
      var now = Date.now();
      if (now - lastTap < 320) {  // double tap: reset if zoomed, else zoom in there
        var l = local(ev);
        if (scale > 1.001) { reset(); } else { zoomAt(2.2, l.x, l.y); }
        lastTap = 0;
      } else { lastTap = now; }
    }
  }
  box.addEventListener('pointerup', up);
  box.addEventListener('pointercancel', up);
  window.addEventListener('resize', paint);

  if (tools) {
    tools.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('button[data-zoom]') : null;
      if (!b) { return; }
      var a = b.getAttribute('data-zoom'), cx = box.clientWidth / 2, cy = view.offsetHeight / 2;
      if (a === 'in') { zoomAt(1.5, cx, cy); } else if (a === 'out') { zoomAt(1 / 1.5, cx, cy); } else { reset(); }
    });
  }
})();
