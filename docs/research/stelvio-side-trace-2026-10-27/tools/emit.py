import json,re
P=json.load(open('art_parts.json')); D=P['D']
def chunks(d,w=92):
    toks=re.findall(r'[MLCZ][^MLCZ]*',d); lines=[];cur=''
    for t in toks:
        if len(cur)+len(t)>w and cur: lines.append(cur);cur=''
        cur+=t
    lines.append(cur); return lines
def const(name,d):
    ls=chunks(d)
    if len(ls)==1: return f'    "{name}": "{ls[0]}",\n'
    return f'    "{name}": (\n'+"".join(f'        "{l}"\n' for l in ls)+'    ),\n'
src='_SIDE_BODY = (\n'+"".join(f'    "{l}"\n' for l in chunks(P['body']))+')\n\n'
src+='#: Detail paths traced from the same photo, same frame (drawing units).\n_SIDE_DETAIL = {\n'
for k,v in D.items(): src+=const(k,v)
src+=const('clad_f',P['clad_f'])+const('clad_r',P['clad_r'])+'}\n'
open('emit_consts.py','w',encoding='utf-8').write(src); print(len(src))
