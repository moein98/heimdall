#!/usr/bin/env python3
"""Route MACH3-SIMPLE-ETH with Freerouting, in two passes. KiCad's Python.

    python3 tools/autoroute.py export1   # board nets, VFD corner kept out
    (freerouting on review/route/pass1.dsn -> pass1.ses)
    python3 tools/autoroute.py import1
    python3 tools/autoroute.py export2   # VFD-side nets only, fenced in
    (freerouting on review/route/pass2.dsn -> pass2.ses)
    python3 tools/autoroute.py import2   # then fills the zones
    python3 tools/autoroute.py barrier   # nothing crosses into the corner

Why two passes: the VFD corner's copper is the VFD's ACM, not GND. A single
pass lets the router take a ground or 3.3 V track straight across it -
A1's first route did exactly that, 0.22 mm from an ACM pad. So pass 1 routes
the board with the corner as a keepout and the VFD-side pads unnetted, and
pass 2 routes only the VFD side with the barrier strips blocking tracks.

In1.Cu is a plane layer (type power) carrying the GND pour; Freerouting
reaches it with vias. The outer GND pours are taken off for export - the
router would otherwise treat them as obstacles - and put back and filled
at the end.

Zones and tracks taken off the board are kept referenced in _KEEP until the
board is saved: pcbnew frees an item's memory when Python drops the last
reference to a removed item, and the next board operation then segfaults.
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb as bp                          # noqa: E402

BOARD = os.path.join('hardware', 'MACH3SIMPLEETH.kicad_pcb')
RDIR = os.path.join('review', 'route')
_KEEP = []


def vfd_net(n):
    return n.startswith(bp.SP_NETS_PREFIX) and n not in bp.SP_BOARD_SIDE


def keepout(board, rect, tracks=True, name='ROUTE_KEEPOUT'):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(True)
    z.SetDoNotAllowFootprints(False)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    ol = z.Outline()
    ol.NewOutline()
    x1, y1, x2, y2 = rect
    for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        ol.Append(bp.mm(px), bp.mm(py))
    z.SetZoneName(name)
    board.Add(z)
    return z


def strip_pours(board):
    """Take the outer-layer pours off (kept for put_back)."""
    out = []
    for z in list(board.Zones()):
        if not z.GetIsRuleArea() and z.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu):
            out.append(z)
            _KEEP.append(z)
            board.Remove(z)
    return out


def barrier_fences(board, tracks):
    for z in board.Zones():
        if z.GetIsRuleArea() and z.GetZoneName() == 'BARRIER':
            z.SetDoNotAllowTracks(tracks)


def export1():
    os.makedirs(RDIR, exist_ok=True)
    board = pcbnew.LoadBoard(BOARD)
    strip_pours(board)
    for f in board.GetFootprints():
        for p in f.Pads():
            if vfd_net(p.GetNetname()):
                p.SetNetCode(0)
    # The corner plus the 1.5 mm barrier, as two rectangles so that U703's
    # input pins (V24, GND), which sit in the barrier band, stay reachable.
    x1, y1, x2, y2 = bp.SP_ZONE
    g = 1.5
    keepout(board, (x1 - g, y1 - g, x2 + g, y2))
    keepout(board, (x1 - g, y2, 25.5, y2 + g))
    keepout(board, (32.5, y2, x2 + g, y2 + g))
    if not pcbnew.ExportSpecctraDSN(board, os.path.join(RDIR, 'pass1.dsn')):
        raise SystemExit('DSN export failed')
    print('exported pass1.dsn')


def import1():
    board = pcbnew.LoadBoard(BOARD)
    if not pcbnew.ImportSpecctraSES(board, os.path.join(RDIR, 'pass1.ses')):
        raise SystemExit('SES import failed')
    for t in board.GetTracks():
        t.SetLocked(True)
    board.Save(BOARD)
    print('imported pass 1: %d tracks/vias' % len(board.GetTracks()))


def export2():
    board = pcbnew.LoadBoard(BOARD)
    strip_pours(board)
    # Only the VFD side is left to route; fence it in.
    barrier_fences(board, True)
    if not pcbnew.ExportSpecctraDSN(board, os.path.join(RDIR, 'pass2.dsn')):
        raise SystemExit('DSN export failed')
    print('exported pass2.dsn')


def import2():
    board = pcbnew.LoadBoard(BOARD)
    before = len(board.GetTracks())
    if not pcbnew.ImportSpecctraSES(board, os.path.join(RDIR, 'pass2.ses')):
        raise SystemExit('SES import failed')
    fill(board)
    board.Save(BOARD)
    print('imported pass 2: %d -> %d tracks/vias' % (before, len(board.GetTracks())))


def fill(board):
    for t in board.GetTracks():
        t.SetLocked(False)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def cmd_fill():
    board = pcbnew.LoadBoard(BOARD)
    fill(board)
    board.Save(BOARD)
    print('filled')


def barrier():
    """No copper of a board net inside the corner (plus 1.5 mm), and no VFD
    net outside it - tracks and vias, not just pads."""
    board = pcbnew.LoadBoard(BOARD)
    x1, y1, x2, y2 = bp.SP_ZONE
    bad = []
    for t in board.GetTracks():
        n = t.GetNetname()
        bb = t.GetBoundingBox()
        box = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
        if vfd_net(n):
            if not bp.in_sp(box):
                bad.append('%s track at %.1f,%.1f outside the corner' % (n, box[0], box[1]))
        elif bp.touches_sp(box, 1.5):
            bad.append('%s track at %.1f,%.1f inside the barrier' % (n, box[0], box[1]))
    print('barrier: %s' % ('clean' if not bad else '%d violations' % len(bad)))
    for b in bad[:20]:
        print('  ' + b)
    return 1 if bad else 0


# Words printed at each screw, in pad order along the edge (left to right on
# the top and bottom, top to bottom on the right). The schematic numbers the
# top terminals right to left (TOP_PIN), so reading the netlist back, not
# this table, is what proves the words match: silk() prints the net each
# word lands on.
LEGENDS = {
    'J701': ('AVI', 'ACM', 'FWD', 'REV', 'AUX', 'DCM'),
    'J503': ('AOK', 'UP', 'DN'),
    'J502': ('EST', 'HLD', 'RUN', 'PRB'),
    'J501': ('X', 'Y', 'Z', 'A', 'B', 'C', 'U', 'V'),
    'J101': ('+24', '0V', '+24', '0V'),
    'J409': ('EN', '0V'),
    'J801': ('A', 'B', '0V'),
}
for _i, _a in enumerate(bp.AXES):
    LEGENDS['J%d' % (401 + _i)] = ('PUL', '0V', 'DIR')
for _i, _c in enumerate(bp.RELAYS):
    LEGENDS['J%d' % (611 + _i)] = ('NO', 'COM', 'NC')
TITLES = {'J701': 'VFD - ISOLATED', 'J503': 'THC', 'J502': 'CONTROL',
          'J501': 'LIMITS', 'J101': 'SENSORS    24V IN', 'J409': 'ENABLE',
          'J801': 'RS485', 'J301': 'ETHERNET', 'J201': 'USB', 'J203': 'SD',
          'J803': 'MPG PENDANT', 'J601': 'EXPANSION', 'J202': 'SWD'}
for _i, _a in enumerate(bp.AXES):
    TITLES['J%d' % (401 + _i)] = '%s AXIS' % _a
for _i, _c in enumerate(bp.RELAYS):
    TITLES['J%d' % (611 + _i)] = 'RELAY %s' % _c
SMALL = ('R_0603', 'C_0603', 'C_0805', 'C_1206', 'R_1206', 'LED_0603', 'D_SOD-123',
         'D_SMA', 'SOT-23', 'R_Array', 'L_0603', 'Fuse_1206', 'TestPoint', 'Crystal',
         'L_Murata', 'SOT-23-6', 'SW_SPST', 'SOT-89', 'CP_Elec', 'SolderJumper')


def text(board, s, x, y, rot=0, size=1.2):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pcbnew.VECTOR2I(bp.mm(x), bp.mm(y)))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(bp.mm(size), bp.mm(size)))
    t.SetTextThickness(bp.mm(size * 0.15))
    t.SetTextAngleDegrees(rot)
    board.Add(t)


def silk():
    board = pcbnew.LoadBoard(BOARD)
    for t in list(board.GetDrawings()):
        if isinstance(t, pcbnew.PCB_TEXT) and t.GetLayer() == pcbnew.F_SilkS:
            _KEEP.append(t)
            board.Remove(t)
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    for ref, f in fps.items():
        fpn = f.GetFPID().GetLibItemName().wx_str()
        if any(k in fpn for k in SMALL) or ref in LEGENDS or ref in TITLES:
            f.Reference().SetVisible(False)
        f.Value().SetVisible(False)
    for ref, words in LEGENDS.items():
        f = fps[ref]
        rot = round(f.GetOrientationDegrees()) % 360
        pads = [(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6, p.GetNetname())
                for p in f.Pads()]
        if rot in (0, 180):
            pads.sort(key=lambda q: q[0])
            inboard = -7.2 if rot == 0 else 7.2
            for (x, y, n), w in zip(pads, words):
                text(board, w, x, y + inboard, 0, 1.1)
            mx = sum(q[0] for q in pads) / len(pads)
            text(board, TITLES[ref], mx, pads[0][1] + inboard * 1.28, 0, 1.3)
        else:
            pads.sort(key=lambda q: q[1])
            for (x, y, n), w in zip(pads, words):
                text(board, w, x - 7.2, y, 90, 1.1)
            my = sum(q[1] for q in pads) / len(pads)
            text(board, TITLES[ref], pads[0][0] - 9.4, my, 90, 1.3)
        print('legend %-5s %s' % (ref, '  '.join('%s=%s' % (w, q[2]) for q, w in zip(pads, words))))
    for ref in ('J301', 'J201', 'J203'):
        bb = fps[ref].GetBoundingBox(False)
        text(board, TITLES[ref], bb.GetRight() / 1e6 + 1.5, bb.GetCenter().y / 1e6, 90, 1.3)
    for ref in ('J803', 'J601', 'J202'):
        bb = fps[ref].GetBoundingBox(False)
        text(board, TITLES[ref], bb.GetCenter().x / 1e6, bb.GetTop() / 1e6 - 1.2, 0, 1.1)
    # The isolated corner: dashed outline and a warning.
    x1, y1, x2, y2 = bp.SP_ZONE
    for (a, c) in (((x1, y2), (x2, y2)), ((x2, y1 + 11.5), (x2, y2)), ((x1, y1 + 11.5), (x1, y2))):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(bp.mm(a[0]), bp.mm(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(bp.mm(c[0]), bp.mm(c[1])))
        s.SetLayer(pcbnew.F_SilkS)
        s.SetStroke(pcbnew.STROKE_PARAMS(bp.mm(0.2), pcbnew.LINE_STYLE_DASH))
        board.Add(s)
    text(board, 'ISOLATED - VFD ACM', (x1 + x2) / 2, y2 - 1.4, 0, 1.0)
    text(board, 'MACH3-SIMPLE-ETH  ETH-0', 105.0, 78.0, 0, 1.8)
    text(board, 'RP2350B  grblHAL  8 AXES', 105.0, 81.5, 0, 1.2)
    board.Save(BOARD)
    print('silk done')


def _box(f):
    cy = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


def _seg_box(t):
    bb = t.GetBoundingBox()
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


# Parts the first placement put far from what they serve, and where they
# go instead: next to the pad they belong to.
MOVE = {'D104': ('J201', 'A4'),      # VBUS Schottky, beside the USB-C
        'C108': ('J301', 'SH'),      # chassis to GND, beside the magjack shield
        'R104': ('J301', 'SH')}


def fixup():
    """Bring a routed board up to date without routing it again from scratch."""
    comps, nets = bp.read_netlist()
    board = pcbnew.LoadBoard(BOARD)
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    # 1. mounting holes: bare now
    for ref in ('H101', 'H102', 'H103', 'H104'):
        old = fps[ref]
        pos = old.GetPosition()
        _KEEP.append(old)
        board.Remove(old)
        lib, name = comps[ref]['fp'].split(':', 1)
        f = pcbnew.FootprintLoad('%s/%s.pretty' % (bp.FP_DIR, lib), name)
        f.SetReference(ref)
        f.SetValue(comps[ref]['value'])
        f.SetFPID(pcbnew.LIB_ID(lib, name))
        board.Add(f)
        f.SetPosition(pos)
        f.Reference().SetVisible(False)
        fps[ref] = f
    # 2. symbol paths from the regenerated schematic
    for ref, f in fps.items():
        if ref in comps:
            f.SetPath(pcbnew.KIID_PATH(comps[ref]['path']))
    # 3. tracks of nets that are re-routed: CHASSIS whole, VBUS whole
    for t in list(board.GetTracks()):
        if t.GetNetname() in ('CHASSIS', 'VBUS'):
            _KEEP.append(t)
            board.Remove(t)
    # 4. move the stragglers next to their pad, first free spot on a spiral
    others = [(_box(f), f.IsFlipped()) for r, f in fps.items() if r not in MOVE]
    import math
    for ref, (to, pad) in MOVE.items():
        f = fps[ref]
        tp = [p for p in fps[to].Pads() if p.GetNumber() == pad][0].GetPosition()
        tx, ty = tp.x / 1e6, tp.y / 1e6
        done = False
        for r in [1.0 + 0.5 * k for k in range(80)]:
            for s_ in range(max(1, int(2 * math.pi * r / 0.8))):
                a = 2 * math.pi * s_ / max(1, int(2 * math.pi * r / 0.8))
                x, y = tx + r * math.cos(a), ty + r * math.sin(a)
                for rot in (0, 90):
                    f.SetOrientationDegrees(rot)
                    f.SetPosition(pcbnew.VECTOR2I(bp.mm(round(x * 4) / 4), bp.mm(round(y * 4) / 4)))
                    b = _box(f)
                    g = (b[0] - 0.25, b[1] - 0.25, b[2] + 0.25, b[3] + 0.25)
                    if g[0] < 1 or g[1] < 1 or g[2] > bp.W - 1 or g[3] > bp.H - 1:
                        continue
                    if bp.touches_sp(g, 1.6):
                        continue
                    if any(bp.overlaps(g, o) for o, back in others
                           if back == f.IsFlipped()):
                        continue
                    others.append((b, f.IsFlipped()))
                    done = True
                    break
                if done:
                    break
            if done:
                break
        print('moved %s to %.2f, %.2f' % (ref, f.GetPosition().x / 1e6, f.GetPosition().y / 1e6))
        # anything of any net now under the part, and its own old tracks, goes
        b = _box(f)
        mynets = {p.GetNetname() for p in f.Pads()}
        for t in list(board.GetTracks()):
            if bp.overlaps(_seg_box(t), b) or (t.GetNetname() in mynets
                                               and t.GetNetname() not in ('GND',)
                                               and bp.overlaps(_seg_box(t), (b[0] - 30, b[1] - 30, b[2] + 30, b[3] + 30))
                                               and False):
                _KEEP.append(t)
                board.Remove(t)
    # 5. In2 pours: ground everywhere, ACM in the corner
    x1, y1, x2, y2 = bp.SP_ZONE
    full = [(0.3, 0.3), (bp.W - 0.3, 0.3), (bp.W - 0.3, bp.H - 0.3), (0.3, bp.H - 0.3)]
    sp = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    if not any(z.GetLayer() == pcbnew.In2_Cu for z in board.Zones() if not z.GetIsRuleArea()):
        bp.zone(board, board.FindNet('GND'), pcbnew.In2_Cu, full, 0, 'GND')
        bp.zone(board, board.FindNet('SP_ACM'), pcbnew.In2_Cu, sp, 2, 'ACM')
    for t in board.GetTracks():
        t.SetLocked(True)
    board.Save(BOARD)
    print('fixup saved')


if __name__ == '__main__':
    cmd = sys.argv[1]
    sys.exit({'export1': export1, 'import1': import1, 'export2': export2,
              'import2': import2, 'barrier': barrier, 'fill': cmd_fill,
              'silk': silk, 'fixup': fixup}[cmd]() or 0)
