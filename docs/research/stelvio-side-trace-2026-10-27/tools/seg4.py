"""Segment car body from photo crop -> body mask -> ordered contour. Pillow only. Reads crop.png."""
import json, sys
from PIL import Image, ImageFilter, ImageDraw
c=Image.open('crop.png').convert('RGB'); W,H=c.size
hsv=c.convert('HSV'); Hh,Ss,Vv=[b.load() for b in hsv.split()]
m=Image.new('L',(W,H),0); mp=m.load()
for y in range(H):
    for x in range(W):
        h,s,v=Hh[x,y],Ss[x,y],Vv[x,y]
        green = 25<=h<=110 and s>35
        road = (s<14 and v>110)
        if not green and not road: mp[x,y]=255
m=m.filter(ImageFilter.MedianFilter(9))
# opening to detach slivers, then keep component at the door centre
m=m.filter(ImageFilter.MinFilter(15)).filter(ImageFilter.MaxFilter(15))
ImageDraw.floodfill(m,(550,380),128,thresh=0)
m=m.point(lambda v:255 if v==128 else 0)
# fill holes: flood background from corner on inverse
inv=m.point(lambda v:255-v)
ImageDraw.floodfill(inv,(2,2),128,thresh=0)
m=inv.point(lambda v:0 if v==128 else 255)
m.save('mask_body.png')
