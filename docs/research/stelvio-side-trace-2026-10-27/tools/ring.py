import json,sys,math
sys.path.insert(0,'tools')
from PIL import Image, ImageDraw
from common import *
m=Image.open('mask_body.png').convert('L'); W,H=m.size
# keep-region polygon (crop px): everything above the body underside; carve the arch openings
keep=[(0,0),(W,0),(W,430),(1490,430),(1486,480),(1470,520),(1430,536),(1335,546),(1255,547),
      (970,545),(350,512),(150,500),(95,470),(60,466),(34,458),(28,430),(0,430)]
k=Image.new('L',(W,H),0); ImageDraw.Draw(k).polygon(keep,fill=255)
d=ImageDraw.Draw(k)
for (cx,cy,r) in (FW,RW):
    R=1.24*r; d.ellipse([cx-R,cy-R,cx+R,cy+R],fill=0)
from PIL import ImageChops
m=ImageChops.multiply(m,k).point(lambda v:255 if v>127 else 0)
# drop anything not connected to the door centre (after carving)
ImageDraw.floodfill(m,(550,380),128,thresh=0); m=m.point(lambda v:255 if v==128 else 0)
m.save('mask_final.png')
px=m.load()
def on(x,y): return 0<=x<W and 0<=y<H and px[x,y]>0
# Moore neighbour tracing (clockwise in image coords)
start=None
for y in range(H):
    for x in range(W):
        if on(x,y): start=(x,y);break
    if start:break
nb=[(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)]
ring=[start]; cur=start; back=4  # came from the west
steps=0
while True:
    found=False
    for i in range(8):
        j=(back+1+i)%8
        nx,ny=cur[0]+nb[j][0],cur[1]+nb[j][1]
        if on(nx,ny):
            back=(j+4)%8; cur=(nx,ny); found=True;break
    if not found:break
    if cur==start and len(ring)>10: break
    ring.append(cur); steps+=1
    if steps>200000:break
print('ring px',len(ring))
json.dump(ring,open('ring_photo.json','w'))
