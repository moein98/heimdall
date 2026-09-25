#!/usr/bin/env python3
"""Place the MACH3-SIMPLE-ETH board: outline, stack-up, placement, zones, rules.

Runs inside KiCad's Python (pcbnew), in the KiCad 10 container:
    python3 tools/build_pcb.py            # reads review/net.net

Four layers, 1.6 mm: F.Cu signal, In1.Cu solid ground (a "power" layer, so
the router uses it only through vias), In2.Cu signal and supply, B.Cu signal
with a ground pour. The RP2350B's 0.4 mm QFN and the W5500's 100-ohm pairs
want an unbroken ground right under them, which two layers cannot give on a
board this dense.

Floor plan, 210 x 155 mm, the same idea as A1 - every screw terminal on an
edge, with the wire going in from the edge:

    top      VFD (in its isolated corner), THC, control, limits ... 24 V in
    right    six relay terminals, relays beside them
    bottom   eight axis terminals, ENABLE, RS485
    left     RJ45, USB-C, microSD; the MPG pendant header just inside

The parts that set the layout are placed here by hand (FIXED). Everything
else goes next to what it connects to: `auto_place` puts each remaining part
at the first free spot on a spiral round the centroid of the pads it shares a
signal net with - or, for a decoupling capacitor, round the particular supply
pin it is assigned to - and never into the isolated VFD corner unless it
belongs there.
"""
import math
import os
import re
import sys

import pcbnew

FP_DIR = os.environ.get('KICAD_FOOTPRINT_DIR', '/usr/share/kicad/footprints')
NET = os.path.join('review', 'net.net')
OUT = os.path.join('hardware', 'MACH3SIMPLEETH.kicad_pcb')

W, H = 210.0, 155.0
CLEAR = 0.4                 # board edge to a connector's courtyard
MARGIN = 0.25               # courtyard to courtyard, auto-placed parts
AXES = ['X', 'Y', 'Z', 'A', 'B', 'C', 'U', 'V']
RELAYS = 'ABCDEF'

# The isolated VFD corner. Everything on the VFD side of the spindle block
# lives inside it and nothing else may: its copper is the VFD's ACM, not GND.
# The opto U702 and the DC-DC U703 straddle its edges.
SP_ZONE = (9.0, 0.3, 49.0, 50.0)          # takes in J701 on the top edge          # x1, y1, x2, y2
SP_NETS_PREFIX = 'SP_'
SP_BOARD_SIDE = {'SP_PWM_IN', 'SP_FWD_IN', 'SP_REV_IN', 'SP_AUX_IN',
                 'SP_PWM_K', 'SP_FWD_K', 'SP_REV_K', 'SP_AUX_K',
                 'SP_PWM_A', 'SP_FWD_A', 'SP_REV_A', 'SP_AUX_A'}

RAILS = {'GND', '+3V3', '+5V', 'V24', 'VIN24', '+1V1', '+3V3A', 'VBUS',
         'CHASSIS', 'SP_ACM', 'SP_12V', 'SP_5V', 'VREG_AVDD'}


def mm(v):
    return pcbnew.FromMM(v)


# ------------------------------------------------------------ netlist --

def _sexpr(text):
    toks = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack, cur = [], []
    for t in toks:
        if t == '(':
            stack.append(cur)
            cur = []
        elif t == ')':
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def _f(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x[1] if len(x) > 1 else ''
    return ''


def read_netlist():
    root = _sexpr(open(NET, encoding='utf-8').read())
    comps, nets = {}, {}
    for sec in root:
        if not isinstance(sec, list):
            continue
        if sec[0] == 'components':
            for c in sec[1:]:
                ref = _f(c, 'ref')
                dnp = any(isinstance(p, list) and p[0] == 'property'
                          and _f(p, 'name') == 'dnp' for p in c)
                sp = [x for x in c if isinstance(x, list) and x[0] == 'sheetpath']
                sheet = _f(sp[0], 'tstamps') if sp else '/'
                ts = [x for x in c if isinstance(x, list) and x[0] == 'tstamps']
                sym = ts[0][1] if ts and len(ts[0]) > 1 else ''
                comps[ref] = {'value': _f(c, 'value'), 'fp': _f(c, 'footprint'),
                              'pads': {}, 'dnp': dnp, 'path': sheet + sym}
        elif sec[0] == 'nets':
            for n in sec[1:]:
                name = _f(n, 'name').lstrip('/')
                nets[name] = []
                for nd in n:
                    if isinstance(nd, list) and nd[0] == 'node':
                        ref, pin = _f(nd, 'ref'), _f(nd, 'pin')
                        nets[name].append((ref, pin))
                        if ref in comps:
                            comps[ref]['pads'][pin] = name
    return comps, nets


# ------------------------------------------------------------- placing --

class Board:
    def __init__(self, comps):
        self.b = pcbnew.CreateEmptyBoard()
        self.b.SetCopperLayerCount(4)
        self.comps = comps
        self.fp = {}
        self.netinfo = {}
        for c in comps.values():
            for n in c['pads'].values():
                if n not in self.netinfo:
                    ni = pcbnew.NETINFO_ITEM(self.b, n)
                    self.b.Add(ni)
                    self.netinfo[n] = ni

    def load(self, ref):
        c = self.comps[ref]
        lib, name = c['fp'].split(':', 1)
        f = pcbnew.FootprintLoad('%s/%s.pretty' % (FP_DIR, lib), name)
        if f is None:
            raise SystemExit('footprint not found: %s' % c['fp'])
        f.SetReference(ref)
        f.SetValue(c['value'])
        # Library nickname and the symbol's path: without them schematic
        # parity sees every footprint as a stranger.
        f.SetFPID(pcbnew.LIB_ID(lib, name))
        f.SetPath(pcbnew.KIID_PATH(c['path']))
        if ref.startswith('H'):
            f.Reference().SetVisible(False)
        for p in f.Pads():
            n = c['pads'].get(p.GetNumber())
            if n:
                p.SetNet(self.netinfo[n])
        if c['dnp']:
            f.SetDNP(True)
        return f

    def put(self, ref, x, y, rot=0):
        f = self.fp.get(ref) or self.load(ref)
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        if ref not in self.fp:
            self.b.Add(f)
            self.fp[ref] = f
        return f

    def box(self, ref, grow=0.0):
        f = self.fp[ref]
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
        return (bb.GetLeft() / 1e6 - grow, bb.GetTop() / 1e6 - grow,
                bb.GetRight() / 1e6 + grow, bb.GetBottom() / 1e6 + grow)

    def edge(self, ref, side, along, rot):
        """Put a connector against an edge. `along` is where its courtyard
        starts along that edge (left end for top/bottom, top end for sides)."""
        self.put(ref, 0, 0, rot)
        x1, y1, x2, y2 = self.box(ref)
        if side == 'top':
            dx, dy = along - x1, CLEAR - y1
        elif side == 'bottom':
            dx, dy = along - x1, H - CLEAR - y2
        elif side == 'left':
            dx, dy = CLEAR - x1, along - y1
        else:
            dx, dy = W - CLEAR - x2, along - y1
        self.put(ref, dx, dy, rot)
        x1, y1, x2, y2 = self.box(ref)
        return x2 if side in ('top', 'bottom') else y2

    def pad_xy(self, ref, num):
        for p in self.fp[ref].Pads():
            if p.GetNumber() == num:
                return p.GetPosition().x / 1e6, p.GetPosition().y / 1e6
        return None


def overlaps(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def in_sp(box, pad=0.0):
    x1, y1, x2, y2 = SP_ZONE
    return (box[0] >= x1 + pad and box[2] <= x2 - pad
            and box[1] >= y1 + pad and box[3] <= y2 - pad)


def touches_sp(box, pad=0.0):
    x1, y1, x2, y2 = SP_ZONE
    return overlaps(box, (x1 - pad, y1 - pad, x2 + pad, y2 + pad))


def vfd_side(c):
    nets = set(c['pads'].values())
    return any(n.startswith(SP_NETS_PREFIX) and n not in SP_BOARD_SIDE for n in nets)


# Hand placement. (x, y, rot) is the footprint origin; edge connectors are
# placed by EDGE instead, against the outline.
EDGE = [
    # top edge, left to right, turned 180 so the wires enter from the edge
    ('J701', 'top', 9.0, 180),        # VFD
    ('J503', 'top', 50.0, 180),       # THC
    ('J502', 'top', 68.0, 180),       # control
    ('J501', 'top', 91.0, 180),       # limits
    ('J101', 'top', 176.0, 180),      # sensors / 24 V in
    # bottom edge
] + [('J%d' % (401 + i), 'bottom', 9.0 + 16.6 * i, 0) for i in range(8)] + [
    ('J409', 'bottom', 9.0 + 16.6 * 8, 0),       # ENABLE
    ('J801', 'bottom', 157.0, 0),                # RS485
] + [('J%d' % (611 + i), 'right', 48.0 + 16.5 * i, 90) for i in range(6)] + [
    ('J301', 'left', 52.0, 270),      # RJ45, opening to the left
    ('J201', 'left', 76.0, 270),      # USB-C
    ('J203', 'left', 90.0, 270),      # microSD
]

FIXED = {
    'H101': (4.0, 4.0, 0), 'H102': (W - 4.0, 4.0, 0),
    'H103': (4.0, H - 4.0, 0), 'H104': (W - 4.0, H - 4.0, 0),
    # MCU in the middle-left, Ethernet between it and the jack
    'U201': (62.0, 86.0, 0),
    'U202': (62.0, 102.0, 0),
    'U301': (38.0, 65.0, 0),
    # buffers above the axis terminals
    'U401': (30.0, 128.0, 90), 'U402': (75.0, 128.0, 90), 'U403': (120.0, 128.0, 90),
    # input optocouplers in a row under the input terminals
    'U501': (66.0, 26.0, 90), 'U502': (90.0, 26.0, 90),
    'U503': (114.0, 26.0, 90), 'U504': (138.0, 26.0, 90),
    # relay side
    'U601': (148.0, 96.0, 0),
    'J601': (132.0, 118.0, 0),
    # the spindle block: U702 straddles the zone's right edge (LEDs out),
    # U703 its bottom edge (outputs in)
    'U701': (60.0, 52.0, 0),
    'U702': (49.0, 29.0, 180),
    'U703': (31.0, 53.81, 180),       # pins 2|3 split at the zone's bottom edge
    # comms
    'U801': (168.0, 132.0, 0),
    'U802': (30.0, 106.0, 0),
    'J803': (8.0, 114.2, 0),
    'J802': (44.0, 118.0, 0),
    # power corner
    'U101': (166.0, 24.0, 0),
    'L101': (188.0, 26.0, 0),
    'U102': (120.0, 58.0, 0),
    'J202': (84.0, 72.0, 0),
}

# Relays in a column beside their terminals, drivers inboard.
for _i, _ch in enumerate(RELAYS):
    _y = 48.0 + 16.5 * _i
    FIXED['K%d' % (601 + _i)] = (182.0, _y + 2.2, 0)


def auto_place(bd, placed_boxes, order):
    """First free spot on a spiral round each part's target."""
    b = bd
    rail_pins = {}          # rail -> [(ref, pad xy)] of IC supply pins
    for ref, f in b.fp.items():
        if ref[0] == 'U':
            for p in f.Pads():
                n = p.GetNetname()
                if n in RAILS and n not in ('GND', 'SP_ACM'):
                    rail_pins.setdefault(n, []).append(
                        (ref, (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)))
    rail_used = {}

    def target(ref):
        c = b.comps[ref]
        pts = []
        for pin, n in c['pads'].items():
            if n in RAILS:
                continue
            for r2, p2 in NETS[n]:
                if r2 != ref and r2 in b.fp:
                    xy = b.pad_xy(r2, p2)
                    if xy:
                        pts.append(xy)
        if pts:
            return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        rails = [n for n in c['pads'].values() if n in rail_pins]
        for n in rails:
            lst = rail_pins[n]
            k = rail_used.get(n, 0)
            if lst:
                rail_used[n] = k + 1
                return lst[k % len(lst)][1]
        return None

    for ref in order:
        t = target(ref)
        if t is None:
            t = (W / 2, H / 2)
        vfd = vfd_side(b.comps[ref])
        done = False
        for r in [0.0] + [0.5 * k for k in range(1, 160)]:
            steps = max(1, int(2 * math.pi * r / 0.8))
            for s in range(steps):
                a = 2 * math.pi * s / steps
                x, y = t[0] + r * math.cos(a), t[1] + r * math.sin(a)
                for rot in (0, 90):
                    b.put(ref, round(x * 4) / 4, round(y * 4) / 4, rot)
                    bx = b.box(ref, MARGIN)
                    if bx[0] < 1 or bx[1] < 1 or bx[2] > W - 1 or bx[3] > H - 1:
                        continue
                    if vfd and not in_sp(bx, 0.5):
                        continue
                    if not vfd and touches_sp(bx, 0.8):
                        continue
                    if any(overlaps(bx, o) for o in placed_boxes):
                        continue
                    placed_boxes.append(b.box(ref, 0.0))
                    done = True
                    break
                if done:
                    break
            if done:
                break
        if not done:
            print('could not place', ref)


def outline(b):
    pts = [(0, 0), (W, 0), (W, H), (0, H)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(pts[i][0]), mm(pts[i][1])))
        s.SetEnd(pcbnew.VECTOR2I(mm(pts[(i + 1) % 4][0]), mm(pts[(i + 1) % 4][1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        b.Add(s)


def zone(b, net, layer, poly, prio=0, name=''):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    if net:
        z.SetNet(net)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in poly:
        ol.Append(mm(x), mm(y))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    if name:
        z.SetZoneName(name)
    b.Add(z)
    return z


def rules(b):
    ds = b.GetDesignSettings()
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_ViasMinDrill = mm(0.2)
    ds.m_MinClearance = mm(0.15)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleClearance = mm(0.2)
    ds.SetBoardThickness(mm(1.6))
    ns = ds.m_NetSettings
    dflt = ns.GetDefaultNetclass()
    dflt.SetClearance(mm(0.15))
    dflt.SetTrackWidth(mm(0.2))
    dflt.SetViaDiameter(mm(0.6))
    dflt.SetViaDrill(mm(0.3))

    def cls(name, width, clear, via=(0.8, 0.4), nets=()):
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(mm(width))
        nc.SetClearance(mm(clear))
        nc.SetViaDiameter(mm(via[0]))
        nc.SetViaDrill(mm(via[1]))
        ns.SetNetclass(name, nc)
        for n in nets:
            ns.SetNetclassPatternAssignment(n, name)
    # Two supply classes. The 3.3 V and 1.1 V rails end on 0.2 mm QFN pads
    # at 0.4 mm pitch (RP2350B) and 0.3 mm at 0.5 mm (W5500): Freerouting
    # does not neck a track down at a pad, so a 0.6 mm class there is a
    # clearance violation at every supply pin - 185 of them, and the first
    # route never got below 165 unrouted.
    cls('Power', 0.6, 0.2, nets=('+5V', 'VBUS', 'V24', 'VIN24', 'VIN24F',
                                  'BUCK_SW', 'SP_12V', 'SP_5V'))
    cls('Logic_Power', 0.3, 0.15, (0.6, 0.3),
        nets=('+3V3', '+3V3A', '+1V1', 'VREG_LX', 'VREG_AVDD'))
    cls('Relay', 1.0, 0.3, (0.9, 0.5), nets=['K%s_%s' % (c, t) for c in RELAYS
                                             for t in ('NO', 'COM', 'NC')]
        + ['RELC_%s' % c for c in RELAYS])
    cls('Ethernet', 0.2, 0.15, nets=('ETH_TXP', 'ETH_TXN', 'ETH_RXP', 'ETH_RXN',
                                     'ETH_TDP', 'ETH_TDN', 'ETH_RDP', 'ETH_RDN'))


def main():
    global NETS
    comps, NETS = read_netlist()
    bd = Board(comps)
    b = bd.b
    for layer, name, t in ((pcbnew.In1_Cu, 'In1.Cu', pcbnew.LT_POWER),):
        b.SetLayerType(layer, t)
    outline(b)
    rules(b)

    for ref, side, along, rot in EDGE:
        bd.edge(ref, side, along, rot)
    for ref, (x, y, rot) in FIXED.items():
        bd.put(ref, x, y, rot)
    placed = [bd.box(r) for r in bd.fp]

    rest = [r for r in comps if r not in bd.fp and not r.startswith('#')]
    # Most-connected first, so the parts everything else hangs off are down
    # before their neighbours look for a spot.
    def weight(r):
        c = comps[r]
        return -sum(1 for n in c['pads'].values() if n not in RAILS)
    rest.sort(key=lambda r: (not r.startswith('U'), weight(r), r))
    auto_place(bd, placed, rest)

    # Planes. In1: ground everywhere but the VFD corner, which is ACM.
    x1, y1, x2, y2 = SP_ZONE
    full = [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]
    sp = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    gnd, acm = bd.netinfo['GND'], bd.netinfo['SP_ACM']
    for layer in (pcbnew.In1_Cu, pcbnew.B_Cu, pcbnew.F_Cu):
        zone(b, gnd, layer, full, 0, 'GND')
        zone(b, acm, layer, sp, 2, 'ACM')
    # 1.5 mm with no copper at all round the VFD corner, on every layer:
    # four keepout strips, so ground cannot creep up to the ACM pour.
    g = 1.5
    # The bottom strip stops either side of U703, whose input pins sit in it.
    ux1, ux2 = 25.5, 32.5
    strips = [((x1 - g, y1 - g), (x2 + g, y1)),
              ((x1 - g, y2), (ux1, y2 + g)), ((ux2, y2), (x2 + g, y2 + g)),
              ((x1 - g, y1), (x1, y2)), ((x2, y1), (x2 + g, y2))]
    if y1 < 1.0:
        strips = strips[1:]          # the corner runs to the top edge
    for (a, c) in strips:
        z = pcbnew.ZONE(b)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(False)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowFootprints(False)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        ol = z.Outline()
        ol.NewOutline()
        for px, py in ((a[0], a[1]), (c[0], a[1]), (c[0], c[1]), (a[0], c[1])):
            ol.Append(mm(px), mm(py))
        z.SetZoneName('BARRIER')
        b.Add(z)

    # The barrier, pad by pad: a VFD-side pad inside the corner, any other
    # pad at least 1.5 mm clear of it. This is what proves U702 and U703 sit
    # the right way round across the edge.
    bad = []
    for ref, f in bd.fp.items():
        for p in f.Pads():
            n = p.GetNetname()
            bb = p.GetBoundingBox()
            pb = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            iso = n.startswith(SP_NETS_PREFIX) and n not in SP_BOARD_SIDE
            if iso and not in_sp(pb):
                bad.append('%s.%s %s outside the VFD corner' % (ref, p.GetNumber(), n))
            # U703's own pin pitch is its isolation (2.54 mm, rated 1 kV):
            # its input pins are as far from the corner as the module allows.
            if not iso and n and ref != 'U703' and touches_sp(pb, 1.5):
                bad.append('%s.%s %s within 1.5 mm of the VFD corner' % (ref, p.GetNumber(), n))
    print('barrier: %s' % ('clean' if not bad else '%d violations' % len(bad)))
    for x in bad[:30]:
        print('  ' + x)

    b.Save(OUT)
    # Report
    over = []
    refs = list(bd.fp)
    for i, r in enumerate(refs):
        for r2 in refs[i + 1:]:
            if overlaps(bd.box(r), bd.box(r2)):
                over.append((r, r2))
    print('placed %d footprints, %d nets; courtyard overlaps: %d'
          % (len(bd.fp), len(bd.netinfo), len(over)))
    for o in over[:40]:
        print('  overlap', o, bd.box(o[0]), bd.box(o[1]))


if __name__ == '__main__':
    main()
