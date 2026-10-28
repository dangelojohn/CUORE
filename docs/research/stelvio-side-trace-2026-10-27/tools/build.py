import json,sys,math
sys.path.insert(0,'tools')
from common import *
ring=json.load(open('ring_photo.json'))
# 1. smooth the pixel ring (circular moving average, window 9) then transform to drawing units
n=len(ring); w=4
sm=[(sum(ring[(i+j)%n][0] for j in range(-w,w+1))/(2*w+1), sum(ring[(i+j)%n][1] for j in range(-w,w+1))/(2*w+1)) for i in range(n)]
pts=[T(x,y) for x,y in sm]
# 2. Douglas-Peucker on a closed ring (split at the two farthest points)
def dp(P,eps):
    if len(P)<3:return P
    (x1,y1),(x2,y2)=P[0],P[-1]; dx,dy=x2-x1,y2-y1; L=math.hypot(dx,dy) or 1e-9
    best,bi=-1,0
    for i in range(1,len(P)-1):
        d=abs(dy*(P[i][0]-x1)-dx*(P[i][1]-y1))/L
        if d>best:best,bi=d,i
    if best>eps: return dp(P[:bi+1],eps)[:-1]+dp(P[bi:],eps)
    return [P[0],P[-1]]
def dp_closed(P,eps):
    a=0; b=max(range(len(P)),key=lambda i:math.hypot(P[i][0]-P[a][0],P[i][1]-P[a][1]))
    A=P[a:b+1]; B=P[b:]+[P[a]]
    return dp(A,eps)[:-1]+dp(B,eps)[:-1]
EPS=float(sys.argv[1]) if len(sys.argv)>1 else 0.7
simp=dp_closed(pts,EPS)
print('ring',n,'simplified',len(simp))
json.dump(simp,open('outline_pts.json','w'))
