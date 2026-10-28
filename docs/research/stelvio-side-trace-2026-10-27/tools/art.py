import json,sys,math
sys.path.insert(0,'tools')
from common import *
def f(v): return f"{v:.1f}"
def corner_split(P,closed,ang=50):
    n=len(P); flags=[]
    for i in range(n):
        a=P[i-1]; b=P[i]; c=P[(i+1)%n]
        if not closed and (i==0 or i==n-1): flags.append(True);continue
        v1=(b[0]-a[0],b[1]-a[1]); v2=(c[0]-b[0],c[1]-b[1])
        d=math.degrees(abs(math.atan2(v1[0]*v2[1]-v1[1]*v2[0],v1[0]*v2[0]+v1[1]*v2[1])))
        flags.append(d>ang)
    return flags
def path_from(P,closed=True,ang=50):
    """corner-aware Catmull-Rom: smooth through non-corner vertices, sharp at corners."""
    n=len(P); fl=corner_split(P,closed,ang)
    d=[f"M{f(P[0][0])},{f(P[0][1])}"]
    rng=range(n) if closed else range(n-1)
    for i in rng:
        p0=P[(i-1)%n]; p1=P[i]; p2=P[(i+1)%n]; p3=P[(i+2)%n]
        if not closed:
            p0=P[max(i-1,0)]; p3=P[min(i+2,n-1)]
        j=(i+1)%n
        if fl[i] and fl[j]: d.append(f"L{f(p2[0])},{f(p2[1])}");continue
        c1=(p1[0]+(p2[0]-p0[0])/6,p1[1]+(p2[1]-p0[1])/6) if not fl[i] else p1
        c2=(p2[0]-(p3[0]-p1[0])/6,p2[1]-(p3[1]-p1[1])/6) if not fl[j] else p2
        d.append(f"C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(p2[0])},{f(p2[1])}")
    return " ".join(d)+(" Z" if closed else "")
def photo_path(P,closed=False,ang=50):
    return path_from([T(*p) for p in P],closed,ang)
def photo_poly(P,closed=True): return photo_path(P,closed,ang=40)
