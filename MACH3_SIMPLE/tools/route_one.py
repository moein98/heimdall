#!/usr/bin/env python3
"""Route one connection the autorouter left open: grid A* on both layers.

    D:/KiCad/bin/python.exe tools/route_one.py NET FROM_REF

Obstacles are every pad, track and via of other nets, grown by half the
track width plus 0.2 mm clearance; the board edge and the VFD side
(SP_ZONE) are out of bounds. It draws a 0.25 mm track from FROM_REF's pad
on NET to the nearest copper already on NET, with a small penalty per turn
so the result is long straight runs, and a large one per via. Used once on
A1, for C_DIR_IN: port 1 pin 16 to U2, 137 mm with six vias, which the
router's first pass could not fit past the VFD keepout. Run DRC after it.
"""
# Route one missing connection on a 2-layer board: grid A* with pcbnew shapes as obstacles.
import pcbnew, heapq, sys, math
sys.path.insert(0, 'tools')
from build_pcb import SP_ZONE
NET = sys.argv[1]
b = pcbnew.LoadBoard('hardware/MACH3SIMPLE.kicad_pcb')
FM, TM = pcbnew.FromMM, pcbnew.ToMM
G = 0.2                      # grid mm
W, CL = 0.25, 0.2            # track width, clearance
VIA_D = 0.6
BW, BH = 150.5, 137.9
NX, NY = int(BW / G) + 1, int(BH / G) + 1
L = (pcbnew.F_Cu, pcbnew.B_Cu)
blocked = [bytearray(NX * NY) for _ in L]
netcode = b.FindNet(NET).GetNetCode()
zone = pcbnew.SHAPE_POLY_SET(); zone.NewOutline()
for x, y in SP_ZONE: zone.Append(FM(x), FM(y))
def mark(li, shape, extra):
    bb = shape.BBox(); bb.Inflate(FM(extra) + 1)
    x0, x1 = max(0, int(TM(bb.GetLeft()) / G)), min(NX - 1, int(TM(bb.GetRight()) / G) + 1)
    y0, y1 = max(0, int(TM(bb.GetTop()) / G)), min(NY - 1, int(TM(bb.GetBottom()) / G) + 1)
    d = FM(extra)
    for gy in range(y0, y1 + 1):
        for gx in range(x0, x1 + 1):
            if blocked[li][gy * NX + gx]: continue
            if shape.Collide(pcbnew.VECTOR2I(FM(gx * G), FM(gy * G)), d):
                blocked[li][gy * NX + gx] = 1
items = []
for t in b.GetTracks():
    if t.GetNetCode() == netcode: continue
    for li, lay in enumerate(L):
        if t.IsOnLayer(lay): items.append((li, t.GetEffectiveShape(lay)))
for f in b.GetFootprints():
    for p in f.Pads():
        for li, lay in enumerate(L):
            if p.IsOnLayer(lay) and p.GetNetCode() != netcode:
                items.append((li, p.GetEffectiveShape(lay)))
        if p.GetDrillSize().x > 0 and p.GetNetCode() != netcode:
            pass
for li, s in items: mark(li, s, W / 2 + CL + 0.01)
# board edge and VFD zone
for gy in range(NY):
    for gx in range(NX):
        x, y = gx * G, gy * G
        if x < 0.6 or y < 0.6 or x > BW - 0.6 or y > BH - 0.6 or zone.Contains(pcbnew.VECTOR2I(FM(x), FM(y))):
            blocked[0][gy * NX + gx] = blocked[1][gy * NX + gx] = 1
# via allowed where both layers free with via radius margin: approximate by checking neighbours
vr = int(math.ceil((VIA_D / 2 - W / 2) / G))
def via_ok(gx, gy):
    for dy in range(-vr, vr + 1):
        for dx in range(-vr, vr + 1):
            i = (gy + dy) * NX + gx + dx
            if blocked[0][i] or blocked[1][i]: return False
    return True
# start/goal: pads of the net, find connected islands via existing copper
pads = [(f.GetReference(), p) for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() == netcode]
print('pads', [(r, p.GetNumber()) for r, p in pads])
src = [p for r, p in pads if r == sys.argv[2]][0]
dst_items = [p for r, p in pads if r != sys.argv[2]] + [t for t in b.GetTracks() if t.GetNetCode() == netcode]
goal = set()
for it in dst_items:
    for li, lay in enumerate(L):
        if not it.IsOnLayer(lay): continue
        s = it.GetEffectiveShape(lay); bb = s.BBox()
        for gy in range(int(TM(bb.GetTop()) / G), int(TM(bb.GetBottom()) / G) + 1):
            for gx in range(int(TM(bb.GetLeft()) / G), int(TM(bb.GetRight()) / G) + 1):
                if s.Collide(pcbnew.VECTOR2I(FM(gx * G), FM(gy * G)), 0): goal.add((gx, gy, li))
start = []
sp = src.GetPosition()
sx, sy = round(TM(sp.x) / G), round(TM(sp.y) / G)
for li in (0, 1): start.append((sx, sy, li))
for li in (0,1):
    for dy in range(-6,7):
        for dx in range(-6,7):
            blocked[li][(sy+dy)*NX+sx+dx]=0 if src.GetEffectiveShape(L[li]).Collide(pcbnew.VECTOR2I(FM((sx+dx)*G),FM((sy+dy)*G)),0) else blocked[li][(sy+dy)*NX+sx+dx]
for (gx, gy, li) in goal: blocked[li][gy * NX + gx] = 0
gl = list(goal)
def h(x, y): return min(abs(x - a) + abs(y - c) for a, c, _ in gl[::max(1, len(gl)//50)]) * 1.0
dist = {}; prev = {}; pq = []
for s in start: dist[s] = 0; heapq.heappush(pq, (h(s[0], s[1]), 0, s))
moves = [(1,0,1),(-1,0,1),(0,1,1),(0,-1,1),(1,1,1.414),(1,-1,1.414),(-1,1,1.414),(-1,-1,1.414)]
end = None
while pq:
    f, d, u = heapq.heappop(pq)
    if d > dist.get(u, 1e18): continue
    if u in goal: end = u; break
    x, y, li = u
    pu = prev.get(u)
    pd = (x - pu[0], y - pu[1]) if pu and pu[2] == li else None
    nb = [((x+dx, y+dy, li), c * (1.0 if li == 1 else 1.05) + (3.0 if pd and pd != (dx, dy) else 0))
          for dx, dy, c in moves]
    if via_ok(x, y): nb.append(((x, y, 1 - li), 30))
    for v, c in nb:
        vx, vy, vl = v
        if not (0 <= vx < NX and 0 <= vy < NY) or blocked[vl][vy * NX + vx]: continue
        nd = d + c
        if nd < dist.get(v, 1e18):
            dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd + h(vx, vy), nd, v))
if not end: print('NO PATH'); sys.exit(1)
path = [end]
while path[-1] in prev: path.append(prev[path[-1]])
path.reverse()
# simplify into segments
segs, vias = [], []
i = 0
pts = path
cur = [pts[0]]
for a, c in zip(pts, pts[1:]):
    if a[2] != c[2]:
        vias.append((a[0], a[1])); segs.append(cur); cur = [c]; continue
    if len(cur) >= 2:
        d1 = (cur[-1][0] - cur[-2][0], cur[-1][1] - cur[-2][1]); d2 = (c[0] - a[0], c[1] - a[1])
        g1 = max(abs(d1[0]), abs(d1[1])) or 1
        if (d1[0] // g1, d1[1] // g1) == d2 and d1[0] % g1 == 0 and d1[1] % g1 == 0:
            cur[-1] = c; continue
    cur.append(c)
segs.append(cur)
n = 0
for s in segs:
    for a, c in zip(s, s[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I(FM(a[0]*G), FM(a[1]*G))); t.SetEnd(pcbnew.VECTOR2I(FM(c[0]*G), FM(c[1]*G)))
        t.SetWidth(FM(W)); t.SetLayer(L[a[2]]); t.SetNetCode(netcode); b.Add(t); t.thisown = False; n += 1
for x, y in vias:
    v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(FM(x*G), FM(y*G)))
    try: v.SetWidth(FM(VIA_D))
    except TypeError: v.SetWidth(pcbnew.F_Cu, FM(VIA_D))
    v.SetDrill(FM(0.3)); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetNetCode(netcode); b.Add(v); v.thisown = False
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save('hardware/MACH3SIMPLE.kicad_pcb')
print('routed %s: %d segments, %d vias, length %.1f mm' % (NET, n, len(vias), sum(math.hypot(a[0]-c[0],a[1]-c[1]) for a,c in zip(pts,pts[1:]) if a[2]==c[2])*G))
