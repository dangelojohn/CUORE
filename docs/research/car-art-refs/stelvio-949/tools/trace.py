import cv2, numpy as np, json, os, math
S = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(S, '..', 'art_dl', 'stelvio-2017-getoutlines-converted.png')
img = cv2.imread(SRC); grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
SPLIT, BAND = 636, 540
def mask_of(x0, x1):
    g = grey[0:BAND, x0:x1]
    _, m = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return g, m
def contours_path(m, T):
    cs, h = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for c in cs:
        a = cv2.approxPolyDP(c, 0.6, True)
        if len(a) < 4 or cv2.contourArea(a) < 3: continue
        pts = [T(float(p[0][0]), float(p[0][1])) for p in a]
        parts.append('M' + ' L'.join('%.1f,%.1f' % p for p in pts) + ' Z')
    return ' '.join(parts)
def silhouette(m, T):
    d = cv2.dilate(m, np.ones((5, 5), np.uint8), iterations=2)
    ff = d.copy(); H, W = ff.shape
    pad = np.zeros((H + 2, W + 2), np.uint8)
    for sx, sy in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
        if ff[sy, sx] == 0: cv2.floodFill(ff, pad, (sx, sy), 128)
    filled = np.where(ff == 128, 0, 255).astype(np.uint8)
    cs, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    a = cv2.approxPolyDP(c, 1.0, True)
    pts = [T(float(p[0][0]), float(p[0][1])) for p in a]
    return 'M' + ' L'.join('%.1f,%.1f' % p for p in pts) + ' Z'
out = {}
# ---------- SIDE ----------
g, m = mask_of(SPLIT, grey.shape[1])
circ = cv2.HoughCircles(cv2.GaussianBlur(g, (5, 5), 1.5), cv2.HOUGH_GRADIENT, dp=1, minDist=300,
                        param1=120, param2=40, minRadius=95, maxRadius=118)
print('hough', circ)
cands = sorted(circ[0], key=lambda c: -c[0] * 0 + c[0])  # by x
# take best (first-accumulator) per half
mid = g.shape[1] / 2
fr = [c for c in circ[0] if c[0] < mid][0]; rr = [c for c in circ[0] if c[0] >= mid][0]
# refine: least-squares circle fit to ink pixels in annulus near the tyre outer edge
def refine(c):
    ys, xs = np.nonzero(m)
    d = np.hypot(xs - c[0], ys - c[1]); sel = (d > c[2] - 4) & (d < c[2] + 4)
    x, y = xs[sel].astype(float), ys[sel].astype(float)
    A = np.c_[2 * x, 2 * y, np.ones_like(x)]; b = x * x + y * y
    s = np.linalg.lstsq(A, b, rcond=None)[0]
    return (s[0], s[1], math.sqrt(s[2] + s[0] ** 2 + s[1] ** 2))
f = refine(fr); r = refine(rr)
print('hough front', fr, 'rear', rr); print('LSQ front', f, 'rear', r)
fx, fy, fR = f; rx, ry, rR = r
src = np.array([fx, fy]); dst = np.array([199, 269.]); src2 = np.array([rx, ry]); dst2 = np.array([650, 269.])
dpx = src2 - src; ddst = dst2 - dst
s = np.hypot(*ddst) / np.hypot(*dpx)
ang = math.atan2(ddst[1], ddst[0]) - math.atan2(dpx[1], dpx[0])
rot = abs(dpx[1]) > 1
if not rot: ang = 0
ca, sa = math.cos(ang), math.sin(ang)
def Ts(x, y):
    px, py = x - src[0], y - src[1]
    return (dst[0] + s * (ca * px - sa * py), dst[1] + s * (sa * px + ca * py))
ys, xs = np.nonzero(m)
nose_px = xs.min(); tail_px = xs.max()
ny = ys[xs == nose_px].mean(); ty = ys[xs == tail_px].mean()
nose = Ts(nose_px, ny)[0]; tail = Ts(tail_px, ty)[0]
bottom_y = Ts((fx), fy + fR)[1]
print('scale units/px', s, 'rot', ang, 'nose', nose, 'tail', tail, 'tyre bottom', bottom_y)
out['side'] = dict(ink=contours_path(m, Ts), silhouette=silhouette(m, Ts),
    wheel_centres_px=[[fx + SPLIT, fy], [rx + SPLIT, ry]], wheel_radius_px=[fR, rR],
    nose_x=nose, tail_x=tail, scale_px_per_unit=1 / s, scale_units_per_px=s, tyre_bottom_y=bottom_y,
    rotation_rad=ang)
# ---------- FRONT ----------
g, m = mask_of(0, SPLIT)
ys, xs = np.nonzero(m)
rows = (ys >= 250) & (ys <= 480)   # below mirrors (mirrors y~115-175), bumper/tyre height
x0, x1 = xs[rows].min(), xs[rows].max()
bottom = ys.max(); top = ys.min()
sf = 304.5 / (x1 - x0)
cx = (x0 + x1) / 2
def Tf(x, y): return (200 + sf * (x - cx), 328 + sf * (y - bottom))
roof_y = Tf(0, top)[1]
print('front span px', x0, x1, 'scale', sf, 'roof_y', roof_y, 'top px', top, 'bottom px', bottom)
out['front'] = dict(ink=contours_path(m, Tf), silhouette=silhouette(m, Tf), roof_y=roof_y,
    body_span=[Tf(x0, 0)[0], Tf(x1, 0)[0]], scale_units_per_px=sf, mirror_span=[Tf(xs.min(), 0)[0], Tf(xs.max(), 0)[0]])
json.dump(out, open(os.path.join(S, 'paths.json'), 'w'))
print('lens', {k: (len(v['ink']), len(v['silhouette'])) for k, v in out.items()})
def svg(k, w, h, guides):
    d = out[k]; gl = ''.join('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="0.4"/>' % g for g in guides)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" style="background:#fff;border:1px solid #ccc">'
            '<path d="%s" fill="#2a6fdb" fill-opacity="0.15"/><path d="%s" fill="#1b1f23" fill-rule="evenodd"/>%s</svg>'
            % (w, h, 1240 if k == 'side' else 560, d['silhouette'], d['ink'], gl))
sg = [(0, 328, 860, 328, '#e33'), (199, 0, 199, 360, '#0a0'), (650, 0, 650, 360, '#0a0'), (61, 0, 61, 360, '#e90'), (811, 0, 811, 360, '#e90')]
fg = [(0, 328, 400, 328, '#e33'), (48, 0, 48, 360, '#e90'), (352, 0, 352, 360, '#e90'), (0, 61, 400, 61, '#0a0')]
open(os.path.join(S, 'preview.html'), 'w', encoding='utf8').write(
    '<!DOCTYPE html><meta charset="utf8"><body style="font:14px sans-serif">'
    '<h3>Side 860x360</h3>' + svg('side', 860, 360, sg) + '<h3>Front 400x360</h3>' + svg('front', 400, 360, fg) + '</body>')
