#!/usr/bin/env python3
"""Read the assembly drawing of the board in service. Outline first.

This replaces tools/read_ref_pdf.py, which read only the text marks and scaled
them by a pitch guessed off the D-sub pads. It had no frame: the numbers it
produced were a cloud of part positions with no board around them, so the board
size had to be inferred from how far apart the outermost parts were plus a
margin somebody made up. That came out 168 x 145 mm and was wrong.

The outline is in the drawing. It is stroked in purple - 0.502 0 0.502 - and it
is the only thing on the page in that ink. With it, every position becomes a
distance from a board edge, which can be checked against the board being built
rather than registered against it by eye.

Scale comes from the D-sub pad field, which is the one dimension on the page
that is fixed by a standard rather than by this board: a DB25's two rows are
2.77 mm apart within a row, offset by half that, so all 25 pins projected onto
the long axis make a ladder at 1.385 mm, and the outer pins of one row span
exactly 12 x 2.77 = 33.24 mm. Both are computed below and they have to agree.
"""
import collections
import json
import os
import re
import statistics
import sys
import zlib

PDF = 'mach3 rs232 inputs 6 outputs 6 - pulse 5v - pnp sens.pdf'
OUT = os.path.join('review', 'ref.json')
OUTLINE_INK = (0.502, 0.0, 0.502)    # the board edge, and only that
PART_INK = (0.0, 0.502, 0.0)         # every part outline
DSUB_PITCH = 2.77          # within one row, mm
DSUB_ROW_SPAN = 12 * 2.77  # outer pin to outer pin of the 13-pin row


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


def segments(content, want):
    """Stroked segments drawn in one ink."""
    segs, ink, cur, start = [], None, None, None
    for line in content.split(b'\n'):
        t = line.strip().decode('latin-1')
        m = re.match(NUM + r'\s+' + NUM + r'\s+' + NUM + r'\s+RG$', t)
        if m:
            ink = tuple(round(float(v), 3) for v in m.groups())
            continue
        m = re.match(NUM + r'\s+' + NUM + r'\s+m$', t)
        if m:
            cur = start = (float(m.group(1)), float(m.group(2)))
            continue
        m = re.match(NUM + r'\s+' + NUM + r'\s+l$', t)
        if m and cur:
            nxt = (float(m.group(1)), float(m.group(2)))
            if ink == want:
                segs.append((cur, nxt))
            cur = nxt
    return segs


def text_marks(content):
    """[(x, y, text)] - the drawing labels every origin and every pad."""
    items, x, y = [], 0.0, 0.0
    for line in content.split(b'\n'):
        t = line.strip()
        # The caret goes outside the repetition. Inside it, the anchor is
        # repeated too and the pattern can never match, so every text mark
        # kept the position of the one before it - which is to say (0, 0).
        m = re.match(r'^' + (NUM + r'\s+') * 5 + NUM + r'\s+Tm$',
                     t.decode('latin-1'))
        if m:
            x, y = float(m.group(5)), float(m.group(6))
            continue
        m = re.match(r'^' + NUM + r'\s+' + NUM + r'\s+Td$', t.decode('latin-1'))
        if m:
            x += float(m.group(1))
            y += float(m.group(2))
            continue
        m = re.search(rb'\((.*)\)\s*Tj', t)
        if m:
            items.append((x, y, m.group(1).decode('latin-1')))
    return items


def main():
    raw = open(sys.argv[1] if len(sys.argv) > 1 else PDF, 'rb').read()
    blobs = streams(raw)
    segs, strokes, marks = [], [], []
    for c in blobs:
        segs.extend(segments(c, OUTLINE_INK))
        strokes.extend(segments(c, PART_INK))
        marks.extend(text_marks(c))
    if not segs:
        print('no outline found in the drawing')
        return 1

    xs = [p[0] for s in segs for p in s]
    ys = [p[1] for s in segs for p in s]
    gx0, gx1, gy0, gy1 = min(xs), max(xs), min(ys), max(ys)
    print('outline   : %d segments, %.2f x %.2f pt'
          % (len(segs), gx1 - gx0, gy1 - gy0))

    origins = {t[2:]: (x, y) for x, y, t in marks
               if t.startswith('CO') and len(t) > 2}
    refs = sorted(origins, key=len, reverse=True)

    # A pad is labelled PA<ref>0<pin>: the pin number carries a leading zero,
    # so J1's twenty-seven pads read PAJ101 .. PAJ1027. The zero is what makes
    # the split unambiguous, and it has to be: the drawing names repeated
    # blocks by nesting, so T13, T1301 and T130101 are three different
    # terminals and the longest reference that still leaves a 0<digits> tail
    # is the right one. Matching on the reference alone put one part's pads on
    # another part.
    pads = collections.defaultdict(dict)
    for x, y, t in marks:
        if not t.startswith('PA'):
            continue
        body = t[2:]
        for r in refs:
            if body.startswith(r) and re.fullmatch(r'0\d+', body[len(r):]):
                pads[r][int(body[len(r) + 1:])] = (x, y)
                break

    # Scale, two ways, from the D-sub that has the most pads.
    best = max(('J1', 'J2'), key=lambda r: len(pads.get(r, ())))
    # One row, outer pin to outer pin. Pins 1 to 13 are the long row of a DB25
    # and they span twelve pitches of 2.77 mm exactly.
    #
    # Not the gap between neighbouring pins. The drawing rounds its text
    # positions to about a third of a point, so consecutive pins come out 6.00,
    # 6.31 and 6.69 pt apart in turn. Taking the middle of those gave 6.00, a
    # scale 4 per cent too small, and a board 4 per cent too large in each
    # direction. Twelve pitches measured as one baseline are immune to that.
    row = [v[1] for k, v in sorted(pads[best].items()) if 1 <= k <= 13]
    scale = (12 * DSUB_PITCH) / (max(row) - min(row))
    gaps = [round(b - a, 2) for a, b in zip(row, row[1:])]
    print('scale     : %s pins 1-13 span %.2f pt = %.2f mm -> %.4f mm/pt'
          % (best, max(row) - min(row), 12 * DSUB_PITCH, scale))
    print('            (single gaps read %s - rounded, hence the long baseline)'
          % ' '.join('%.2f' % g for g in sorted(set(gaps))))

    # The text marks and the strokes are two frames, and they differ by a
    # scale as well as an offset - the labels are drawn 3.47 per cent larger
    # than the geometry they annotate. Checking for strokes at a pad's stated
    # position finds nothing; the part is lower AND closer in.
    #
    # That matters for exactly one number. Every distance derived inside the
    # text frame is right, because the scale was calibrated inside it and the
    # ratio cancels. The board outline is not: it is drawn, not labelled, so
    # measuring it in points and multiplying by the text frame's scale made it
    # 3.47 per cent too small. It came out 145.2 x 133.0 mm that way.
    #
    # The two frames are tied together here by features that appear in both:
    # the six relay bodies for x, the two D-sub bodies for y. Both give the
    # same ratio, which is the check that the fit means something.
    def fit(t, g):
        """Least squares a, b for t = a*g + b, plus the worst residual."""
        n = len(t)
        mt, mg = sum(t) / n, sum(g) / n
        a = (sum((ti - mt) * (gi - mg) for ti, gi in zip(t, g))
             / sum((gi - mg) ** 2 for gi in g))
        b = mt - a * mg
        return a, b, max(abs(ti - (a * gi + b)) for ti, gi in zip(t, g))

    def bodies(vert, lo, hi, want):
        """Pairs of vertical strokes of a given length: a row of part outlines."""
        v = sorted((x, min(p, q), max(p, q)) for x, p, q in vert
                   if lo < abs(q - p) < hi)
        edges = sorted(x for x, _a, _b in v)
        out, i = [], 0
        while i + 1 < len(edges):
            if edges[i + 1] - edges[i] > want * 0.8:
                out.append((edges[i] + edges[i + 1]) / 2.0)
                i += 2
            else:
                i += 1
        return out

    vert = [(a[0], a[1], b[1]) for a, b in strokes
            if abs(a[0] - b[0]) < 0.05]
    relays_g = bodies(vert, 38.0, 45.0, 30.0)
    dsubs_g = sorted(set(round((a + b) / 2.0, 1) for x, a, b in vert
                         if 110 < abs(b - a) < 122))
    relays_t = sorted(((min(p[0] for p in v.values())
                        + max(p[0] for p in v.values())) / 2.0, r)
                      for r, v in pads.items() if r.startswith('K'))
    dsubs_t = sorted((min(p[1] for p in pads[r].values())
                      + max(p[1] for p in pads[r].values())) / 2.0
                     for r in ('J1', 'J2') if r in pads)
    if len(relays_g) < 6 or len(dsubs_g) < 2:
        print('could not tie the two frames together')
        return 1
    ax, bx, rx = fit([t for t, _r in relays_t][:6], relays_g[:6])
    ay, by, ry = fit(dsubs_t, dsubs_g[:2])
    print('frames    : text = %.4f x strokes %+.1f in x (worst %.2f pt),'
          ' %.4f %+.1f in y' % (ax, bx, rx, ay, by))
    print('            scale ratio %.4f in x, %.4f in y - they agree to %.2f%%'
          % (ax, ay, 100 * abs(ax - ay) / ax))

    # The drawn board, in the drawn frame, at the drawn frame's scale.
    gscale = scale * (ax + ay) / 2.0
    bw, bh = (gx1 - gx0) * gscale, (gy1 - gy0) * gscale
    print('BOARD     : %.1f x %.1f mm' % (bw, bh))

    def mm(p):
        """A text-frame point, to mm from the board's top-left corner.

        Through the fit, so the answer is where the part is drawn rather than
        where its label is printed.
        """
        return (round(((p[0] - bx) / ax - gx0) * gscale, 2),
                round((gy1 - (p[1] - by) / ay) * gscale, 2))

    out = {'board': [round(bw, 2), round(bh, 2)], 'scale_mm_per_pt': scale,
           'parts': {r: mm(origins[r]) for r in origins},
           'pads': {r: {str(k): mm(p) for k, p in sorted(v.items())}
                    for r, v in pads.items()}}
    os.makedirs('review', exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1, sort_keys=True)
    print('parts     : %d with an origin, %d with pads located'
          % (len(origins), len(pads)))
    print('written   : %s' % OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
