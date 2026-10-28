import json,sys,math
sys.path.insert(0,'tools'); sys.path.insert(0,r'C:\Users\User\mcp-servers')
from art import *
EPS=0.9
pts=json.load(open('outline_pts.json'))
import subprocess
body=path_from(pts,True,ang=50)
D=json.load(open('details.json'))
RO,RC=73.2,81.0
def clad(cx):
    a=math.radians(22); 
    x0,x1=cx-math.cos(a),cx+math.cos(a); y=WY+math.sin(a)
    r=RC; r2=RO
    p0=(cx-r*math.cos(a),WY+r*math.sin(a)); p1=(cx+r*math.cos(a),WY+r*math.sin(a))
    q1=(cx+r2*math.cos(a),WY+r2*math.sin(a)); q0=(cx-r2*math.cos(a),WY+r2*math.sin(a))
    return f"M{f(p0[0])},{f(p0[1])} A{r},{r} 0 1 1 {f(p1[0])},{f(p1[1])} L{f(q1[0])},{f(q1[1])} A{r2},{r2} 0 1 0 {f(q0[0])},{f(q0[1])} Z"
print(len(pts),'points; body path chars',len(body))
json.dump({'body':body,'clad_f':clad(AX_F),'clad_r':clad(AX_R),'D':D,'npts':len(pts)},open('art_parts.json','w'))
