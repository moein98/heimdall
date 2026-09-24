#!/usr/bin/env python3
"""Read the assembly drawing of the board in service as vectors, from scratch.

The earlier reader took only the text marks - the CO<ref> origin labels - and
scaled them by a pitch guessed off the D-sub pads. That gave positions with no
frame to sit in: the drawing's coordinates had to be registered against the
generated board by eye, and every comparison carried an unknown offset.

This reads the geometry instead. The drawing is a vector PDF whose strokes are
colour-coded, and one of those colours is the board outline. With the outline
in hand every part position becomes a distance from a board edge, which is a
number that can be checked rather than argued about.
"""
import collections
import re
import sys
import zlib

PDF = 'mach3 rs232 inputs 6 outputs 6 - pulse 5v - pnp sens.pdf'


def streams(raw):
    out = []
    for m in re.finditer(rb'stream\r?\n', raw):
        s = m.end()
        e = raw.find(b'endstream', s)
        if e < 0:
            continue
        try:
            out.append(zlib.decompress(raw[s:e]))
        except zlib.error:
            pass
    return out


NUM = r'(-?[\d.]+)'


def paths(content):
    """[(colour, [(x1,y1,x2,y2), ...])] - every stroked segment, with its ink."""
    segs, colour, cur, start = [], (0.0, 0.0, 0.0), None, None
    for line in content.split(b'\n'):
        t = line.strip().decode('latin-1')
        m = re.match(NUM + r'\s+' + NUM + r'\s+' + NUM + r'\s+RG$', t)
        if m:
            colour = tuple(round(float(v), 3) for v in m.groups())
            continue
        m = re.match(NUM + r'\s+' + NUM + r'\s+m$', t)
        if m:
            cur = start = (float(m.group(1)), float(m.group(2)))
            continue
        m = re.match(NUM + r'\s+' + NUM + r'\s+l$', t)
        if m and cur:
            nxt = (float(m.group(1)), float(m.group(2)))
            segs.append((colour, cur[0], cur[1], nxt[0], nxt[1]))
            cur = nxt
            continue
        m = re.match(NUM + r'\s+' + NUM + r'\s+' + NUM + r'\s+' + NUM
                     + r'\s+re$', t)
        if m:
            x, y, w, h = (float(v) for v in m.groups())
            for a in ((x, y, x + w, y), (x + w, y, x + w, y + h),
                      (x + w, y + h, x, y + h), (x, y + h, x, y)):
                segs.append((colour,) + a)
            continue
        if t == 'h' and cur and start:
            segs.append((colour, cur[0], cur[1], start[0], start[1]))
            cur = start
    return segs


def main():
    raw = open(sys.argv[1] if len(sys.argv) > 1 else PDF, 'rb').read()
    segs = []
    for c in streams(raw):
        segs.extend(paths(c))
    print('stroked segments: %d' % len(segs))

    by = collections.defaultdict(list)
    for s in segs:
        by[s[0]].append(s[1:])
    print()
    print('%-22s %6s  %-28s %s' % ('ink', 'count', 'extent (pt)', 'size (pt)'))
    for col, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        xs = [p for s in v for p in (s[0], s[2])]
        ys = [p for s in v for p in (s[1], s[3])]
        print('%-22s %6d  %7.1f %7.1f %7.1f %7.1f   %7.1f x %7.1f'
              % (str(col), len(v), min(xs), min(ys), max(xs), max(ys),
                 max(xs) - min(xs), max(ys) - min(ys)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
