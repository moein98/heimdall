#!/usr/bin/env python3
"""Compare the generated placement against the board in service.

The drawing of the board in service is the specification for this layout, so
the layout needs a check against it that is a number rather than an opinion.
This prints, for every part that could be matched one-for-one, where it sits on
the generated board and where its counterpart sits on the drawing; and for each
row of connectors, the pitch measured on the drawing beside the pitch built.

What it does NOT do is claim the two coordinate systems are registered to each
other. They are not: the drawing gives a field of parts, not a board outline, so
absolute positions carry an unknown offset of a few millimetres. Pitches and
relative spacings are the trustworthy part, and they are what is checked.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb as bp                                       # noqa: E402

BOARD = os.path.join('hardware', 'MACH3SIMPLE.kicad_pcb')
REF = os.path.join('review', 'ref.json')

# Generated reference -> reference on the drawing. Only parts that could be
# identified with confidence are here; the board in service uses six
# single-channel optocouplers where this one uses two four-channel parts, so
# those cannot be matched one-for-one and are left out.
# Taken from the placement itself, so the two cannot drift apart. It already
# says which part here stands for which part on the drawing; repeating that
# here by hand is how this check came to be testing a mapping the board had
# stopped using.
# A value may be several references: a four-channel optocoupler here stands
# for four single-channel ones there, and is placed at the middle of them.
SAME = {mine: ((theirs,) if isinstance(theirs, str) else tuple(theirs))
        for mine, (theirs, _rot) in bp.ANCHORS.items()}

# Rows whose pitch is the thing to get right.
ROWS = (('axis terminals, down the right edge',
         ['J10', 'J11', 'J12', 'J13', 'J14', 'J15'], 1),
        ('relay terminals, along the bottom',
         ['J40', 'J41', 'J42', 'J43', 'J44', 'J45'], 0),
        ('relays, above their terminals',
         ['K1', 'K2', 'K3', 'K4', 'K5', 'K6'], 0),
        ('parallel ports, down the left edge', ['J1', 'J2'], 1))


def board_positions(path):
    """{reference: (x, y) of its pad field's centre} from a built board.

    The centre of the pads, not the footprint's origin: origins sit wherever
    the library author put them, and the placement is matched on pads.
    """
    t = open(path, encoding='utf-8').read()
    comps = bp.read_netlist()
    out = {}
    # One footprint at a time, rather than one pattern across the file. The
    # generator writes a footprint's position and its reference next to each
    # other; pcbnew, saving the routed board, puts its description and tags in
    # between, and a pattern that assumed the first layout matched nothing at
    # all on the second.
    for blk in re.split(r'\n\s*\(footprint "', t)[1:]:
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', blk)
        rf = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if not (at and rf):
            continue
        r = rf.group(1)
        if r not in comps or not comps[r]['fp']:
            continue
        x, y = float(at.group(1)), float(at.group(2))
        rot = float(at.group(3) or 0)
        bx1, by1, bx2, by2 = bp.rot_box(bp.pad_box(comps[r]['fp']), rot)
        out[r] = (x + (bx1 + bx2) / 2.0, y + (by1 + by2) / 2.0)
    return out


def pitches(seq, axis):
    return [round(b[axis] - a[axis], 1) for a, b in zip(seq, seq[1:])]


def main():
    if not os.path.exists(BOARD):
        print('no board yet - run tools/build_pcb.py')
        return 1
    mine, ref = board_positions(BOARD), json.load(open(REF))
    # Compare pad-field centres, which is what the placement matches on.
    def centre(names):
        pts = [p for n in names for p in ref['pads'].get(n, {}).values()]
        if not pts:
            return None
        return ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0,
                (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0)

    theirs = {mine: centre(names) for mine, names in SAME.items()
              if centre(names)}

    print('ROW PITCH (mean)                     drawing            generated')
    bad = 0
    for name, refs, axis in ROWS:
        t = [theirs[r] for r in refs if r in theirs]
        m = [mine[r] for r in refs if r in mine]
        if len(t) != len(refs) or len(m) != len(refs):
            print('  %-30s incomplete' % name)
            continue
        pt, pm = pitches(t, axis), pitches(m, axis)
        if pt and pm and (pt[0] < 0) != (pm[0] < 0):
            pt = [-v for v in reversed(pt)]
        # Compare the averages, not step by step. A row of identical parts on a
        # real board has one pitch; where the drawing gives 16.6 for one step
        # and 18.9 for the next, the difference is the extraction's error, not
        # the board's. The spread is printed so that error stays visible.
        at = sum(abs(v) for v in pt) / len(pt)
        am = sum(abs(v) for v in pm) / len(pm)
        spread = max(abs(v) for v in pt) - min(abs(v) for v in pt)
        off = abs(at - am)
        flag = '' if off <= 0.5 else '   <-- %.1f mm out' % off
        bad += off > 0.5
        print('  %-34s %5.1f  (spread %.1f)      %5.1f%s'
              % (name, at, spread, am, flag))

    print()
    print('MATCHED PARTS      drawing            generated          dx     dy')
    # Register the two frames on the parts themselves: the median offset is the
    # best estimate of where the drawing's field sits on the board.
    keys = [k for k in SAME if k in mine and k in theirs]
    # Register on the integrated circuits alone. A KiCad footprint's origin is
    # the centre of the part; the drawing's is a corner for a connector and pin
    # one for a relay, so mixing them into the estimate drags it by tens of
    # millimetres and then reports that drag as everything being out of place.
    anchor = [k for k in keys if k.startswith('U')] or keys
    dxs = sorted(mine[k][0] - theirs[k][0] for k in anchor)
    dys = sorted(mine[k][1] - theirs[k][1] for k in anchor)
    ox, oy = dxs[len(dxs) // 2], dys[len(dys) // 2]
    print('  (drawing offset by %+.1f, %+.1f mm to line the two up)' % (ox, oy))
    for k in sorted(keys, key=lambda k: (mine[k][1], mine[k][0])):
        tx, ty = theirs[k]
        mx, my = mine[k]
        dx, dy = mx - (tx + ox), my - (ty + oy)
        # A part moved on purpose is listed in NUDGE with how far; only what
        # is left over after that is drift.
        nx, ny = bp.NUDGE.get(k, (0.0, 0.0))
        far = '   <--' if max(abs(dx - nx), abs(dy - ny)) > 1.0 else ''
        print('  %-5s %-12s %7.1f %7.1f    %7.1f %7.1f   %+5.1f %+5.1f%s'
              % (k, '+'.join(SAME[k])[:12], tx + ox, ty + oy,
                 mx, my, dx, dy, far))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
