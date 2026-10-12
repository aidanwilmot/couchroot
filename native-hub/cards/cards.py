#!/usr/bin/env python3
"""Native Hub card styles: validate JSON specs, render SVG/PNG previews, emit hub-cards.h.

  python3 cards.py validate SPEC.json...
  python3 cards.py preview OUT_DIR SPEC.json...   (SVG grid; PNG too when node+playwright exist)
  python3 cards.py header OUT.h SPEC.json...      (generated C table for hub-art.h)

Spec: a JSON list of objects
  id      exact app id (unique)            name   display name for previews
  base    "#rrggbb" card fill              ink    "#rrggbb" wordmark colour
  word    wordmark text (default: name)    weight "bold" | "regular"
  accent  "#rrggbb" optional colour for the last `split` characters of word
  split   0..3 trailing characters drawn in accent (e.g. Plex's x)
  glyph   optional "play": rounded red-free play badge left of the word (uses accent)
  shapes  up to 4 {points: [[x,y],...] (3..8, normalised 0..1), color: "#rrggbb"}
Shapes are drawn in order over the base, all inside the rounded card. Text is centred;
no shape may overlap the (generously estimated) wordmark box.
"""
import json,sys,math,subprocess,shutil
from pathlib import Path
CARD_SIZES=[(537,302),(393,221),(820,461)]  # 3-column, 4-column, single-card layouts
RADIUS=20;MAX_SHAPES=4;MAX_POINTS=8
def rgb(h):
    assert isinstance(h,str) and len(h)==7 and h[0]=='#',h;return tuple(int(h[i:i+2],16) for i in (1,3,5))
def lum(c):
    def ch(v):v/=255;return v/12.92 if v<=.03928 else ((v+.055)/1.055)**2.4
    r,g,b=map(ch,c);return .2126*r+.7152*g+.0722*b
def contrast(a,b):
    la,lb=sorted((lum(a),lum(b)),reverse=True);return (la+.05)/(lb+.05)
def inside_round(x,y,w,h):
    px,py=x*w,y*h;r=RADIUS
    if px<0 or py<0 or px>w or py>h:return False
    cx=min(max(px,r),w-r);cy=min(max(py,r),h-r);return (px-cx)**2+(py-cy)**2<=r*r+1e-6
def point_in(x,y,pts):
    inside=False;j=len(pts)-1
    for i in range(len(pts)):
        xi,yi=pts[i];xj,yj=pts[j]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/(yj-yi)+xi:inside=not inside
        j=i
    return inside
def wordmark_box(s,size=52,w=537,h=302):
    """Generous normalised wordmark box at the 3-column size, with padding."""
    word=s.get('word') or s.get('name') or '';sz=size*3//2 if len(word)<=4 else size
    tw=len(word)*sz*(.62 if s.get('weight','bold')=='bold' else .56)+(sz*5/4 if s.get('glyph')=='play' else 0)
    half=min(tw/2+18,w/2-20)/w;return .5-half,.5-(sz*.62+10)/h,.5+half,.5+(sz*.62+10)/h
def validate(specs):
    errors=[];seen=set()
    for s in specs:
        sid=s.get('id','?');e=lambda m:errors.append(f'{sid}: {m}')
        allowed={'id','name','base','ink','word','weight','accent','split','glyph','shapes','notes'}
        for k in s:
            if k not in allowed:e(f'unknown key {k}')
        if sid in seen:e('duplicate id')
        seen.add(sid)
        try:base=rgb(s['base']);ink=rgb(s['ink'])
        except Exception as x:e(f'bad colour {x}');continue
        word=s.get('word') or s.get('name') or ''
        if not word or len(word)>24:e('word must be 1..24 chars')
        if s.get('weight','bold') not in('bold','regular'):e('weight')
        if contrast(base,ink)<4.5:e(f'ink/base contrast {contrast(base,ink):.2f} < 4.5')
        split=s.get('split',0)
        if split:
            if not 0<split<=3 or split>=len(word) or 'accent' not in s:e('split needs accent and 1..3 chars')
            elif contrast(base,rgb(s['accent']))<3:e('accent/base contrast < 3')
        if s.get('glyph') not in(None,'play'):e('glyph')
        if s.get('glyph')=='play' and 'accent' not in s:e('play glyph needs accent')
        shapes=s.get('shapes',[])
        if len(shapes)>MAX_SHAPES:e(f'more than {MAX_SHAPES} shapes')
        for i,sh in enumerate(shapes):
            pts=sh.get('points',[]);c=rgb(sh['color'])
            if not 3<=len(pts)<=MAX_POINTS:e(f'shape {i}: 3..{MAX_POINTS} points')
            for x,y in pts:
                if not all(inside_round(x,y,w,h) for w,h in CARD_SIZES):e(f'shape {i}: point {x},{y} outside rounded card');break
            xs=[p[0] for p in pts];ys=[p[1] for p in pts]
            if max(xs)>.12 and min(xs)<.88 and max(ys)>.3 and min(ys)<.7 and contrast(ink,c)<3:
                e(f'shape {i} crosses the text band with ink contrast {contrast(ink,c):.2f} < 3')
            x0,y0,x1,y1=wordmark_box(s)
            if any(point_in(px,py,pts) for px in [x0+(x1-x0)*k/23 for k in range(24)] for py in [y0+(y1-y0)*k/7 for k in range(8)]):
                e(f'shape {i} overlaps the wordmark area {x0:.2f},{y0:.2f}-{x1:.2f},{y1:.2f}; keep the text area clean')
    return errors
def load(paths):
    specs=[]
    for p in paths:specs+=json.loads(Path(p).read_text())
    return specs
def svg_card(s,w,h,size):
    esc=lambda t:t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><clipPath id="c"><rect width="{w}" height="{h}" rx="{RADIUS}"/></clipPath></defs><g clip-path="url(#c)"><rect width="{w}" height="{h}" fill="{s["base"]}"/>']
    for sh in s.get('shapes',[]):
        out.append('<polygon fill="%s" points="%s"/>'%(sh['color'],' '.join(f'{x*w:.1f},{y*h:.1f}' for x,y in sh['points'])))
    word=s.get('word') or s['name'];split=s.get('split',0);fw=700 if s.get('weight','bold')=='bold' else 400
    if len(word)<=4:size=size*3//2  # same rule as wordmark() in hub-art.h
    head,tail=(word[:-split],word[-split:]) if split else (word,'')
    gx='';tw=len(word)*size*(.6 if fw==700 else .54)  # preview estimate; firmware measures real text
    if s.get('glyph')=='play':
        iw,ih=size,size*7//10;gap=size//4;gx=f'<g transform="translate({w/2-(tw+iw+gap)/2:.0f},{h/2-ih/2:.0f})"><rect width="{iw}" height="{ih}" rx="{ih/4:.0f}" fill="{s["accent"]}"/><polygon fill="#ffffff" points="{iw*.4:.0f},{ih*.25:.0f} {iw*.7:.0f},{ih*.5:.0f} {iw*.4:.0f},{ih*.75:.0f}"/></g>'
    anchor_x=w/2+((size+size//4)/2 if gx else 0)
    out.append(gx+f'<text x="{anchor_x:.0f}" y="{h/2:.0f}" dominant-baseline="central" text-anchor="middle" font-family="Samsung One, Helvetica, Arial, sans-serif" font-weight="{fw}" font-size="{size}" fill="{s["ink"]}">{esc(head)}<tspan fill="{s.get("accent","")}">{esc(tail)}</tspan></text></g></svg>')
    return ''.join(out)
def preview(out,specs):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);cols=4;W,H=537,302;gap=30
    rows=(len(specs)+cols-1)//cols
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols*(W+gap)+gap}" height="{rows*(H+70)+gap}"><rect width="100%" height="100%" fill="#111212"/>']
    for i,s in enumerate(specs):
        x=gap+(i%cols)*(W+gap);y=gap+(i//cols)*(H+70)
        parts.append(f'<g transform="translate({x},{y})">{svg_card(s,W,H,52)}</g><text x="{x}" y="{y+H+36}" font-family="Helvetica" font-size="22" fill="#a8aa9e">{s["name"]} — {s["id"]}</text>')
    parts.append('</svg>');svg=out/'cards.svg';svg.write_text(''.join(parts))
    png=out/'cards.png';node=shutil.which('node');repo=Path(__file__).resolve().parents[3]
    if node and (repo/'node_modules/playwright').exists():
        js=f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage({{viewport:{{width:{cols*(W+gap)+gap},height:{rows*(H+70)+gap}}}}});await p.setContent(require('fs').readFileSync({json.dumps(str(svg))},'utf8'));await p.screenshot({{path:{json.dumps(str(png))}}});await b.close();}})();"
        subprocess.run([node,'-e',js],cwd=repo,check=True)
    print(svg);print(png if png.exists() else '(no PNG: playwright unavailable)')
def cstr(t):return '"'+t.replace('\\','\\\\').replace('"','\\"')+'"'
def header(out,specs):
    lines=['/* Generated by native-hub/cards/cards.py from cards/<group>.json; do not edit. */',
           '/* Exact app-id styles; shapes are normalised polygons inside the rounded card. */',
           'typedef struct{unsigned char n;float p[%d][2];unsigned char rgb[3];}CardShape;'%MAX_POINTS,
           'typedef struct{const char *id,*word;unsigned char base[3],ink[3],accent[3];unsigned char bold,split,play,shapes;CardShape shape[%d];}CardStyle;'%MAX_SHAPES,
           'static const CardStyle card_styles[]={']
    for s in specs:
        sh=[]
        for x in s.get('shapes',[]):
            pts=','.join('{%.3ff,%.3ff}'%(a,b) for a,b in x['points']);sh.append('{%d,{%s},{%d,%d,%d}}'%(len(x['points']),pts,*rgb(x['color'])))
        acc=rgb(s['accent']) if 'accent' in s else (0,0,0)
        lines.append(' {%s,%s,{%d,%d,%d},{%d,%d,%d},{%d,%d,%d},%d,%d,%d,%d,{%s}},'%(cstr(s['id']),cstr(s.get('word') or s['name']),*rgb(s['base']),*rgb(s['ink']),*acc,
            s.get('weight','bold')=='bold',s.get('split',0),s.get('glyph')=='play',len(sh),','.join(sh)))
    lines+=['};','#define CARD_STYLE_COUNT ((int)(sizeof(card_styles)/sizeof(card_styles[0])))','']
    Path(out).write_text('\n'.join(lines));print(out)
if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='validate':
        errs=validate(load(sys.argv[2:]));print('\n'.join(errs) or 'ok');sys.exit(1 if errs else 0)
    specs=load(sys.argv[3:]);errs=validate(specs)
    if errs:print('\n'.join(errs));sys.exit(1)
    (preview if cmd=='preview' else header)(sys.argv[2],specs)
