#!/usr/bin/env python3
"""Native Hub card styles: validate JSON specs, render SVG/PNG previews, emit hub-cards.h.

  python3 cards.py validate SPEC.json...
  python3 cards.py preview OUT_DIR SPEC.json...   (SVG grid; PNG too when node+playwright exist)
  python3 cards.py header OUT.h SPEC.json...      (generated C table for hub-art.h)

One shared tile anatomy for every app (calm, cohesive, brand by colour not by shapes):
  1. base    deep brand-tinted rounded card
  2. glow    2-3 nested translucent ellipses of brand light rising from the bottom edge
             under the wordmark (a low horizon), clipped to the rounded card; on focus the
             outer layer is repeated in the accent so the light brightens (hub-ui.h)
  3. mark    centred wordmark on one type scale (Bold), optional accent tail or play glyph
Per-tile objects (base + glow layers + text + tail/glyph) are capped at MAX_OBJECTS.

Spec: a JSON list of objects
  id       exact app id (unique); "*default*" is the unknown-app fallback
  name     display name for previews          word    wordmark text (default: name)
  base     "#rrggbb" card fill                ink     "#rrggbb" wordmark (default: INK)
  accent   "#rrggbb" brand colour: glow, accent tail and play glyph
  glow     optional "#rrggbb" or 2-3 colours (outer..inner) overriding accent for the glow
  strength "soft" | "normal" | "strong" glow (utility tiles use soft)
  split    0..3 trailing characters of word drawn in accent (e.g. Plex's x)
  glyph    optional "play": small accent play triangle left of the word
  weight   "bold" (default) | "regular"
The validator composites glow layers over the base and checks wordmark contrast (>= 4.5:1,
tail too) and glyph contrast (>= 3:1) at every sample in the wordmark box, both at rest and
under the focus lift overlay; every polygon point must sit inside the rounded card at all sizes.
"""
import json,sys,math,subprocess,shutil
from pathlib import Path
CARD_SIZES=[(537,302),(393,221),(825,464),(820,461),(630,354)]  # 3-col, 4-col, 2-col, single, preview
RADIUS_W=20/393;MAX_POINTS=32;          # corner radius scales with card width
MAX_SHAPES=3;MAX_OBJECTS=6
INK='#f3f1ec'                       # shared warm white wordmark
LIFT_ALPHA=34                       # focus: outer glow layer repeated in accent at this alpha (hub-ui.h focus_ring)
# Glow geometry, in pixels of the 3-column reference card (16:9): one anchor for every tile.
REF_W,REF_H=537,302
# Each layer is an ellipse (cx, cy, rx, ry) in card fractions, outer..inner: a low horizon
# of light rising from the bottom edge under the wordmark, clear of the bottom corners.
GLOW_LAYERS=((0.5,1.25,0.80,0.61),(0.5,1.16,0.48,0.40),(0.5,1.10,0.26,0.20))
GLOW_ALPHA={'soft':(10,14,24),'normal':(14,24,50),'strong':(18,30,62)}
# Type scale (mirrors wordmark() in hub-art.h): size = h*TYPE_H, short words up to *BOOST,
# shrink to fit TYPE_MAXW of the card width.
TYPE_H=0.19;BOOST=1.2;SHORT_W=0.30;TYPE_MAXW=0.66;TYPE_LIFT=0.03  # wordmark sits 3% of h above centre
def rgb(h):
    assert isinstance(h,str) and len(h)==7 and h[0]=='#',h;return tuple(int(h[i:i+2],16) for i in (1,3,5))
def hexc(c):return '#%02x%02x%02x'%tuple(int(round(v)) for v in c)
def lum(c):
    def ch(v):v/=255;return v/12.92 if v<=.03928 else ((v+.055)/1.055)**2.4
    r,g,b=map(ch,c);return .2126*r+.7152*g+.0722*b
def contrast(a,b):
    la,lb=sorted((lum(a),lum(b)),reverse=True);return (la+.05)/(lb+.05)
def over(dst,src,a):return tuple(d+(s-d)*a/255 for d,s in zip(dst,src))
def inside_round(x,y,w,h):
    """Inside the rounded card as round_box() draws it, within 1px (rasterisation)."""
    px,py=x*w,y*h;r=round(w*RADIUS_W)
    if px<-1e-6 or py<-1e-6 or px>w+1e-6 or py>h+1e-6:return False
    cx=min(max(px,r),w-r);cy=min(max(py,r),h-r);return (px-cx)**2+(py-cy)**2<=(r+1)**2
def point_in(x,y,pts):
    inside=False;j=len(pts)-1
    for i in range(len(pts)):
        xi,yi=pts[i];xj,yj=pts[j]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/(yj-yi)+xi:inside=not inside
        j=i
    return inside
# --- glow geometry -------------------------------------------------------------------------
def clip_region():
    """Rounded card in normalised space using the largest normalised radius of any size, so
    it lies inside every real card (convex, counter-clockwise in screen space)."""
    rx=RADIUS_W+.001;ry=max(w*RADIUS_W/h for w,h in CARD_SIZES)+.001;pts=[]
    for cx,cy,a0 in ((1-rx,ry,-90),(1-rx,1-ry,0),(rx,1-ry,90),(rx,ry,180)):
        for k in range(7):
            a=math.radians(a0+k*15);pts.append((cx+rx*math.cos(a),cy+ry*math.sin(a)))
    return pts
def clip(poly,region):
    def side(p,a,b):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    def cross(p,q,a,b):
        s1,s2=side(p,a,b),side(q,a,b);t=s1/(s1-s2);return (p[0]+(q[0]-p[0])*t,p[1]+(q[1]-p[1])*t)
    out=poly
    for i in range(len(region)):
        a,b=region[i],region[(i+1)%len(region)];src,out=out,[]
        for j in range(len(src)):
            p,q=src[j],src[(j+1)%len(src)];ip,iq=side(p,a,b)>=0,side(q,a,b)>=0
            if ip:out.append(p)
            if ip!=iq:out.append(cross(p,q,a,b))
        if not out:break
    return out
def reduce(poly,n,keep=()):
    """Drop the least significant vertices (smallest triangle area) of a convex polygon;
    the result stays inside the original. Vertices of the card outline (keep) go last, so
    rounded corners stay flush with the base."""
    pts=list(poly)
    def kept(p):return any(abs(p[0]-k[0])<1e-6 and abs(p[1]-k[1])<1e-6 for k in keep)
    def area(i):
        a,b,c=pts[i-1],pts[i],pts[(i+1)%len(pts)]
        return abs((b[0]-a[0])*(c[1]-a[1])*REF_W*REF_H-(c[0]-a[0])*(b[1]-a[1])*REF_W*REF_H)+(1e9 if kept(b) else 0)
    while len(pts)>n:pts.pop(min(range(len(pts)),key=area))
    return pts
def glow_shapes(s):
    if 'accent' not in s and 'glow' not in s:return []
    g=s.get('glow',s.get('accent'));cols=[g]*3 if isinstance(g,str) else list(g)
    alphas=GLOW_ALPHA[s.get('strength','normal')];cols=cols[-3:];alphas=alphas[-len(cols):];layers=GLOW_LAYERS[-len(cols):]
    region=clip_region();shapes=[]
    for col,a,(cx,cy,rx,ry) in zip(cols,alphas,layers):
        ellipse=[(cx+rx*math.cos(2*math.pi*k/96),cy+ry*math.sin(2*math.pi*k/96)) for k in range(96)]
        poly=clip(ellipse,region)
        if len(poly)<3:continue
        shapes.append({'points':[(round(x,4),round(y,4)) for x,y in reduce(poly,MAX_POINTS,region)],'rgb':rgb(col),'alpha':a})
    return shapes
def shapes_of(s):return glow_shapes(s)
# --- wordmark estimate (Arial-like metrics; firmware measures real text) --------------------
def text_units(t,bold):
    u=0
    for ch in t:
        u+=.85 if ord(ch)>127 else .278 if ch in 'ilIjt ' else .82 if ch in 'MWmw' else .611 if (bold and ch in 'pbd') else (.72 if ch.isupper() else .556)
    return u
def word_layout(s,w,h):
    """Returns (size, total width, glyph width) like wordmark() in hub-art.h."""
    word=s.get('word') or s.get('name') or '';bold=s.get('weight','bold')=='bold'
    size=h*TYPE_H;glyph=s.get('glyph')=='play'
    def total(sz):return text_units(word,bold)*sz+(sz*.85 if glyph else 0)
    if total(size)<SHORT_W*w:size=min(size*BOOST,size*SHORT_W*w/total(size))
    if total(size)>TYPE_MAXW*w:size=size*TYPE_MAXW*w/total(size)
    return size,total(size)
def wordmark_box(s,w=REF_W,h=REF_H):
    size,tw=word_layout(s,w,h);half=(tw/2+8)/w;vh=(size*.62+6)/h;c=.5-TYPE_LIFT
    return .5-half,c-vh,.5+half,c+vh
def objects(s):return 1+len(shapes_of(s))+1+(1 if s.get('split') else 0)+(1 if s.get('glyph') else 0)
def composite_at(s,x,y,lift=False):
    c=rgb(s['base'])
    shapes=shapes_of(s)
    for sh in shapes:
        if point_in(x,y,sh['points']):c=over(c,sh['rgb'],sh['alpha'])
    return over(c,rgb(s['accent']),LIFT_ALPHA) if lift and shapes and point_in(x,y,shapes[0]['points']) else c
def validate(specs):
    errors=[];seen=set()
    for s in specs:
        sid=s.get('id','?');e=lambda m:errors.append(f'{sid}: {m}')
        allowed={'id','name','base','ink','word','weight','accent','glow','strength','split','glyph','notes'}
        for k in s:
            if k not in allowed:e(f'unknown key {k}')
        if sid in seen:e('duplicate id')
        seen.add(sid)
        try:
            base=rgb(s['base']);ink=rgb(s.get('ink',INK));accent=rgb(s['accent']) if 'accent' in s else None
            g=s.get('glow');[rgb(c) for c in ([g] if isinstance(g,str) else g or [])]
        except Exception as x:e(f'bad colour {x}');continue
        word=s.get('word') or s.get('name') or ''
        if not word or len(word)>24:e('word must be 1..24 chars')
        if s.get('weight','bold') not in('bold','regular'):e('weight')
        if s.get('strength','normal') not in GLOW_ALPHA:e('strength must be soft|normal|strong')
        if isinstance(g,list) and not 2<=len(g)<=3:e('glow list needs 2..3 colours')
        if lum(base)>.03:e(f'base too light for a dark-room tile (luminance {lum(base):.3f} > 0.03)')
        split=s.get('split',0)
        if split and (not 0<split<=3 or split>=len(word) or accent is None):e('split needs accent and 1..3 chars')
        if s.get('glyph') not in(None,'play'):e('glyph')
        if accent is None:e('accent (brand colour) is required: glow, focus lift, tail and glyph use it');continue
        if s.get('glyph') and split:e('use either an accent tail or a glyph, not both')
        shapes=shapes_of(s)
        if len(shapes)>MAX_SHAPES:e(f'more than {MAX_SHAPES} glow layers')
        if objects(s)>MAX_OBJECTS:e(f'{objects(s)} objects > {MAX_OBJECTS}')
        for i,sh in enumerate(shapes):
            if not 3<=len(sh['points'])<=MAX_POINTS:e(f'shape {i}: 3..{MAX_POINTS} points')
            for x,y in sh['points']:
                if not all(inside_round(x,y,w,h) for w,h in CARD_SIZES):e(f'shape {i}: point {x},{y} outside rounded card');break
        x0,y0,x1,y1=wordmark_box(s);worst=(99,None);worst_acc=(99,None)
        for lift in (False,True):
            for px in [x0+(x1-x0)*k/15 for k in range(16)]:
                for py in [y0+(y1-y0)*k/5 for k in range(6)]:
                    c=composite_at(s,px,py,lift);worst=min(worst,(contrast(ink,c),c))
                    if accent:worst_acc=min(worst_acc,(contrast(accent,c),c))
        if worst[0]<4.5:e(f'ink contrast {worst[0]:.2f} < 4.5 over {hexc(worst[1])}')
        if split and worst_acc[0]<4.5:e(f'accent tail contrast {worst_acc[0]:.2f} < 4.5 over {hexc(worst_acc[1])}')
        if s.get('glyph') and worst_acc[0]<3:e(f'glyph contrast {worst_acc[0]:.2f} < 3 over {hexc(worst_acc[1])}')
    if specs and '*default*' not in seen:errors.append('*default*: missing fallback style')
    return errors
def load(paths):
    specs=[]
    for p in paths:specs+=json.loads(Path(p).read_text())
    return specs
def svg_card(s,w,h,lift=False):
    """Preview of the same anatomy (estimated text widths; firmware measures real text)."""
    esc=lambda t:t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" rx="{w*RADIUS_W:.0f}" fill="{s["base"]}"/>']
    for sh in shapes_of(s):
        out.append('<polygon fill="%s" fill-opacity="%.3f" points="%s"/>'%(hexc(sh['rgb']),sh['alpha']/255,' '.join(f'{x*w:.1f},{y*h:.1f}' for x,y in sh['points'])))
    if lift and shapes_of(s):out.append('<polygon fill="%s" fill-opacity="%.3f" points="%s"/>'%(s['accent'],LIFT_ALPHA/255,' '.join(f'{x*w:.1f},{y*h:.1f}' for x,y in shapes_of(s)[0]['points'])))
    word=s.get('word') or s['name'];split=s.get('split',0);fw=700 if s.get('weight','bold')=='bold' else 400
    size,tw=word_layout(s,w,h);head,tail=(word[:-split],word[-split:]) if split else (word,'')
    left=w/2-tw/2;gx=''
    if s.get('glyph')=='play':
        th=size*.62;cy=h*(.5-TYPE_LIFT);gx=f'<polygon fill="{s["accent"]}" points="{left:.0f},{cy-th/2:.0f} {left+th*.86:.0f},{cy:.0f} {left:.0f},{cy+th/2:.0f}"/>';left+=size*.85
    out.append(gx+f'<text x="{left:.0f}" y="{h*(.5-TYPE_LIFT):.0f}" dominant-baseline="central" font-family="Samsung One, Helvetica, Arial, sans-serif" font-weight="{fw}" font-size="{size:.0f}" fill="{s.get("ink",INK)}">{esc(head)}<tspan fill="{s.get("accent","")}">{esc(tail)}</tspan></text></svg>')
    return ''.join(out)
def preview(out,specs):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);cols=4;W,H=393,221;gap=30
    rows=(len(specs)+cols-1)//cols
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols*(W+gap)+gap}" height="{rows*(H+60)+gap}"><rect width="100%" height="100%" fill="#111212"/>']
    for i,s in enumerate(specs):
        x=gap+(i%cols)*(W+gap);y=gap+(i//cols)*(H+60)
        parts.append(f'<g transform="translate({x},{y})">{svg_card(s,W,H)}</g><text x="{x}" y="{y+H+32}" font-family="Helvetica" font-size="20" fill="#a8aa9e">{s["name"]} — {objects(s)} objects</text>')
    parts.append('</svg>');svg=out/'cards.svg';svg.write_text(''.join(parts))
    png=out/'cards.png';node=shutil.which('node');repo=Path(__file__).resolve().parents[3]
    if node and (repo/'node_modules/playwright').exists():
        js=f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage({{viewport:{{width:{cols*(W+gap)+gap},height:{rows*(H+60)+gap}}}}});await p.setContent(require('fs').readFileSync({json.dumps(str(svg))},'utf8'));await p.screenshot({{path:{json.dumps(str(png))}}});await b.close();}})();"
        subprocess.run([node,'-e',js],cwd=repo,check=True)
    print(svg);print(png if png.exists() else '(no PNG: playwright unavailable)')
def cstr(t):return '"'+t.replace('\\','\\\\').replace('"','\\"')+'"'
def header(out,specs):
    lines=['/* Generated by native-hub/cards/cards.py from cards/<group>.json; do not edit. */',
           '/* Exact app-id styles. Shapes are translucent glow layers (straight RGBA; hub-art.h premultiplies),',
           ' * normalised polygons already clipped inside the rounded card. */',
           '#define CARD_MAX_SHAPES %d'%MAX_SHAPES,'#define CARD_MAX_POINTS %d'%MAX_POINTS,'#define CARD_MAX_OBJECTS %d'%MAX_OBJECTS,
           '#define CARD_LIFT_ALPHA %d'%LIFT_ALPHA,'#define CARD_RADIUS_W %.5ff /* corner radius = card width * this */'%RADIUS_W,
           '#define CARD_TYPE_H %.3ff'%TYPE_H,'#define CARD_TYPE_BOOST %.3ff'%BOOST,'#define CARD_TYPE_SHORT %.3ff'%SHORT_W,'#define CARD_TYPE_MAXW %.3ff'%TYPE_MAXW,'#define CARD_TYPE_LIFT %.3ff'%TYPE_LIFT,
           'typedef struct{unsigned char n;float p[CARD_MAX_POINTS][2];unsigned char rgba[4];}CardShape;',
           'typedef struct{const char *id,*word;unsigned char base[3],ink[3],accent[3];unsigned char bold,split,play,shapes;CardShape shape[CARD_MAX_SHAPES];}CardStyle;',
           'static const CardStyle card_styles[]={']
    for s in specs:
        sh=[]
        for x in shapes_of(s):
            pts=','.join('{%.4ff,%.4ff}'%(a,b) for a,b in x['points']);sh.append('{%d,{%s},{%d,%d,%d,%d}}'%(len(x['points']),pts,*x['rgb'],x['alpha']))
        acc=rgb(s['accent']) if 'accent' in s else (0,0,0)
        lines.append(' {%s,%s,{%d,%d,%d},{%d,%d,%d},{%d,%d,%d},%d,%d,%d,%d,{%s}},'%(cstr(s['id']),cstr(s.get('word') or s['name']),*rgb(s['base']),*rgb(s.get('ink',INK)),*acc,
            s.get('weight','bold')=='bold',s.get('split',0),s.get('glyph')=='play',len(sh),','.join(sh)))
    lines+=['};','#define CARD_STYLE_COUNT ((int)(sizeof(card_styles)/sizeof(card_styles[0])))','']
    Path(out).write_text('\n'.join(lines));print(out)
if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='validate':
        specs=load(sys.argv[2:]);errs=validate(specs)
        if not errs:
            for s in specs:print(f'{s["id"]:32} {objects(s)} objects')
        print('\n'.join(errs) or 'ok');sys.exit(1 if errs else 0)
    specs=load(sys.argv[3:]);errs=validate(specs)
    if errs:print('\n'.join(errs));sys.exit(1)
    (preview if cmd=='preview' else header)(sys.argv[2],specs)
