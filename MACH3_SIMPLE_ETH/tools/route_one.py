#!/usr/bin/env python3
"""Close the connections Freerouting left open, one at a time: grid A*.

    python3 tools/route_one.py            # every open connection in review/DRC.json

For each unconnected pair DRC reports (other than two islands of the same
pour, which tools/autoroute.py stitch joins with vias), it routes from the
first item to the second - the very two items DRC names, so a pad is never
"connected" to the stub of track it already sits on. A* on a 0.1 mm grid on
the three routing layers (F.Cu, In2.Cu, B.Cu; In1.Cu is the ground plane and
a via simply passes it), obstacles every pad, track and via of other nets
grown by clearance plus half the track, with a turn penalty for straight
runs and a large cost per via. A VFD-side net stays inside the VFD corner
and everything else stays out of it and its barrier.

The A1 version of this (MACH3_SIMPLE/tools/route_one.py) routed one net on
two layers from a pad to the nearest copper of its net; that is wrong on a
board with stubs everywhere, and the reason for routing between the two
items DRC gives instead. Run DRC again after it.
"""
import heapq
import json
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb as bp                      # noqa: E402

BOARD = os.path.join('hardware', 'MACH3SIMPLEETH.kicad_pcb')
DRC = os.path.join('review', 'DRC.json')
FM, TM = pcbnew.FromMM, pcbnew.ToMM
G = 0.1
CL = 0.15
VIA_D, VIA_DR = 0.6, 0.3
LAYERS = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
NX, NY = int(bp.W / G) + 1, int(bp.H / G) + 1
ANY = False
# Removed items stay referenced until the board is saved: pcbnew frees an
# item when Python drops its last reference, and the next call segfaults.
_KEEP = []
POWER = {'+5V', '+3V3', '+3V3A', 'VBUS', 'V24', '+1V1', 'SP_12V', 'SP_5V', 'GND'}


def width_for(net):
    # Narrow enough to reach a 0.4 mm pitch QFN pin between its neighbours;
    # these are short repairs, a few mm each.
    return 0.2


def item_at(board, net, x, y):
    p = pcbnew.VECTOR2I(FM(x), FM(y))
    for f in board.GetFootprints():
        for pad in f.Pads():
            if pad.GetNetname() == net and pad.HitTest(p, FM(0.05)):
                return pad
    for t in board.GetTracks():
        if t.GetNetname() == net and t.HitTest(p, FM(0.05)):
            return t
    return None


def route(board, net, a, b):
    code = board.FindNet(net).GetNetCode()
    w = width_for(net)
    grow = w / 2 + CL
    blocked = [bytearray(NX * NY) for _ in LAYERS]
    vfd = net.startswith(bp.SP_NETS_PREFIX) and net not in bp.SP_BOARD_SIDE

    def mark(li, shape, extra):
        bb = shape.BBox()
        bb.Inflate(FM(extra) + 1)
        x0, x1 = max(0, int(TM(bb.GetLeft()) / G)), min(NX - 1, int(TM(bb.GetRight()) / G) + 1)
        y0, y1 = max(0, int(TM(bb.GetTop()) / G)), min(NY - 1, int(TM(bb.GetBottom()) / G) + 1)
        d = FM(extra)
        row = blocked[li]
        for gy in range(y0, y1 + 1):
            for gx in range(x0, x1 + 1):
                i = gy * NX + gx
                if not row[i] and shape.Collide(pcbnew.VECTOR2I(FM(gx * G), FM(gy * G)), d):
                    row[i] = 1

    # Only obstacles near the two ends matter for a local repair: 25 mm.
    ax, ay = TM(a.GetPosition().x), TM(a.GetPosition().y)
    bx_, by_ = TM(b.GetPosition().x), TM(b.GetPosition().y)
    win = (min(ax, bx_) - 25, min(ay, by_) - 25, max(ax, bx_) + 25, max(ay, by_) + 25)

    def near(item):
        bb = item.GetBoundingBox()
        return not (TM(bb.GetRight()) < win[0] or TM(bb.GetLeft()) > win[2]
                    or TM(bb.GetBottom()) < win[1] or TM(bb.GetTop()) > win[3])

    for t in board.GetTracks():
        if t.GetNetCode() != code and near(t):
            for li, lay in enumerate(LAYERS):
                if t.IsOnLayer(lay):
                    mark(li, t.GetEffectiveShape(lay), grow)
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() == code or not near(p):
                continue
            for li, lay in enumerate(LAYERS):
                if p.IsOnLayer(lay):
                    mark(li, p.GetEffectiveShape(lay), grow)
            if p.GetDrillSize().x > 0:          # a hole blocks every layer
                for li in range(len(LAYERS)):
                    mark(li, p.GetEffectiveHoleShape(), grow + 0.1)
    x1, y1, x2, y2 = bp.SP_ZONE
    g = 1.6
    for gy in range(max(0, int(win[1] / G)), min(NY, int(win[3] / G) + 1)):
        for gx in range(max(0, int(win[0] / G)), min(NX, int(win[2] / G) + 1)):
            x, y = gx * G, gy * G
            edge = x < 0.8 or y < 0.8 or x > bp.W - 0.8 or y > bp.H - 0.8
            inside = x1 + 0.5 < x < x2 - 0.5 and y1 + 0.5 < y < y2 - 0.5
            near_sp = x1 - g < x < x2 + g and y1 - g < y < y2 + g
            if edge or (vfd and not inside) or (not vfd and near_sp):
                for row in blocked:
                    row[gy * NX + gx] = 1
    vr = int(math.ceil((VIA_D / 2 + CL - w / 2) / G))

    def via_ok(gx, gy):
        for dy in range(-vr, vr + 1):
            for dx in range(-vr, vr + 1):
                i = (gy + dy) * NX + gx + dx
                if i < 0 or i >= NX * NY or any(row[i] for row in blocked):
                    return False
        return True

    def cells(item):
        out = set()
        for li, lay in enumerate(LAYERS):
            if not item.IsOnLayer(lay):
                continue
            s = item.GetEffectiveShape(lay)
            bb = s.BBox()
            for gy in range(int(TM(bb.GetTop()) / G), int(TM(bb.GetBottom()) / G) + 1):
                for gx in range(int(TM(bb.GetLeft()) / G), int(TM(bb.GetRight()) / G) + 1):
                    if s.Collide(pcbnew.VECTOR2I(FM(gx * G), FM(gy * G)), 0):
                        out.add((gx, gy, li))
        return out

    start, goal = cells(a), cells(b)
    if ANY:
        # Every item of the net that is not already joined to `a`: flood
        # fill over same-net items that touch on a shared copper layer.
        items = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode() == code]
        items += [t for t in board.GetTracks() if t.GetNetCode() == code]

        def touch(p, q):
            for lay in LAYERS + (pcbnew.In1_Cu,):
                if p.IsOnLayer(lay) and q.IsOnLayer(lay):
                    if p.GetEffectiveShape(lay).Collide(q.GetEffectiveShape(lay), 0):
                        return True
            return False
        mine, todo = {id(a)}, [a]
        while todo:
            p = todo.pop()
            for q in items:
                if id(q) not in mine and touch(p, q):
                    mine.add(id(q))
                    todo.append(q)
        goal = set()
        for q in items:
            if id(q) not in mine and near(q):
                goal |= cells(q)
    for (gx, gy, li) in start | goal:
        blocked[li][gy * NX + gx] = 0
    gl = list(goal)[::max(1, len(goal) // 40)]

    def h(x, y):
        return min(abs(x - p) + abs(y - q) for p, q, _ in gl)

    dist, prev, pq = {}, {}, []
    for s in start:
        dist[s] = 0
        heapq.heappush(pq, (h(s[0], s[1]), 0, s))
    moves = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1),
             (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    end = None
    drop = net == 'GND'         # a GND pin may simply drop a via into In1
    while pq:
        f, d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        if u in goal:
            end = u
            break
        if drop and u not in start and via_ok(u[0], u[1]):
            end = u
            break
        x, y, li = u
        pu = prev.get(u)
        pd = (x - pu[0], y - pu[1]) if pu and pu[2] == li else None
        nb = [((x + dx, y + dy, li), c + (4.0 if pd and pd != (dx, dy) else 0))
              for dx, dy, c in moves]
        if via_ok(x, y):
            for lj in range(len(LAYERS)):
                if lj != li:
                    nb.append(((x, y, lj), 60))
        for v, c in nb:
            vx, vy, vl = v
            if not (0 <= vx < NX and 0 <= vy < NY) or blocked[vl][vy * NX + vx]:
                continue
            nd = d + c
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd + h(vx, vy), nd, v))
    if not end:
        return None
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    segs, vias, cur = [], [], [path[0]]
    for p, q in zip(path, path[1:]):
        if p[2] != q[2]:
            vias.append((p[0], p[1]))
            segs.append(cur)
            cur = [q]
            continue
        if len(cur) >= 2:
            d1 = (cur[-1][0] - cur[-2][0], cur[-1][1] - cur[-2][1])
            d2 = (q[0] - p[0], q[1] - p[1])
            g1 = max(abs(d1[0]), abs(d1[1])) or 1
            if (d1[0] // g1, d1[1] // g1) == d2 and d1[0] % g1 == 0 and d1[1] % g1 == 0:
                cur[-1] = q
                continue
        cur.append(q)
    segs.append(cur)
    if drop and end not in goal:
        vias.append((end[0], end[1]))
    n = 0
    for s in segs:
        for p, q in zip(s, s[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(FM(p[0] * G), FM(p[1] * G)))
            t.SetEnd(pcbnew.VECTOR2I(FM(q[0] * G), FM(q[1] * G)))
            t.SetWidth(FM(w))
            t.SetLayer(LAYERS[p[2]])
            t.SetNetCode(code)
            board.Add(t)
            t.thisown = False
            n += 1
    for x, y in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(FM(x * G), FM(y * G)))
        v.SetWidth(pcbnew.F_Cu, FM(VIA_D))
        v.SetDrill(FM(VIA_DR))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetNetCode(code)
        board.Add(v)
        v.thisown = False
    length = sum(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(path, path[1:])
                 if p[2] == q[2]) * G
    return n, len(vias), length


def cleanup(board):
    """Drop what the repairs and the autorouter left lying about: a second
    via on the spot (or within 0.5 mm) of another of its net, and vias that
    touch no track of their own net and no pad (dangling), except GND
    vias, which join the pours to the plane."""
    vias = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]
    segs = [t for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA)]
    gone, seen = 0, []
    for v in vias:
        p = v.GetPosition()
        dup = any(q.GetNetCode() == v.GetNetCode()
                  and (q.GetPosition() - p).EuclideanNorm() < pcbnew.FromMM(0.5) for q in seen)
        touching = any(s.GetNetCode() == v.GetNetCode()
                       and (s.GetStart() == p or s.GetEnd() == p) for s in segs)
        if dup or (not touching and v.GetNetname() != 'GND'):
            _KEEP.append(v)
            board.Remove(v)
            gone += 1
            continue
        seen.append(v)
    print('cleanup: %d vias removed' % gone)


def main():
    d = json.load(open(DRC))
    board = pcbnew.LoadBoard(BOARD)
    cleanup(board)
    # The VBUS repair that ran too close to J201's hole: take it up again.
    for v in d['violations']:
        if v['type'] == 'hole_clearance':
            for it in v['items']:
                if it['description'].startswith('Track'):
                    t = [t for t in board.GetTracks() if t.HitTest(pcbnew.VECTOR2I(
                        FM(it['pos']['x']), FM(it['pos']['y'])), FM(0.05))]
                    for x in t:
                        _KEEP.append(x)
                        board.Remove(x)
    done = failed = 0
    for v in d['unconnected_items']:
        its = v['items']
        if any(i['description'].startswith('Zone') for i in its):
            continue                        # pour islands: autoroute.py stitch
        net = its[0]['description'].split('[')[1].split(']')[0]
        a = item_at(board, net, its[0]['pos']['x'], its[0]['pos']['y'])
        b = item_at(board, net, its[1]['pos']['x'], its[1]['pos']['y'])
        # Start from the chip's or connector's pin: that is the isolated end.
        # Starting from the other item, a GND repair dropped its via next to
        # copper that was already on the plane and left the pin as it was.
        def is_pin(it):
            return (isinstance(it, pcbnew.PAD)
                    and it.GetParentFootprint().GetReference()[0] in 'UJ')
        if b is not None and is_pin(b) and not is_pin(a):
            a, b = b, a
        if not a or not b:
            print('  %-8s could not find both items' % net)
            failed += 1
            continue
        global ANY
        ANY = False
        r = route(board, net, a, b)
        if not r:
            ANY = True                      # any unjoined copper of the net
            r = route(board, net, a, b)
        if r:
            print('  %-8s %s -> %s: %d segments, %d vias, %.1f mm'
                  % (net, its[0]['description'][:28], its[1]['description'][:28], *r))
            done += 1
        else:
            print('  %-8s %s -> %s: NO PATH' % (net, its[0]['description'][:28], its[1]['description'][:28]))
            failed += 1
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(BOARD)
    print('routed %d, failed %d' % (done, failed))


if __name__ == '__main__':
    main()
