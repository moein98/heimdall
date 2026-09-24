#!/usr/bin/env python3
"""Route the whole board with Freerouting, and bring the result back.

Run with KiCad's own Python - it needs the pcbnew module:

    D:/KiCad/bin/python.exe tools/autoroute.py export
    java -jar freerouting.jar --gui.enabled=false \\
         -de review/route/MACH3SIMPLE.dsn -do review/route/MACH3SIMPLE.ses -mp 40
    D:/KiCad/bin/python.exe tools/autoroute.py import

The routing step is left as a separate command on purpose. It is a long run of
a downloaded program, and it is better seen being started than hidden inside
a script.

This replaces tools/route.py for this board. That router was written for the
sister project's short local hops and left a quarter of the connections for a
person to finish; Freerouting takes the whole board, ground included - see
export() for why ground is routed rather than left to the pour.

When a connection is left open, look at the rules before re-running: the
same DSN routes the same way. Relay A's NC contact stayed open run after run,
and the cause was the contact class - 1.0 mm track at 0.5 mm clearance, too
wide a corridor beside the lower D-sub. At 0.3 mm it routes.

Net widths come from the netclasses in the .kicad_pro - Power at 0.6 mm,
relay contacts at 1.0 mm with 0.5 mm clearance, everything else 0.25 mm - and
KiCad writes them into the DSN, so the router honours them.
"""
import os
import sys

import pcbnew

BOARD = os.path.join('hardware', 'MACH3SIMPLE.kicad_pcb')
DSN = os.path.join('review', 'route', 'MACH3SIMPLE.dsn')
SES = os.path.join('review', 'route', 'MACH3SIMPLE.ses')


def counts(board):
    tracks = [t for t in board.GetTracks()
              if t.GetClass() in ('PCB_TRACK', 'PCB_ARC')]
    vias = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA']
    return len(tracks), len(vias)


def export():
    board = pcbnew.LoadBoard(BOARD)
    t, v = counts(board)
    if t or v:
        print('REFUSING : %s already has %d tracks and %d vias.' % (BOARD, t, v))
        print('           Export from the unrouted board: run build_pcb.py --force.')
        return 1
    os.makedirs(os.path.dirname(DSN), exist_ok=True)
    # Route ground as a net, not a plane. With the pour in place KiCad exports
    # GND as a plane on both layers, Freerouting takes that at its word, and
    # never draws a ground track - but once the signal tracks are in, the real
    # pour is cut into islands and fifteen to twenty-five ground pads end up
    # reaching nothing. Stitching vias closed some of that and could not close
    # the rest: the pads that lose their copper are the ones on fine-pitch
    # parts, boxed in by signal tracks, where there is no room for a via.
    #
    # So the pour is left out of the export - on this copy of the board only,
    # which is never saved - and every ground connection is routed like any
    # other. The pour is filled over the result afterwards and adds area; it no
    # longer has to be what makes the connection.
    for z in list(board.Zones()):
        if z.GetNetname() == 'GND':
            board.Remove(z)
    if not pcbnew.ExportSpecctraDSN(board, DSN):
        print('export failed')
        return 1
    print('exported  : %s' % DSN)
    return 0


def import_ses():
    if not os.path.exists(SES):
        print('no %s - run Freerouting first' % SES)
        return 1
    board = pcbnew.LoadBoard(BOARD)
    t, v = counts(board)
    if t or v:
        print('REFUSING : %s already has %d tracks and %d vias.' % (BOARD, t, v))
        print('           Importing on top of them would double every route.')
        return 1
    if not pcbnew.ImportSpecctraSES(board, SES):
        print('import failed')
        return 1
    # The pour has to be refilled around the new copper, or it still covers
    # the places the tracks now run and DRC reports every one as a short.
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(BOARD)
    t, v = counts(board)
    print('imported  : %d tracks, %d vias -> %s' % (t, v, BOARD))
    return 0


def _inside(poly, x, y, r, island=-1):
    """True if a disc of radius r at (x, y) lies inside a filled polygon.

    With `island`, inside that one outline of it only.
    """
    import math
    pts = [(x, y)] + [(x + r * math.cos(a * math.pi / 4),
                       y + r * math.sin(a * math.pi / 4)) for a in range(8)]
    return all(poly.Contains(pcbnew.VECTOR2I(int(px), int(py)), island)
               for px, py in pts)


def _holes(board):
    """(x, y, radius) of every hole already drilled, vias and pads alike."""
    out = []
    for t in board.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            out.append((p.x, p.y, t.GetDrillValue() / 2))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            d = pad.GetDrillSize()
            if d.x > 0:
                p = pad.GetPosition()
                out.append((p.x, p.y, max(d.x, d.y) / 2))
    return out


def _clear_of_holes(holes, x, y, drill, gap):
    """No existing hole within `gap` of a new one, edge to edge.

    Being inside the ground fill is not enough on its own. A ground via the
    router placed sits in ground copper by definition, so the fill test passes
    right on top of it, and the first stitched board put a new via 0.2 mm from
    one - a hole_to_hole violation, and two drills where one would do.
    """
    for hx, hy, hr in holes:
        if (hx - x) ** 2 + (hy - y) ** 2 < (hr + drill / 2 + gap) ** 2:
            return False
    return True


def _via(board, gnd, x, y, via_mm, drill_mm):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    try:
        v.SetWidth(pcbnew.FromMM(via_mm))
    except TypeError:
        v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(via_mm))
    v.SetDrill(pcbnew.FromMM(drill_mm))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(gnd)
    board.Add(v)


def _fills(board, zones):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    out = {}
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        polys = [z.GetFilledPolysList(layer) for z in zones
                 if z.IsOnLayer(layer)]
        out[layer] = polys[0] if polys else None
    return out


def _islands(poly):
    """[(index, area)] of every separate piece of a fill, largest first."""
    return sorted(((i, abs(poly.Outline(i).Area()))
                   for i in range(poly.OutlineCount())),
                  key=lambda t: -t[1])


def stitch(pitch_mm=8.0, via_mm=0.6, drill_mm=0.3):
    """Tie the front and back ground pours together with vias.

    Ground is routed as a net now, so every ground pad is already connected;
    this is not what makes the connection. It is what turns two poured layers
    into one ground plane, which is what the step lines' return current wants.
    It was written when ground was still left to the pour, and the island pass
    below dates from then.

    Two passes. A coarse grid ties the two main planes together all over the
    board, which is what a return current wants. Then every remaining island,
    on either layer, gets a via of its own placed where it overlaps the main
    plane of the other layer. The grid alone was tried first, at 5 mm: it
    put down 298 vias and still left 19 connections open, because a small
    island between grid points is never hit by one.

    A via goes only where its whole pad, plus a margin, lands inside ground on
    both layers, so it can only touch ground, and the fill has already kept
    its clearance from everything else.
    """
    board = pcbnew.LoadBoard(BOARD)
    gnd = board.FindNet('GND')
    zones = [z for z in board.Zones() if z.GetNetname() == 'GND']
    if not gnd or not zones:
        print('no GND pour to stitch')
        return 1
    r = pcbnew.FromMM(via_mm / 2.0 + 0.15)

    fill = _fills(board, zones)
    main = {L: _islands(fill[L])[0][0] for L in fill}
    holes = _holes(board)
    drill = pcbnew.FromMM(drill_mm)
    gap = pcbnew.FromMM(0.5)
    box = board.GetBoardEdgesBoundingBox()
    step = pcbnew.FromMM(pitch_mm)
    grid = 0
    y = box.GetTop() + step // 2
    while y < box.GetBottom():
        x = box.GetLeft() + step // 2
        while x < box.GetRight():
            if (_inside(fill[pcbnew.F_Cu], x, y, r, main[pcbnew.F_Cu])
                    and _inside(fill[pcbnew.B_Cu], x, y, r, main[pcbnew.B_Cu])
                    and _clear_of_holes(holes, x, y, drill, gap)):
                _via(board, gnd, x, y, via_mm, drill_mm)
                holes.append((x, y, drill / 2))
                grid += 1
            x += step
        y += step

    # Islands. Refill first: the grid vias have joined some of them already,
    # and an island that no longer exists needs nothing.
    fill = _fills(board, zones)
    fine = pcbnew.FromMM(0.4)
    joined = stranded = 0
    for here, there in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
        target = _islands(fill[there])[0][0]
        for idx, _area in _islands(fill[here])[1:]:
            bb = fill[here].Outline(idx).BBox()
            spot = None
            yy = bb.GetTop()
            while yy <= bb.GetBottom() and spot is None:
                xx = bb.GetLeft()
                while xx <= bb.GetRight():
                    if (_inside(fill[here], xx, yy, r, idx)
                            and _inside(fill[there], xx, yy, r, target)
                            and _clear_of_holes(holes, xx, yy, drill, gap)):
                        spot = (xx, yy)
                        break
                    xx += fine
                yy += fine
            if spot:
                _via(board, gnd, spot[0], spot[1], via_mm, drill_mm)
                holes.append((spot[0], spot[1], drill / 2))
                joined += 1
            else:
                stranded += 1
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(BOARD)
    print('stitched  : %d grid vias at %.0f mm, %d more joining islands,'
          ' %d islands with nowhere to put one'
          % (grid, pitch_mm, joined, stranded))
    return 0


def bypass(limit_mm=4.0):
    """Measure the copper from each bypass capacitor to the pin it serves.

    In the schematic every bypass capacitor is +5V to GND, and nothing there
    can tell one from another. build_pcb.py puts each against a named pin, but
    the router sees one +5V net and is free to join a capacitor to it anywhere
    - at which point it sits beside its pin and decouples something else. So
    this walks the routed +5V copper, vias included, from the capacitor's +5V
    pad to its pin, and fails if the path is longer than `limit_mm`.
    """
    import heapq
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_pcb import PIN_CAPS
    board = pcbnew.LoadBoard(BOARD)
    mm = pcbnew.ToMM
    adj = {}

    def key(p, layer):
        return (round(mm(p.x), 2), round(mm(p.y), 2), layer)

    def link(a, c, w):
        adj.setdefault(a, []).append((c, w))
        adj.setdefault(c, []).append((a, w))

    for t in board.GetTracks():
        if t.GetNetname() != '+5V':
            continue
        if t.GetClass() == 'PCB_TRACK':
            link(key(t.GetStart(), t.GetLayer()), key(t.GetEnd(), t.GetLayer()),
                 mm(t.GetLength()))
        elif t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            link(key(p, pcbnew.F_Cu), key(p, pcbnew.B_Cu), 0.0)
    pads = {(fp.GetReference(), pd.GetNumber()): pd
            for fp in board.GetFootprints() for pd in fp.Pads()}

    def on(pd):
        bb = pd.GetBoundingBox()
        return {n for n in adj
                if bb.GetLeft() <= pcbnew.FromMM(n[0]) <= bb.GetRight()
                and bb.GetTop() <= pcbnew.FromMM(n[1]) <= bb.GetBottom()}

    bad = 0
    for cap, (ic, pin, _u, _s) in sorted(PIN_CAPS.items()):
        if (cap, '1') not in pads or (ic, pin) not in pads:
            continue
        src, dst = on(pads[(cap, '1')]), on(pads[(ic, pin)])
        dist = {n: 0.0 for n in src}
        q = [(0.0, n) for n in src]
        best = None
        while q:
            d, n = heapq.heappop(q)
            if d > dist.get(n, 1e9):
                continue
            if n in dst:
                best = d
                break
            for m, w in adj.get(n, ()):
                if d + w < dist.get(m, 1e9):
                    dist[m] = d + w
                    heapq.heappush(q, (d + w, m))
        ok = best is not None and best <= limit_mm
        bad += not ok
        print('bypass    : %-4s -> %s pin %-3s %s%s'
              % (cap, ic, pin, ('%.1f mm of copper' % best) if best is not None
                 else 'no copper path', '' if ok else '   <-- too far'))
    return 1 if bad else 0


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else ''
    if what == 'bypass':
        sys.exit(bypass())
    if what == 'export':
        sys.exit(export())
    if what == 'import':
        sys.exit(import_ses())
    if what == 'stitch':
        sys.exit(stitch())
    print(__doc__)
    sys.exit(2)
