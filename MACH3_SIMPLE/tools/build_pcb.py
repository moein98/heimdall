#!/usr/bin/env python3
"""Generate the MACH3-SIMPLE board: outline, placement, ground pour, rules.

Much plainer than the sister project's generator, because the board is plainer.
There is one ground, so there is one pour and no isolation band to police.

**The geometry is copied, not invented.** This board reproduces one already in
service, and every connector, relay and identifiable chip is placed on the
position of its counterpart on that board's assembly drawing: 150.5 x 137.9 mm,
the D-subs 62.8 mm apart, axis terminals at 16.1 mm, relays at 16.2 mm.
tools/read_ref.py measures the drawing and review/ref.json holds the result;
ANCHORS below says which part here stands for which part there.

Parts are placed in this order: ANCHORS from the drawing, then each bypass
capacitor against its own pin (PIN_CAPS) and the crystal against the MCU
(NEAR_MCU), then mounting holes and FIXED_PARTS,
and finally everything else packed into the bands in GROUPS, which keep out of
all of the above. The board is routed separately, by tools/autoroute.py.
"""
import json
import math
import os
import re
import sys
import uuid

FP_DIR = os.environ.get('KICAD_FOOTPRINT_DIR',
                        'D:/KiCad/share/kicad/footprints')
NET = os.path.join('review', 'net.net')
REF = os.path.join('review', 'ref.json')
OUT = os.path.join('hardware', 'MACH3SIMPLE.kicad_pcb')

# From the drawing. tools/read_ref.py finds the board outline in it - the
# only purple strokes on the page - and measures it in the frame the
# geometry is drawn in, which is not the frame the labels are printed in.
BOARD_W, BOARD_H = 150.5, 137.9
CLEAR = 0.4                     # board edge to a connector flange
GAP = 2.0                       # between neighbouring courtyards
EDGE_GAP = 0.5                  # between two connectors on the same edge

# Which edge each connector faces, for the silkscreen legends. Where it sits
# is not here - that comes from the drawing, through ANCHORS.
EDGES = (
    ('left',   ('J1', 'J2')),
    ('top',    ('J20', 'J30', 'J3', 'J4')),
    ('bottom', ('J40', 'J41', 'J42', 'J43', 'J44', 'J45')),
    ('right',  ('J10', 'J11', 'J12', 'J13', 'J14', 'J15', 'J50')),
)

# Every connector and relay is placed by matching the centre of its pad field
# to the centre of its counterpart's pad field on the drawing of the board in
# service. review/ref.json holds that measurement; tools/read_ref.py makes it.
#
# Matching pads, not courtyards: a terminal block's body overhangs the board
# edge by a different amount on every part, and its pads do not. Matching the
# centre rather than an edge means a footprint that is a fraction wider than
# the original sits symmetrically on the original's position instead of
# walking the whole row along.
#
# Spans chosen by hand used to set these positions, and the error compounded:
# a 2 mm floor between neighbours forced an 18 mm pitch where the board uses
# 16.1, and by the sixth relay that was 16 mm of drift.
ANCHORS = {
    'J1': ('J1', 270), 'J2': ('J2', 270),
    'J10': ('T1', 90), 'J11': ('T2', 90), 'J12': ('T3', 90),
    'J13': ('T4', 90), 'J14': ('T5', 90), 'J15': ('T6', 90),
    'J50': ('RS232', 90),
    # The six-way EMG & HOME block is drawn as a four-way beside a two-way,
    # and the four-way handwheel as two two-ways; one part here covers both.
    'J20': (('T15', 'T16'), 180),
    'J30': (('T17', 'T18'), 180),
    'J3': ('T9', 180), 'J4': ('T10', 180),
    'J40': ('T130101', 0), 'J41': ('T120101', 0), 'J42': ('T1301', 0),
    'J43': ('T1201', 0), 'J44': ('T13', 0), 'J45': ('T12', 0),
    # The relays run right to left on the drawing, and each is turned on its
    # side: its pad field there is 12.0 x 14.7 mm, which is a JQC-3FF's
    # 14.2 x 12.0 rotated.
    'K1': ('K20101', 90), 'K2': ('K10101', 90), 'K3': ('K201', 90),
    'K4': ('K101', 90), 'K5': ('K2', 90), 'K6': ('K1', 90),

    # Inside the board. These are matched by what the part does, not by what
    # it is: the board in service is through-hole where this one is surface
    # mount, and it uses six single-channel optocouplers on the inputs where
    # this one uses two four-channel parts, so a quad is anchored to the
    # middle of the four it replaces.
    'U1': ('U1701', 0),          # axis buffer, beside the terminals it feeds
    # The input pull-downs, where the board in service keeps its resistor
    # network for each buffer: R1701 beside the first, R2001 beside the second.
    # Its networks are SIP-9, 20 mm long; these are 4 x 0603 arrays, three of
    # them for twelve lines, so two share the first network's place.
    'RN1': ('R1701', 0), 'RN2': ('R1701', 0), 'RN3': ('R2001', 0),
    'U2': ('U1801', 0),
    'U21': ('U23', 0),           # the MCU: 44 pads there, a TQFP-32 here
    'U20': ('max1', 0),          # RS232 transceiver, by its own terminal
    # The programming header, on the spot the board in service keeps its own
    # 10-pin one. Turned 90 degrees: its pin rows run across the board there.
    'J60': ('P1', 90),
    'U10': (('U29', 'U28', 'U27', 'U26'), 0),
    'U11': (('U25', 'U22', 'U33', 'U32'), 0),
    # One relay driver per relay, in the row above the flyback diodes; theirs
    # are optocouplers, these are small MOSFETs.
    'Q1': ('U3701', 0), 'Q2': ('U3801', 0), 'Q3': ('U37', 0),
    'Q4': ('U38', 0), 'Q5': ('U39', 0), 'Q6': ('U34', 0),
    # Each flyback diode directly above the coil it protects.
    'D40': ('D3', 0), 'D41': ('D4', 0), 'D42': ('D5', 0),
    'D43': ('D6', 0), 'D44': ('D7', 0), 'D45': ('D8', 0),
    # The power block, under the two supply terminals.
    'D1': ('D1', 0), 'D2': ('D2', 0),
    'C1': ('C1', 0), 'C2': ('C2', 0),
    # The rail indicators are NOT anchored. On the drawing they stack into the
    # same 16 mm column as the diode and the bulk capacitor of each rail, and
    # the parts here are too big for that: an electrolytic is 9.4 x 8.5 mm
    # against two pads 4.8 mm apart there. They go in the strip below instead.
}

# A KiCad footprint rotation of 90 maps local +Y onto board +X, so a terminal
# whose wire entry is at local +Y faces right at 90, left at 270, up at 180 and
# down at 0.
EDGE_ROT = {'bottom': 0, 'right': 90, 'top': 180, 'left': 270}

# What is left after the anchors: the passives, in the bands the drawing puts
# them in. The packer keeps out of anything already placed, so these overlap
# the anchored parts on purpose - a band is where a row of resistors may go,
# not a box nothing else may enter.
GROUPS = (
    ('inputs',  (32.0, 12.0, 94.0, 42.0),
     r'^(R[13]\d|D2\d|C1\d|R4[0-3])$'),
    # A thin strip below the rail indicators: the parts in it - two fuses,
    # a shunt diode and the shell termination - have no counterpart on the
    # drawing, and the space their block occupies there is already full.
    ('power',   (96.0, 29.0, 138.0, 42.0),
     r'^(F[12]|D3|R[12]|D1[01])$'),
    # The D-sub shell termination, between the two shells it ties together.
    # It was filed under power, which put a chassis capacitor at the far end
    # of the board from the connectors whose shells it terminates.
    ('chassis', (14.0, 63.0, 30.0, 71.0),
     r'^(C3|R3)$'),
    ('switch',  (34.0, 44.0, 56.0, 76.0),
     r'^(U3|R4[4-7]|R52)$'),
    ('mcu',     (58.0, 44.0, 112.0, 78.0),
     r'^(R5[01]|D30)$'),
    ('buffers', (116.0, 56.0, 146.0, 96.0),
     r'^R5$'),
    ('relaydrv', (32.0, 80.0, 116.0, 97.0),
     r'^(D5\d|R[678]\d)$'),
    ('serial',  (116.0, 104.0, 146.0, 134.0),
     r'^C2[0-3]$'),
)


# Mounting holes, one in each corner, 4 mm in from both edges - the owner's
# board has them in the corners. The drawing does not show them at all: every
# 3.2 mm circle in it is an LED, in the rows at y = 12.7, 25.5 and 89.8, and
# none is near a corner, so the inset is the usual one for an M3 standoff
# rather than a measurement. An earlier version put the top-left hole 25 mm in,
# clear of the upper D-sub; the D-sub's courtyard starts 8.7 mm down, so the
# corner itself was free all along.
MOUNTS = ((4.0, 4.0), (146.5, 4.0), (146.5, 133.9), (4.0, 133.9))

# Nothing is placed by hand any more. Everything the drawing pins down is in
# ANCHORS, the bypass capacitors are in PIN_CAPS, and everything else is
# packed into a band. This stays as the escape hatch for a part that needs to
# go somewhere none of those cover.
FIXED_PARTS = {}


def uid():
    return str(uuid.uuid4())


def fmt(v):
    return ('%.4f' % v).rstrip('0').rstrip('.') or '0'


def span(t, st):
    d = 0
    for j in range(st, len(t)):
        if t[j] == '(':
            d += 1
        elif t[j] == ')':
            d -= 1
            if d == 0:
                return j + 1
    raise ValueError('unbalanced')


def blocks(t, tok):
    out, i = [], 0
    while True:
        i = t.find(tok, i)
        if i < 0:
            return out
        a = t.index('(', i)
        b = span(t, a)
        out.append(t[a:b])
        i = b


def read_netlist():
    s = open(NET, encoding='utf-8').read()
    comps = {}
    for b in blocks(s, '(comp\n'):
        ref = re.search(r'\(ref "([^"]+)"\)', b)
        val = re.search(r'\(value "([^"]*)"\)', b)
        fp = re.search(r'\(footprint "([^"]*)"\)', b)
        if ref:
            fields = {}
            fb = blocks(b, '(fields')
            if fb:
                for f in blocks(fb[0], '(field'):
                    fm = re.search(r'\(name "([^"]+)"\)\s*"([^"]*)"', f)
                    if fm and fm.group(1) not in ('Footprint', 'Datasheet',
                                                  'Description'):
                        fields[fm.group(1)] = fm.group(2)
            comps[ref.group(1)] = {'value': val.group(1) if val else '',
                                   'fp': fp.group(1) if fp else '',
                                   'fields': fields, 'pads': {},
                                   'dnp': bool(re.search(
                                       r'\(property\s*\(name "dnp"\)', b))}
    for b in blocks(s, '(net\n'):
        nm = re.search(r'\(name "([^"]*)"\)', b)
        if not nm:
            continue
        for nb in blocks(b, '(node'):
            r = re.search(r'\(ref "([^"]+)"\)', nb)
            p = re.search(r'\(pin "([^"]+)"\)', nb)
            if r and p and r.group(1) in comps:
                comps[r.group(1)]['pads'][p.group(1)] = nm.group(1)
    return comps


def load_footprint(fpid):
    lib, name = fpid.split(':', 1)
    with open('%s/%s.pretty/%s.kicad_mod' % (FP_DIR, lib, name),
              encoding='utf-8') as f:
        return f.read()


_BOX = {}


def footprint_box(fpid):
    """(x1, y1, x2, y2) of the courtyard, falling back to pad extents."""
    if fpid in _BOX:
        return _BOX[fpid]
    body = load_footprint(fpid)
    xs, ys = [], []
    for m in re.finditer(r'\(fp_(?:rect|poly|line|circle)', body):
        blk = body[m.start():span(body, m.start())]
        if 'CrtYd' not in blk:
            continue
        # A circle is written as its centre and one point on its edge. Taking
        # those two as corners gave a mounting hole a courtyard of (0, 0) to
        # (3.45, 0) - a line, not a 6.9 mm disc - and the packer, keeping out
        # of that, would have laid parts straight across the hole.
        if blk.startswith('(fp_circle'):
            ce = re.search(r'\(center\s+(-?[\d.]+)\s+(-?[\d.]+)', blk)
            en = re.search(r'\(end\s+(-?[\d.]+)\s+(-?[\d.]+)', blk)
            if ce and en:
                cx, cy = float(ce.group(1)), float(ce.group(2))
                r = math.hypot(float(en.group(1)) - cx, float(en.group(2)) - cy)
                xs += [cx - r, cx + r]
                ys += [cy - r, cy + r]
                continue
        for c in re.finditer(
                r'\((?:start|end|center|xy)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)', blk):
            xs.append(float(c.group(1)))
            ys.append(float(c.group(2)))
    if not xs:
        for m in re.finditer(r'\(pad "', body):
            blk = body[m.start():span(body, m.start())]
            at = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', blk)
            sz = re.search(r'\(size\s+([\d.]+)\s+([\d.]+)\s*\)', blk)
            if at and sz:
                x, y = float(at.group(1)), float(at.group(2))
                w, h = float(sz.group(1)) / 2, float(sz.group(2)) / 2
                xs += [x - w, x + w]
                ys += [y - h, y + h]
    if not xs:
        xs, ys = [-2.0, 2.0], [-2.0, 2.0]
    _BOX[fpid] = (min(xs), min(ys), max(xs), max(ys))
    return _BOX[fpid]


_PADBOX = {}


def pad_box(fpid):
    """(x1, y1, x2, y2) of the pads alone, in the footprint's own frame.

    The courtyard is no use for matching against the drawing. A terminal
    block's courtyard includes the body, which overhangs the board edge by a
    different amount on every part; its pads do not. The drawing gives pad
    positions, so pads are what the two boards are lined up on.
    """
    if fpid in _PADBOX:
        return _PADBOX[fpid]
    body = load_footprint(fpid)
    xs, ys = [], []
    for m in re.finditer(r'\(pad "', body):
        blk = body[m.start():span(body, m.start())]
        at = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', blk)
        if at:
            xs.append(float(at.group(1)))
            ys.append(float(at.group(2)))
    box = ((min(xs), min(ys), max(xs), max(ys)) if xs
           else footprint_box(fpid))
    _PADBOX[fpid] = box
    return box


def rot_box(box, rot):
    """Courtyard after rotating by `rot`. Board space has Y down."""
    x1, y1, x2, y2 = box
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    pts = [(x * ca + y * sa, -x * sa + y * ca)
           for x in (x1, x2) for y in (y1, y2)]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def edge_datum(fpid):
    """Local +Y of a D-sub's panel flange, or None for everything else.

    A horizontal D-sub is placed by its flange, not its courtyard: the shell has
    to hang off the board to meet an enclosure cut-out, which puts several
    millimetres of courtyard outside the outline on purpose.
    """
    body = load_footprint(fpid)
    rects = []
    for m in re.finditer(r'\(fp_rect', body):
        blk = body[m.start():span(body, m.start())]
        if 'F.Fab' not in blk:
            continue
        c = re.findall(r'\((?:start|end)\s+(-?[\d.]+)\s+(-?[\d.]+)', blk)
        if len(c) == 2:
            (x1, y1), (x2, y2) = [(float(a), float(b)) for a, b in c]
            rects.append((abs(x2 - x1), max(y1, y2)))
    if len(rects) < 3:
        return None
    widest = max(r[0] for r in rects)
    full = [r for r in rects if r[0] >= 0.9 * widest]
    return None if len(full) == len(rects) else max(r[1] for r in full)


PROP = ('\n\t\t(property "%s" "%s"\n\t\t\t(at 0 0 %s)\n\t\t\t(layer "F.Fab")'
        '\n\t\t\t(hide yes)\n\t\t\t(uuid "%s")'
        '\n\t\t\t(effects (font (size 0.8 0.8) (thickness 0.15))))')


def footprint_instance(fpid, ref, value, x, y, pads, rot=0, fields=None,
                       hide_ref=False,
                       nets=None, ref_at=None, dnp=False):
    body = load_footprint(fpid)
    for tok in ('\n\t(version', '\n\t(generator_version', '\n\t(generator'):
        i = body.find(tok)
        if i >= 0:
            body = body[:i] + body[span(body, body.index('(', i)):]
    while True:
        m = re.search(r'\(property "(?!Reference|Value|Footprint|Datasheet|'
                      r'Description)[^"]*"', body)
        if not m:
            break
        ls = body.rfind('\n', 0, m.start())
        body = body[:ls] + body[span(body, m.start()):]
    for nm in ('Reference', 'Value'):
        i = body.find('(property "%s"' % nm)
        if i >= 0:
            ls = body.rfind('\n', 0, i)
            body = body[:ls] + body[span(body, i):]
    inner = body[body.index('(layer "F.Cu")') + len('(layer "F.Cu")'):
                 body.rstrip().rfind(')')]
    if dnp:
        # Do Not Populate, as the schematic says - or the parity check
        # reports the difference, and the placement file lists the part.
        inner = re.sub(r'\(attr ([^)]*)\)', r'(attr \1 dnp)', inner, count=1)

    out, last = [], 0
    for a, b in [(m.start(), span(inner, m.start()))
                 for m in re.finditer(r'\(pad "', inner)]:
        pb = inner[a:b]
        num = re.match(r'\(pad "([^"]*)"', pb).group(1)
        if rot:
            am = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\s*\)', pb)
            if am:
                pa = (float(am.group(3) or 0) + rot) % 360
                pb = (pb[:am.start()] + '(at %s %s %s)'
                      % (am.group(1), am.group(2), fmt(pa)) + pb[am.end():])
        net = pads.get(num)
        if net and '(net ' not in pb:
            lm = re.search(r'\n(\t+)\(layers[^\n]*\)', pb)
            if lm:
                pb = (pb[:lm.end()] + '\n%s(net %d "%s")'
                      % (lm.group(1), (nets or {}).get(net, 0), net)
                      + pb[lm.end():])
        out.append(inner[last:a])
        out.append(pb)
        last = b
    out.append(inner[last:])
    inner = ''.join(out)

    # The reference used to sit at a fixed (0, -3), which is inside the body
    # of anything larger than a 1206: every terminal block and both D-subs
    # printed their designator across their own outline. Putting it just
    # clear of the courtyard costs nothing. The connectors that already
    # carry a legend from LABELS hide it altogether - the legend is what
    # anyone wiring the board actually reads, and two lots of text in the
    # same place is worse than one.
    rx, ry = 0.0, footprint_box(fpid)[1] - 0.9
    if ref_at:
        # REF_AT is in board directions; the field is stored in the
        # footprint's own frame, which turns with it.
        a = math.radians(rot)
        rx = ref_at[0] * math.cos(a) - ref_at[1] * math.sin(a)
        ry = ref_at[0] * math.sin(a) + ref_at[1] * math.cos(a)
    props = (
        '\n\t\t(property "Reference" "%s"\n\t\t\t(at %s %s %s)'
        '\n\t\t\t(layer "F.SilkS")\n\t\t\t(uuid "%s")%s'
        '\n\t\t\t(effects (font (size 0.8 0.8) (thickness 0.15))))'
        '\n\t\t(property "Value" "%s"\n\t\t\t(at 0 3 %s)\n\t\t\t(layer "F.Fab")'
        '\n\t\t\t(hide yes)\n\t\t\t(uuid "%s")'
        '\n\t\t\t(effects (font (size 0.8 0.8) (thickness 0.15))))'
        % (ref, fmt(rx), fmt(ry), fmt(rot), uid(),
           '\n\t\t\t(hide yes)' if hide_ref else '',
           value.replace('"', "'"), fmt(rot), uid()))
    for k, v in sorted((fields or {}).items()):
        props += PROP % (k, v.replace('"', "'"), fmt(rot), uid())
    return ('\t(footprint "%s"\n\t\t(layer "F.Cu")\n\t\t(uuid "%s")'
            '\n\t\t(at %s %s%s)%s%s\t)'
            % (fpid, uid(), fmt(x), fmt(y),
               (' %s' % fmt(rot)) if rot else '', props, inner))


# Rows of identical parts. A row on a real board has one pitch; the drawing
# gives each member its own position, and those differ by up to half a
# millimetre because the drawing rounds. Fitting a straight line through a row
# is both more accurate and the difference between terminals that touch and
# terminals with a tenth of a millimetre between them.
ROWS = (
    ('J10', 'J11', 'J12', 'J13', 'J14', 'J15'),
    ('J40', 'J41', 'J42', 'J43', 'J44', 'J45'),
    ('K1', 'K2', 'K3', 'K4', 'K5', 'K6'),
    ('D40', 'D41', 'D42', 'D43', 'D44', 'D45'),
    ('Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6'),
)

# Nudges, in millimetres, for the few places where a part here is bigger than
# the one it is copying and will not fit where that one sits.
NUDGE = {
    # The flyback diodes sit just above the relay bodies. A JQC-3FF's
    # courtyard is 19.8 mm deep against the 14.7 mm pad field of the relay on
    # the drawing, so its top edge reaches a millimetre higher.
    'D40': (0.0, -2.5), 'D41': (0.0, -2.5), 'D42': (0.0, -2.5),
    'D43': (0.0, -2.5), 'D44': (0.0, -2.5), 'D45': (0.0, -2.5),
    # The supply terminals here are 10.8 mm deep and reach further into the
    # board than the ones on the drawing, which puts the first diode of each
    # rail underneath one.
    'D1': (0.0, 3.5),
    # The 24 V diode went further: at 3.5 it sat on the terminal's own
    # legend, '24V IN', and hid it. Its capacitor moves down to make room.
    'D2': (0.0, 8.8),
    # Two arrays on the one network's position, one above the other.
    'RN1': (0.0, -4.0), 'RN2': (0.0, 4.0),
    # And the bulk capacitors here are 9.4 x 8.5 mm against a pair of pads
    # 4.8 mm apart on the drawing, so they need the room below the diode.
    'C1': (0.0, 6.0), 'C2': (0.0, 7.5),
}


def linearise(targets):
    """Replace a row's measured positions with a straight line through them."""
    for row in ROWS:
        pts = [(i, targets[r]) for i, r in enumerate(row) if r in targets]
        if len(pts) < 3:
            continue
        n = len(pts)
        mi = sum(i for i, _p in pts) / n
        for axis in (0, 1):
            vals = [p[axis] for _i, p in pts]
            mv = sum(vals) / n
            den = sum((i - mi) ** 2 for i, _p in pts)
            slope = sum((i - mi) * (v - mv) for (i, _p), v in zip(pts, vals)) / den
            for k, (i, _p) in enumerate(pts):
                t = list(targets[row[i]])
                t[axis] = mv + slope * (i - mi)
                targets[row[i]] = tuple(t)
    return targets


# Bypass capacitors, each against the supply pin it serves. In the schematic
# they are all +5V to GND and interchangeable; on the board a capacitor a few
# centimetres from its pin decouples nothing, so the pin is named here.
#
# cap: (chip, pin, outward direction in the chip's own frame, shift along the
#       pin row)
#
# The MCU's two VCC pins are 1.6 mm apart on the same side, with ground
# between them, so their capacitors are pushed 0.8 mm apart along the row or
# their courtyards would touch. A 74HC245 has VCC and GND at opposite
# corners; its capacitor goes past the end of the package by pin 20, rather
# than out to the side where the eight outputs fan out to the terminals.
PIN_CAPS = {
    'C30': ('U21', '4', (-1, 0), (0.0, -0.8)),
    # Level with its pin, not below it: below is where the crystal's pins are.
    'C31': ('U21', '6', (-1, 0), (0.0, 0.0)),
    'C32': ('U21', '18', (1, 0), (0.0, 0.0)),
    'C40': ('U1', '20', (0, -1), (0.0, 0.0)),
    'C41': ('U2', '20', (0, -1), (0.0, 0.0)),
    # MAX3232 pin 16, past the top of the package like the buffers'.
    'C42': ('U20', '16', (0, -1), (0.0, 0.0)),
}
CAP_GAP = 0.35          # mm between the chip's pad and the capacitor's

# The crystal and its two load capacitors, in the MCU's own frame - (dx, dy)
# from its origin, and a rotation added to its own. Pins 7 (XTAL1) and 8
# (XTAL2) are the last two down the MCU's left side. The crystal sits just
# below-left of them, turned so that pad 1 (XTAL2) is the corner nearest the
# chip and pad 3 (XTAL1) the corner above-left; its ground pads take the other
# two. Each load capacitor lies off its own crystal pad, away from the chip.
# First placed unturned, XTAL2's pad was the far corner, the router ran a
# ground track between the crystal's pads, and XTAL2 went round through two
# vias. Turned, both signals reach their pads on the top layer.
NEAR_MCU = {
    'Y1':  ('U21', (-7.315, 7.005), 90),
    'C33': ('U21', (-10.615, 5.905), 180),   # pad 1 (XTAL1) right, onto Y1 pad 3
    'C34': ('U21', (-6.465, 10.605), 270),   # pad 1 (XTAL2) up, onto Y1 pad 1
}


def near_mcu(comps, fixed):
    """{ref: (x, y, rot)} for NEAR_MCU, following the MCU wherever it goes."""
    out = {}
    for ref, (ic, (lx, ly), rot) in NEAR_MCU.items():
        if ref not in comps or ic not in fixed:
            continue
        ix, iy, irot = fixed[ic]
        a = math.radians(irot)
        out[ref] = (ix + lx * math.cos(a) + ly * math.sin(a),
                    iy - lx * math.sin(a) + ly * math.cos(a),
                    (rot + irot) % 360)
    return out


def pad_geom(fpid, num):
    """(x, y, w, h) of one pad, in the footprint's own frame."""
    body = load_footprint(fpid)
    for m in re.finditer(r'\(pad "([^"]+)"', body):
        if m.group(1) != num:
            continue
        blk = body[m.start():span(body, m.start())]
        at = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', blk)
        sz = re.search(r'\(size\s+([\d.]+)\s+([\d.]+)', blk)
        return (float(at.group(1)), float(at.group(2)),
                float(sz.group(1)), float(sz.group(2)))
    return None


def bypass(comps, fixed):
    """{capacitor: (x, y, rot)} - each one hard against its own pin.

    The capacitor is laid radially, its long axis pointing at the pin, and
    turned so that pad 1 - the +5V end - is the one nearest the chip. Pad 1 of
    a C_0603 sits on the footprint's -x side; turning it by atan2(-uy, ux)
    points that side back along the outward direction, at the pin.
    """
    out = {}
    for cap, (ic, pin, (ux, uy), (sx, sy)) in PIN_CAPS.items():
        if cap not in comps or ic not in fixed or not comps[cap]['fp']:
            continue
        g = pad_geom(comps[ic]['fp'], pin)
        if not g:
            print('NO PAD   : %s pin %s for %s' % (ic, pin, cap))
            continue
        px, py, pw, ph = g
        cb = footprint_box(comps[cap]['fp'])
        half_pad = (pw if ux else ph) / 2.0
        half_cap = (cb[2] - cb[0]) / 2.0
        # Clear of the pad, and clear of the chip's courtyard too. The two are
        # not the same thing past the end of a SOIC: its body runs almost a
        # millimetre beyond its last pad, and a capacitor spaced off the pad
        # alone landed on the buffer's own courtyard.
        ib = footprint_box(comps[ic]['fp'])
        edge = (ib[0] if ux < 0 else ib[2]) if ux else (ib[1] if uy < 0 else ib[3])
        along = px if ux else py
        reach = max(half_pad + CAP_GAP, abs(edge - along) + 0.05) + half_cap
        lx, ly = px + ux * reach + sx, py + uy * reach + sy
        ix, iy, irot = fixed[ic]
        a = math.radians(irot)
        wx = lx * math.cos(a) + ly * math.sin(a)
        wy = -lx * math.sin(a) + ly * math.cos(a)
        crot = (math.degrees(math.atan2(-uy, ux)) + irot) % 360
        out[cap] = (ix + wx, iy + wy, crot)
    return out


def reference():
    """The drawing, as tools/read_ref.py measured it."""
    with open(REF, encoding='utf-8') as f:
        return json.load(f)


def anchored(comps, ref):
    """{reference: (x, y, rot)} for everything the drawing pins down."""
    out, targets, turn = {}, {}, {}
    for mine, (theirs, rot) in ANCHORS.items():
        if mine not in comps or not comps[mine]['fp']:
            continue
        names = (theirs,) if isinstance(theirs, str) else theirs
        pts = [p for n in names for p in ref['pads'].get(n, {}).values()]
        if not pts:
            print('NO ANCHOR: %s (wanted %s)' % (mine, names))
            continue
        targets[mine] = ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0,
                         (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0)
        turn[mine] = rot
    linearise(targets)
    for mine, (tx, ty) in targets.items():
        dx, dy = NUDGE.get(mine, (0.0, 0.0))
        bx1, by1, bx2, by2 = rot_box(pad_box(comps[mine]['fp']), turn[mine])
        out[mine] = (tx + dx - (bx1 + bx2) / 2.0,
                     ty + dy - (by1 + by2) / 2.0, turn[mine])
    return out


def net_table(comps):
    names = set()
    for c in comps.values():
        names.update(c['pads'].values())
    return {n: i + 1 for i, n in enumerate(sorted(names))}


class Shelf:
    """Pack a rectangle in rows, then open the rows out to fill it.

    Spreading only ever increases the distance between parts, provided each row
    keeps its own height: giving every row an equal slice looks tidier and drops
    a 16 mm relay onto its neighbour.

    A shelf also has to know what it may not use. Parts placed by hand are put
    down before any shelf runs, and the shelf has no other way of hearing about
    them - the first version did not, so hand-placing three chips inside the
    input band dropped them straight onto the resistors the packer had already
    filed there: 14 shorted pads that DRC found and the generator did not.
    `block` takes those rectangles and every row then packs around them.
    """

    def __init__(self, name, rect):
        self.name = name
        self.x1, self.y1, self.x2, self.y2 = rect
        self.x, self.y, self.h = self.x1, self.y1, 0.0
        self.overflow, self.items, self.row, self.blocks = [], [], 0, []

    def block(self, rects):
        """Keep out of these, in board coordinates. Ones that miss are ignored."""
        self.blocks = [r for r in rects
                       if r[0] < self.x2 and r[2] > self.x1
                       and r[1] < self.y2 and r[3] > self.y1]

    def usable(self, h):
        """The least width any band of this height can count on.

        `add` decides how many parts go in a row; `spread` then decides what
        height that row sits at, and the two need not agree. Measuring the free
        width at the height `add` happens to be at builds rows for a width that
        `spread` may not have: the input row was packed against 82 mm of clear
        space above the optocouplers and then laid out level with them, where
        there are 47 mm, and the last few parts marched straight out of the
        rectangle and across the power block.

        Taking the worst band instead is never wrong, only sometimes mean.
        """
        lo, worst = self.y1, None
        while lo + h <= self.y2 + 1e-9:
            # Each separate run costs a gap of its own at the far end, and a
            # band split three ways by two chips is three runs, not one.
            w = sum(max(0.0, b - a - GAP) for a, b in self._free(lo, lo + h))
            worst = w if worst is None else min(worst, w)
            lo += 1.0
        return (self.x2 - self.x1) if worst is None else worst

    def add(self, ref, box):
        bx1, by1, bx2, by2 = box
        w, h = bx2 - bx1, by2 - by1
        room = self.usable(max(self.h, h))
        if self.x + w + GAP > self.x1 + room and self.x > self.x1:
            # self.h has to be read before it is cleared - the first version
            # zeroed it first, so self.y only ever advanced by GAP and every
            # row believed it was still at the top of the shelf.
            self.y += self.h + GAP
            self.x, self.h = self.x1, 0.0
            self.row += 1
        self.items.append([ref, bx1, by1, w, h, self.row])
        self.x += w + GAP
        self.h = max(self.h, h)
        if self.y + self.h > self.y2:
            self.overflow.append(ref)

    def _free(self, lo, hi):
        """The x runs across this band that no blocked rectangle covers."""
        cuts = sorted((r[0], r[2]) for r in self.blocks
                      if r[1] < hi and r[3] > lo)
        free, x = [], self.x1
        for c0, c1 in cuts:
            if c0 > x:
                free.append((x, min(c0, self.x2)))
            x = max(x, c1)
        if x < self.x2:
            free.append((x, self.x2))
        return [f for f in free if f[1] - f[0] > 1.0] or [(self.x1, self.x2)]

    def spread(self):
        rows = {}
        for it in self.items:
            rows.setdefault(it[5], []).append(it)
        if not rows:
            return {}
        order = sorted(rows)
        heights = [max(it[4] for it in rows[r]) for r in order]
        slack = (self.y2 - self.y1) - sum(heights)
        extra = max(slack / (len(order) + 1), GAP) if slack > 0 else GAP
        pos, top = {}, self.y1 + extra
        for i, r in enumerate(order):
            segs = self._free(top, top + heights[i])
            # Fill each free run in turn, moving on when the next part no longer
            # fits. The last run takes whatever is left over.
            runs, k, cur, used = [], 0, [], 0.0
            for it in rows[r]:
                room = segs[k][1] - segs[k][0]
                if cur and k < len(segs) - 1 and used + it[3] + GAP * len(cur) > room:
                    runs.append((segs[k], cur))
                    k, cur, used = k + 1, [], 0.0
                cur.append(it)
                used += it[3]
            runs.append((segs[k], cur))
            for (sx1, sx2), items in runs:
                gap = max((sx2 - sx1 - sum(it[3] for it in items))
                          / (len(items) + 1), GAP)
                left = sx1 + gap
                for ref, bx1, by1, w, h, _r in items:
                    # Say so rather than walking out of the rectangle. A part
                    # laid past the end of the shelf lands on whatever is
                    # there; past the end of one run inside it is only tight.
                    if left + w > self.x2 + 1e-6 and ref not in self.overflow:
                        self.overflow.append(ref)
                    pos[ref] = (left - bx1,
                                top + (heights[i] - h) / 2.0 - by1)
                    left += w + gap
            top += heights[i] + extra
        return pos



# place_edge used to spread a row of connectors between two coordinates,
# and it is gone: every connector now lands on the position measured off the
# drawing. Its minimum-gap rule was what forced an 18 mm pitch onto a 16 mm
# block and walked the last relay 16 mm out of place.

# Designators that the default spot - centred above the part - puts on top of
# something else: another designator, a neighbour's pads or outline, or a
# terminal legend. (dx, dy) from the part's origin, in board directions.
REF_AT = {
    'D1': (0.0, 2.6),       # below: above is the handwheel terminal's outline
    'D2': (-4.6, 0.0),      # left: above is the '24V IN' legend
    'C2': (0.0, 4.4),       # below: above, since D2 moved down, is D2
    'C30': (0.0, -1.6),     # above: below, it lay across C31's pads
    'Y1': (-1.6, 3.2),      # below-left: its left side is C33's designator
    'U20': (-2.5, -6.1),    # left of C42's designator, not on it
}

# What to silkscreen beside each terminal, keyed by reference so it cannot
# drift from the schematic without being noticed.
LABELS = {
    'J1': ('LPT PORT 1', 'STEP / DIR / HOME'),
    'J2': ('LPT PORT 2', 'E-STOP / MPG'),
    'J3': ('5V IN', '+5  0V'), 'J4': ('24V IN', '+24  0V'),
    'J30': ('HANDWHEEL', '+5  0V  A  B'),
    'J50': ('RS232', 'RX  TX  GND'),
}
for _i, _a in enumerate('XYZABC'):
    LABELS['J%d' % (10 + _i)] = ('%s AXIS' % _a, 'PUL  0V  DIR')
# One six-way block carries all of it, one wire per channel, exactly as on the
# board in service. The sensors take their +24 and 0 V from the supply terminal,
# not from here - there is no third screw per channel to take it from.
LABELS['J20'] = ('EMG & HOME', 'EMG   C   A   Z   Y   X')
for _i, _c in enumerate('ABCDEF'):
    LABELS['J%d' % (40 + _i)] = ('RELAY %s' % _c, 'NO  COM  NC',
                                 "'%s'=on  '%s'=off" % (_c, _c.lower()))


def silk(text, x, y, rot, size=1.2, just='', layer='F.SilkS'):
    return ('\t(gr_text "%s" (at %s %s %s) (layer "%s") (uuid "%s")'
            ' (effects (font (size %s %s) (thickness 0.2))%s))'
            % (text, fmt(x), fmt(y), fmt(rot), layer, uid(), size, size,
               (' (justify %s)' % just) if just else ''))


def main():
    if os.path.exists(OUT) and '--force' not in sys.argv:
        if open(OUT, encoding='utf-8').read().count('(segment'):
            print('REFUSING : %s already holds routed copper.' % OUT)
            print('           Regenerating discards it. Use --force if that is')
            print('           what you want, then re-run the router.')
            return 1

    comps = read_netlist()
    nets = net_table(comps)

    ref = reference()
    fixed = anchored(comps, ref)
    fixed.update(bypass(comps, fixed))
    fixed.update(near_mcu(comps, fixed))
    for i, (hx, hy) in enumerate(MOUNTS):
        if 'H%d' % (i + 1) in comps:
            fixed['H%d' % (i + 1)] = (hx, hy, 0)
    for r, v in FIXED_PARTS.items():
        if r in comps:
            fixed[r] = v

    shelves = [Shelf(n, rect) for n, rect, _ in GROUPS]
    by_name = {s.name: s for s in shelves}
    rules = [(n, re.compile(p)) for n, _, p in GROUPS]
    # The strip between the D-subs and the middle of the board, which is
    # empty on their board too. Nothing should land here.
    spare = Shelf('spare', (16.0, 46.0, 28.0, 100.0))  # nothing should land here

    # Everything already placed, with a gap around it, is out of bounds for the
    # packer. Connectors on the edges count too: an edge terminal's body reaches
    # well inside the board.
    taken = []
    for ref, (fx, fy, frot) in fixed.items():
        if ref not in comps or not comps[ref]['fp']:
            continue
        bx1, by1, bx2, by2 = rot_box(footprint_box(comps[ref]['fp']), frot)
        taken.append((fx + bx1 - GAP, fy + by1 - GAP,
                      fx + bx2 + GAP, fy + by2 + GAP))
    for sh in shelves + [spare]:
        sh.block(taken)

    # Mounting holes carry no silkscreen outline, so the designator lands
    # inside the hole. There is nothing for it to name anyway.
    hole_refs = {'H%d' % (i + 1) for i in range(len(MOUNTS))}
    # The relays are 16.2 mm wide on a 16.2 mm pitch and turned on their side,
    # which leaves no room between one and the next for a designator.
    # The legend under each one already reads RELAY A .. RELAY F, so the
    # designator is the thing to drop rather than the pitch.
    hole_refs |= {'K%d' % (i + 1) for i in range(6)}
    placed, skipped, pending, counts = [], [], [], {}
    order = sorted(comps, key=lambda r: (re.match(r'[A-Za-z#]+', r).group(0),
                                         int(re.sub(r'\D', '', r) or 0)))
    for ref in order:
        c = comps[ref]
        if not c['fp'] or ':' not in c['fp']:
            skipped.append((ref, 'no footprint'))
            continue
        box = footprint_box(c['fp'])
        if ref in fixed:
            x, y, rot = fixed[ref]
            where = 'by hand' if ref in FIXED_PARTS or ref.startswith('K') \
                else 'edge'
        else:
            rot, where = 0, None
            for name, pat in rules:
                if pat.match(ref):
                    where = name
                    break
            sh = by_name[where] if where else spare
            where = where or 'spare'
            sh.add(ref, box)
            x = y = None
        counts[where] = counts.get(where, 0) + 1
        pending.append((ref, c, x, y, rot))

    pos = {}
    for sh in shelves + [spare]:
        pos.update(sh.spread())
    for ref, c, x, y, rot in pending:
        if x is None:
            x, y = pos[ref]
        placed.append(footprint_instance(c['fp'], ref, c['value'], x, y,
                                         c['pads'], rot, c.get('fields'),
                                         ref in LABELS or ref in hole_refs,
                                         nets, REF_AT.get(ref), c.get('dnp')))

    edge = []
    for x1, y1, x2, y2 in ((0, 0, BOARD_W, 0), (BOARD_W, 0, BOARD_W, BOARD_H),
                           (BOARD_W, BOARD_H, 0, BOARD_H), (0, BOARD_H, 0, 0)):
        edge.append('\t(gr_line (start %s %s) (end %s %s)'
                    ' (stroke (width 0.15) (type default)) (layer "Edge.Cuts")'
                    ' (uuid "%s"))' % (fmt(x1), fmt(y1), fmt(x2), fmt(y2), uid()))

    silks, unlabelled = [], []
    for side, refs in EDGES:
        for ref in refs:
            # Every connector on an edge gets its legend, not just the screw
            # terminals. The D-subs used to be identified by their own
            # designator; that is hidden now, so without this they carry no
            # marking at all.
            if ref not in fixed:
                continue
            if ref not in LABELS:
                unlabelled.append(ref)
                continue
            lab = LABELS[ref]
            x, y, rot = fixed[ref]
            bx1, by1, bx2, by2 = rot_box(footprint_box(comps[ref]['fp']), rot)
            cx, cy = x + (bx1 + bx2) / 2.0, y + (by1 + by2) / 2.0
            if side == 'top':
                silks.append(silk(lab[1], cx, y + by2 + 1.6, 0, 0.9))
                silks.append(silk(lab[0], cx, y + by2 + 4.0, 0, 1.2))
            elif side == 'bottom':
                # On F.Fab, not the silkscreen. A relay's body ends half a
                # millimetre above its own terminal - on the board in service
                # too, which is why that board carries this text outside its
                # own outline, as drawing annotation. F.Fab is the same idea:
                # it prints in review/PLACEMENT.pdf and not on the board.
                for k, line in enumerate(lab):
                    silks.append(silk(line, cx, y + by1 - 1.4 - 2.2 * k, 0,
                                      1.1 if k == 0 else 0.9,
                                      layer='F.Fab'))
            elif side == 'left':
                silks.append(silk(lab[1], x + bx2 + 1.6, cy, 270, 0.9))
                silks.append(silk(lab[0], x + bx2 + 4.0, cy, 270, 1.2))
            elif side == 'right':
                silks.append(silk(lab[1], x + bx1 - 1.6, cy, 90, 0.9))
                silks.append(silk(lab[0], x + bx1 - 4.0, cy, 90, 1.2))
    HEAD = {'inputs': 'INPUTS', 'power': 'POWER', 'buffers': 'AXIS BUFFERS',
            'mcu': 'MCU', 'relaydrv': 'RELAY DRIVERS',
            'switch': 'MPG / THC SWITCH', 'serial': 'RS232', 'chassis': 'SHELL'}
    for name, rect, _ in GROUPS:
        silks.append(silk(HEAD[name], rect[0] + 1.0, rect[1] - 1.2, 0, 1.3,
                          'left bottom'))
    silks.append(silk('MACH3-SIMPLE  NOT ISOLATED', 14.0, 7.5, 0, 1.0,
                      'left bottom'))

    zone = ('\t(zone\n\t\t(net %d)\n\t\t(net_name "GND")'
            '\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(uuid "%s")\n\t\t(name "GND pour")'
            '\n\t\t(hatch edge 0.508)\n\t\t(connect_pads (clearance 0.508))'
            '\n\t\t(min_thickness 0.25)'
            '\n\t\t(fill yes (thermal_gap 0.508) (thermal_bridge_width 0.508))'
            '\n\t\t(polygon (pts (xy 0.5 0.5) (xy %s 0.5) (xy %s %s)'
            ' (xy 0.5 %s)))\n\t)'
            % (nets.get('GND', 0), uid(), fmt(BOARD_W - 0.5),
               fmt(BOARD_W - 0.5), fmt(BOARD_H - 0.5), fmt(BOARD_H - 0.5)))

    decl = ['\t(net 0 "")'] + ['\t(net %d "%s")' % (i, n)
                               for n, i in sorted(nets.items(),
                                                  key=lambda kv: kv[1])]
    head = ('(kicad_pcb (version 20240108) (generator "pcbnew")'
            ' (general (thickness 1.6)) (paper "A3")'
            '(layers (0 "F.Cu" signal) (31 "B.Cu" signal)'
            ' (34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user)'
            ' (37 "F.SilkS" user) (38 "B.Mask" user) (39 "F.Mask" user)'
            ' (40 "Dwgs.User" user) (41 "Cmts.User" user) (44 "Edge.Cuts" user)'
            ' (45 "Margin" user))(setup (pad_to_mask_clearance 0)'
            ' (grid_origin 0 0))')
    with open(OUT, 'w', encoding='utf-8', newline='') as f:
        f.write(head + '\n' + '\n'.join(decl + edge + silks + placed + [zone])
                + '\n)\n')
    write_rules()

    print('board    : %.0f x %.0f mm, 2 layers, one ground pour'
          % (BOARD_W, BOARD_H))
    print('placed   : %d footprints' % len(placed))
    for k in ('edge', 'by hand') + tuple(g[0] for g in GROUPS) + ('spare',):
        if counts.get(k):
            print('           %-10s %3d' % (k, counts[k]))
    over = [(s.name, s.overflow) for s in shelves + [spare] if s.overflow]
    for name, refs in over:
        print('OVERFLOW : %-10s %d: %s' % (name, len(refs), ' '.join(refs)))
    if unlabelled:
        print('NO LABEL : %s' % ' '.join(unlabelled))
    if skipped:
        print('SKIPPED  : %s' % skipped[:8])
    print('silk     : %d labels' % len(silks))
    print('routing  : none yet')
    return 0


def write_rules():
    path = os.path.join('hardware', 'MACH3SIMPLE.kicad_dru')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('(version 1)\n\n'
                '# A bypass capacitor wants the lowest inductance it can get to\n'
                '# the plane, so a thermal relief on one works against the reason\n'
                '# it is there. Through-hole pads keep their reliefs so the\n'
                '# terminals stay hand-solderable.\n'
                '(rule "surface-mount pads connect solid"\n'
                '\t(constraint zone_connection solid)\n'
                '\t(condition "A.Pad_Type == \'SMD\'"))\n\n'
                '# One spoke is enough on a through-hole ground pad, because the\n'
                '# spokes are not what connects it. Ground is routed as a net\n'
                '# (see tools/autoroute.py), so every ground pad already has its\n'
                '# own track, and the pour only adds area. KiCad wants two by\n'
                '# default, and on a D-sub - where signal tracks crowd between\n'
                '# the pins - the router often leaves room for one; that failed\n'
                '# DRC as an error on a different D-sub pin on each routing run.\n'
                '# A bare count, not (min 1): the (min ...) form is for\n'
                '# distances. Written that way, KiCad threw the whole file away\n'
                '# without a word, and the SMD rule above went with it.\n'
                '(rule "through-hole ground pads need one spoke"\n'
                '\t(constraint min_resolved_spokes 1)\n'
                '\t(condition "A.Pad_Type == \'Through-hole\' && A.NetName == \'GND\'"))\n')


if __name__ == '__main__':
    sys.exit(main() or 0)
