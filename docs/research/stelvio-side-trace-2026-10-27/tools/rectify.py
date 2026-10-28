import sys; sys.path.insert(0,'tools')
from common import *
from PIL import Image
c=Image.open('crop.png').convert('RGB'); cp=c.load(); CW,CH=c.size
S=2; OW,OH=860*S,360*S
def invx(X):
    lo,hi=-200.0,1900.0
    for _ in range(40):
        mid=(lo+hi)/2
        if T(mid,0)[0]<X: lo=mid
        else: hi=mid
    return lo
out=Image.new('RGB',(OW,OH),(235,235,235)); op=out.load()
for i in range(OW):
    X=i/S
    x=invx(X)
    if not (0<=x<CW-1): continue
    r=_r=FW[2]+(RW[2]-FW[2])/(RW[0]-FW[0])*(x-FW[0]); yc=FW[1]+(RW[1]-FW[1])*(x-FW[0])/(RW[0]-FW[0])
    xi=int(round(x))
    for j in range(OH):
        Y=j/S
        y=yc+(Y-WY)*r/TR
        yi=int(round(y))
        if 0<=yi<CH: op[i,j]=cp[xi,yi]
out.save('rectified.png'); print('ok')
