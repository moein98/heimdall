#!/usr/bin/env python3
"""Route the short, unambiguous connections on MACH3SIMPLE.

The sister project's router, with the two things that do not apply here taken
out. It is still not an autorouter: it lays the local hops - a bypass capacitor
to the pin it belongs to, a series resistor into its optocoupler, a pull-up onto
the output it holds up - which are tedious by hand, unambiguous, and the same
whoever does them. Anything long, congested or needing a layer change is left
for the interactive router in pcbnew, because a bad automatic route costs more
to rip up than it saved.

One rule shapes everything here.

* **The back layer is a last resort.** B.Cu is a ground pour, and every signal
  return wants continuous copper directly under it; each back-side track cuts a
  slot in that. So a via costs the router the same as 15 mm of track. It will
  detour a long way on the front before it drops through, and the summary prints
  how much back copper it ended up using, so the trade is visible rather than
  assumed.

Two things carried over from MACH3BOB are inert on this board and were kept
rather than deleted, because this board is meant to grow back into that one:

* **The isolation barrier.** MACH3BOB refuses any route that would leave its
  net's domain. Here there is one ground and one domain, so `domain_of` returns
  the same answer everywhere.
* **Differential pairs.** MACH3BOB routes its RS-422 STEP/DIR pairs first and
  side by side. Pairs are found by matching `_P` against `_N`, and this board's
  outputs are single-ended 5 V, so nothing matches and the pass does nothing.

Usage:  python tools/route.py [max_length_mm]
"""
import heapq
import math
import os
import re
import sys

BOARD = os.path.join('hardware', 'MACH3SIMPLE.kicad_pcb')

GRID = 0.25                 # mm per cell
CLEARANCE = 0.2             # mm, matches the Default net class
DEFAULT_W = 0.25
POWER_W = 0.6
POWER_NETS = ('V24', '+5V', 'GND')

# The isolation band, from build_pcb. A route may not enter it unless the net
# already lives there, and may never pass through it.


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


def read_board(path):
    """(text, board_w, board_h, [pad]) where a pad is a dict in board space."""
    s = open(path, encoding='utf-8').read()
    xs = [float(m.group(1)) for m in
          re.finditer(r'\(gr_line \(start ([\d.]+) [\d.]+\) \(end ([\d.]+)', s)]
    pads = []
    for m in re.finditer(r'\n\t\(footprint "', s):
        st = s.index('(', m.start() + 1)
        blk = s[st:span(s, st)]
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk)
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', blk)
        if not (ref and at):
            continue
        fx, fy = float(at.group(1)), float(at.group(2))
        frot = math.radians(float(at.group(3) or 0))
        ca, sa = math.cos(frot), math.sin(frot)
        for pm in re.finditer(r'\(pad "', blk):
            pb = blk[pm.start():span(blk, pm.start())]
            num = re.match(r'\(pad "([^"]*)" (\w+) (\w+)', pb)
            pat = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?', pb)
            psz = re.search(r'\(size\s+([\d.]+)\s+([\d.]+)', pb)
            pnet = re.search(r'\(net (\d+) "([^"]*)"\)', pb)
            if not (num and pat and psz):
                continue
            px, py = float(pat.group(1)), float(pat.group(2))
            # KiCad board space has Y down, so a positive angle maps
            # (x, y) to (x cos + y sin, -x sin + y cos).
            ax = fx + px * ca + py * sa
            ay = fy - px * sa + py * ca
            w, h = float(psz.group(1)), float(psz.group(2))
            # The pad's own rotation is absolute in the file, so it already
            # includes the footprint's.
            pang = math.radians(float(pat.group(3) or 0)
                                if pat.lastindex and pat.lastindex >= 3
                                else 0.0)
            layers = re.search(r'\(layers([^)]*)\)', pb)
            front = ('*.Cu' in (layers.group(1) if layers else '')
                     or 'F.Cu' in (layers.group(1) if layers else ''))
            pads.append({
                'ref': ref.group(1), 'num': num.group(1),
                'type': num.group(2), 'x': ax, 'y': ay,
                'r': math.hypot(w, h) / 2.0,
                'w': w, 'h': h, 'ang': pang,
                'net': pnet.group(2) if pnet else '',
                'tht': num.group(2) != 'smd',
                'front': front or num.group(2) != 'smd'})
    w = max(xs) if xs else 230.0
    h = 200.0
    hm = [float(m.group(1)) for m in
          re.finditer(r'\(gr_line \(start [\d.]+ ([\d.]+)\) \(end', s)]
    if hm:
        h = max(hm)
    return s, w, h, pads


# Route one section at a time instead of taking the whole board shortest-first.
# Shortest-first is a reasonable default and a poor plan: it lets a stray 0603
# in a far corner claim space before the 24 V rail has been laid, and it leaves
# every section half-finished while the board fills up. Working section by
# section gives each circuit a clean area to be routed in, and the sections that
# matter most get first claim on it.
#
# Power goes early, but after the differential pairs. The pairs are the most
# constrained thing on the board - two tracks that have to travel together over
# 80 mm - and they have no freedom to detour. A power rail is a mesh that can go
# almost any way round and still be a good power rail, so it loses less by
# waiting one step.
SECTION_ORDER = ('power', 'relaydrv', 'buffers', 'inputs', 'switch',
                 'mcu', 'edge', 'other')

POWER_NETS_FIRST = ('V24', '+5V')


def load_sections():
    """{reference: section name}, from the same rules the placement used."""
    import importlib
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    bp = importlib.import_module('build_pcb')
    rules = [(n, re.compile(pat)) for n, _rect, pat in bp.GROUPS]
    edge = set()
    for _side, _lo, _hi, refs in bp.EDGES:
        edge.update(refs)
    comps = bp.read_netlist()
    out = {}
    for ref in comps:
        if ref in edge:
            out[ref] = 'edge'
            continue
        out[ref] = 'other'
        for name, pat in rules:
            if pat.match(ref):
                out[ref] = name
                break
    return out


def domain_of(_x):
    """Which side of the isolation barrier a coordinate is on.

    MACH3SIMPLE has no barrier: one ground, one domain, copper may go anywhere.
    Answering the same everywhere satisfies both the crossing test and the via
    test in the search loop without special-casing either, and leaves one place
    to change if isolation is ever added back.
    """
    return 'machine'


VIA_COST = 600              # in the same units as a 0.25 mm step (10), so 15 mm
VIA_R = 0.4                 # via pad radius, mm

# Obstacles are inflated by this much, and the router then only has to ask
# whether the cell under the track's centre line is free.
#
# Getting this wrong is not subtle. The first version inflated pads by the
# clearance alone and tested the centre cell, which says nothing about where the
# copper actually ends: a track centred 0.25 mm from a pad has its edge 0.125 mm
# away, and two tracks in neighbouring cells touch. That produced 199 shorts and
# 499 clearance errors from a router that believed it had succeeded. KEEP is the
# clearance plus the widest half-track on the board, so a centre line this far
# from foreign copper always leaves at least the clearance between the edges.
# KiCad's default board-edge clearance. The router clamped its search to the
# grid, which is the outline itself, so it happily laid copper right up to the
# cut line - three violations that no amount of clearance between nets would
# ever have caught.
EDGE_CLEAR = 0.5

MAXHALF = POWER_W / 2.0
# The half grid step is margin: the router samples cell centres, and the track
# between two of them passes slightly closer to a corner than either sample does.
KEEP = CLEARANCE + MAXHALF + GRID / 2.0


class Grid:
    """Occupancy on both copper layers. Layer 0 is F.Cu, layer 1 is B.Cu."""

    def __init__(self, w, h):
        self.nx = int(w / GRID) + 1
        self.ny = int(h / GRID) + 1
        self.n = self.nx * self.ny
        self.cell = bytearray(self.n * 2)
        self.owner = {}          # index -> net name, for cells that are taken
        # Cells no via may occupy. A through-hole pad's own net counts as free
        # for a track, which let a via be placed straight down a pad's hole -
        # two drills in the same place, which is how holes_co_located appeared.
        self.novia = set()
        # Cells inside the corridor the first half of a differential pair took.
        # Its partner pays a penalty for every step outside this.
        self.corridor = bytearray(self.n)
        # Cells held for one net while another routes past. Unlike a stamp this
        # never blocks the net it belongs to and never turns a contested cell
        # into one nobody may use - the first attempt at reserving space for a
        # pair's second half used stamp_pad, which does both, and sealed in the
        # very net it was supposed to protect. Pairs went from six to none.
        self.reserved = {}

    def idx(self, ix, iy, layer):
        return layer * self.n + iy * self.nx + ix

    def stamp(self, x, y, r, net, layers=(0, 1)):
        """Mark a disc as occupied by `net` on the given layers."""
        r2 = r * r
        i0 = max(0, int((x - r) / GRID))
        i1 = min(self.nx - 1, int((x + r) / GRID) + 1)
        j0 = max(0, int((y - r) / GRID))
        j1 = min(self.ny - 1, int((y + r) / GRID) + 1)
        for iy in range(j0, j1 + 1):
            dy = iy * GRID - y
            for ix in range(i0, i1 + 1):
                dx = ix * GRID - x
                if dx * dx + dy * dy <= r2:
                    for L in layers:
                        k = self.idx(ix, iy, L)
                        self.cell[k] = 1
                        # A cell inside two different nets' keep-out discs
                        # belongs to neither. Simply assigning the owner let the
                        # second stamp hand the cell to its own net, so a track
                        # could be routed straight through a neighbouring pad
                        # that had been stamped first - which is where the last
                        # handful of shorts and clearance errors came from.
                        prev = self.owner.get(k, net)
                        self.owner[k] = net if prev == net else None

    def block_via(self, x, y, r):
        """Mark cells where a via may not go, whatever net owns them."""
        n = int(r / GRID) + 1
        for dy in range(-n, n + 1):
            for dx in range(-n, n + 1):
                if dx * dx + dy * dy > n * n:
                    continue
                jx, jy = int(x / GRID) + dx, int(y / GRID) + dy
                if 0 <= jx < self.nx and 0 <= jy < self.ny:
                    self.novia.add(jy * self.nx + jx)

    def mark_corridor(self, path, width):
        """Flag the cells within `width` mm of a routed path."""
        self.corridor = bytearray(self.n)
        n = int(width / GRID) + 1
        for ix, iy, _L in path:
            for dy in range(-n, n + 1):
                for dx in range(-n, n + 1):
                    if dx * dx + dy * dy > n * n:
                        continue
                    jx, jy = ix + dx, iy + dy
                    if 0 <= jx < self.nx and 0 <= jy < self.ny:
                        self.corridor[jy * self.nx + jx] = 1

    def stamp_pad(self, pad, r, layers=(0, 1)):
        """Mark every cell within r of the pad's actual rectangle.

        Treating a pad as a circle of its own diagonal is the difference
        between a routable board and an unroutable one. A SOIC pad is
        1.55 x 0.6 mm; as a circle it becomes 1.66 mm across, so once the
        keep-out is added the dead zones of neighbouring pins on a 1.27 mm
        pitch overlap - and because a cell claimed by two nets belongs to
        neither, every pin on every fine-pitch package ends up sealed inside
        its own exclusion zone with no way out. That is what stopped the
        differential pairs leaving their driver at all.
        """
        x, y, w, h = pad['x'], pad['y'], pad['w'], pad['h']
        hw, hh = w / 2.0, h / 2.0
        ca, sa = math.cos(pad['ang']), math.sin(pad['ang'])
        ext = math.hypot(hw, hh) + r
        r2 = r * r
        i0 = max(0, int((x - ext) / GRID))
        i1 = min(self.nx - 1, int((x + ext) / GRID) + 1)
        j0 = max(0, int((y - ext) / GRID))
        j1 = min(self.ny - 1, int((y + ext) / GRID) + 1)
        net = pad['net']
        for iy in range(j0, j1 + 1):
            for ix in range(i0, i1 + 1):
                dx = ix * GRID - x
                dy = iy * GRID - y
                # Into the pad's own frame. Board space is Y-down, which is
                # why the sign of the sine terms is the way it is.
                lx = dx * ca - dy * sa
                ly = dx * sa + dy * ca
                qx = abs(lx) - hw
                qy = abs(ly) - hh
                if qx < 0:
                    qx = 0.0
                if qy < 0:
                    qy = 0.0
                if qx * qx + qy * qy > r2:
                    continue
                for L in layers:
                    k = self.idx(ix, iy, L)
                    self.cell[k] = 1
                    prev = self.owner.get(k, net)
                    self.owner[k] = net if prev == net else None

    def block_back(self, x1, y1, x2, y2):
        """Keep B.Cu clear over this rectangle, and keep vias out of it.

        The strip behind a row of edge connectors is where the ground pour has
        to stay whole: a back-side track through it cuts the pour into islands,
        and a terminal's ground pin then thermals onto a piece of copper that
        reaches nothing. KiCad calls that a starved thermal, and one appeared
        behind the Y axis terminal.

        Only the back is barred. The front is where these connections want to
        run anyway, so this costs the router very little.
        """
        for iy in range(max(0, int(y1 / GRID)),
                        min(self.ny - 1, int(y2 / GRID)) + 1):
            for ix in range(max(0, int(x1 / GRID)),
                            min(self.nx - 1, int(x2 / GRID)) + 1):
                k = self.idx(ix, iy, 1)
                self.cell[k] = 1
                self.owner[k] = None
                self.novia.add(iy * self.nx + ix)

    def block_border(self, w, h, margin):
        """Bar copper within `margin` of the board outline."""
        n = int(margin / GRID) + 1
        for iy in range(self.ny):
            for ix in range(self.nx):
                if (ix < n or iy < n
                        or ix * GRID > w - margin or iy * GRID > h - margin):
                    for L in (0, 1):
                        k = self.idx(ix, iy, L)
                        self.cell[k] = 1
                        self.owner[k] = None
                    self.novia.add(iy * self.nx + ix)

    def reserve(self, pad, r, net):
        """Hold the space around a pad for `net` while something else routes."""
        x, y, w, h = pad['x'], pad['y'], pad['w'], pad['h']
        hw, hh = w / 2.0, h / 2.0
        ca, sa = math.cos(pad['ang']), math.sin(pad['ang'])
        ext = math.hypot(hw, hh) + r
        r2 = r * r
        for iy in range(max(0, int((y - ext) / GRID)),
                        min(self.ny - 1, int((y + ext) / GRID) + 1) + 1):
            for ix in range(max(0, int((x - ext) / GRID)),
                            min(self.nx - 1, int((x + ext) / GRID) + 1) + 1):
                dx, dy = ix * GRID - x, iy * GRID - y
                lx = dx * ca - dy * sa
                ly = dx * sa + dy * ca
                qx = max(abs(lx) - hw, 0.0)
                qy = max(abs(ly) - hh, 0.0)
                if qx * qx + qy * qy <= r2:
                    self.reserved.setdefault(iy * self.nx + ix, net)

    def free(self, ix, iy, layer, net):
        k = self.idx(ix, iy, layer)
        if self.reserved.get(iy * self.nx + ix, net) != net:
            return False
        return not self.cell[k] or self.owner.get(k) == net

    def disc_free(self, ix, iy, r, net):
        """Both layers clear of other nets within r of this cell.

        A via is a hole through everything, so unlike a track it has to be clear
        on the front and the back at once, and over its whole pad rather than at
        one point.
        """
        n = int(r / GRID) + 1
        for dy in range(-n, n + 1):
            for dx in range(-n, n + 1):
                if dx * dx + dy * dy > n * n:
                    continue
                jx, jy = ix + dx, iy + dy
                if not (0 <= jx < self.nx and 0 <= jy < self.ny):
                    return False
                if jy * self.nx + jx in self.novia:
                    return False
                if not (self.free(jx, jy, 0, net) and self.free(jx, jy, 1, net)):
                    return False
        return True


# What one step off the partner's corridor costs. Less than a step, so the
# search still prefers a short route over a slavishly parallel one; enough that
# it will go a good way round to stay beside its partner.
STRAY = 12


def track_width(net, a, b):
    """Width for this connection, capped by the pads at its two ends.

    The first and last cell of a route sit on their own pad and are exempt from
    the occupancy test - they have to be, or nothing could leave a pad at all.
    That exemption is also a blind spot: a 0.6 mm power track reaching the
    centre of a 0.55 mm TQFP pad ends up nearer the neighbouring pin than the
    pad itself is, and the router never sees it. One GND stub into an ATmega
    came out at 0.175 mm against a 0.2 mm rule that way.

    Capping the width at the narrowest pad the track terminates on makes it no
    worse than the copper it is soldered to, which is legal by construction,
    and costs nothing anywhere else: a power rail between two terminal blocks
    still gets its full 0.6 mm.
    """
    w = POWER_W if net in POWER_NETS else DEFAULT_W
    for p in (a, b):
        # Room for the clearance on both sides as well as the copper. Capping
        # at the pad's own width is not enough: a 0.55 mm track leaving a
        # 0.55 mm TQFP pad is legal where it lands and 0.15 mm from the
        # neighbouring pin a fifth of a millimetre further along, which is
        # where the second of these violations came from.
        w = min(w, max(min(p['w'], p['h']) - 2 * CLEARANCE, DEFAULT_W))
    return w


def route_one(grid, a, b, net, half, limit_cells, follow=False,
              via_cost=None, window=24):
    """A* from pad a to pad b on the front layer. Returns a cell path or None."""
    sx, sy = int(round(a['x'] / GRID)), int(round(a['y'] / GRID))
    tx, ty = int(round(b['x'] / GRID)), int(round(b['y'] / GRID))
    if (sx, sy) == (tx, ty):
        return []
    # A surface-mount pad exists only on the front, so a route to one has to
    # arrive there; a through-hole pad can be met on either layer.
    start_layers = (0,) if not a.get('tht') else (0, 1)
    end_layers = (0,) if not b.get('tht') else (0, 1)
    via_cost = VIA_COST if via_cost is None else via_cost
    # Search window: the bounding box plus room to go round obstacles. 6 mm is
    # enough for a local hop and nowhere near enough for a route that has to
    # leave a congested corner and come back, which is most of what fails.
    pad = window
    lo_x, hi_x = min(sx, tx) - pad, max(sx, tx) + pad
    lo_y, hi_y = min(sy, ty) - pad, max(sy, ty) + pad
    lo_x = max(1, lo_x); lo_y = max(1, lo_y)
    hi_x = min(grid.nx - 2, hi_x); hi_y = min(grid.ny - 2, hi_y)

    dom = domain_of(a['x'])
    steps = ((1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10),
             (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14))

    def h(ix, iy):
        return (abs(ix - tx) + abs(iy - ty)) * 10

    open_q, came, cost = [], {}, {}
    for L in start_layers:
        open_q.append((h(sx, sy), 0, sx, sy, L))
        cost[(sx, sy, L)] = 0
    heapq.heapify(open_q)
    seen = 0
    while open_q:
        _, g, ix, iy, L = heapq.heappop(open_q)
        if (ix, iy) == (tx, ty) and L in end_layers:
            path, cur = [], (tx, ty, L)
            while cur in came:
                path.append(cur)
                cur = came[cur]
            path.append(cur)
            path.reverse()
            return path
        if g > cost.get((ix, iy, L), 1 << 30):
            continue
        seen += 1
        if seen > limit_cells:
            return None
        for dx, dy, w in steps:
            nx_, ny_ = ix + dx, iy + dy
            if not (lo_x <= nx_ <= hi_x and lo_y <= ny_ <= hi_y):
                continue
            # Never let a route wander out of its own domain.
            if domain_of(nx_ * GRID) not in (dom, 'barrier'):
                continue
            if not grid.free(nx_, ny_, L, net):
                continue
            # A diagonal step is a real 45 degree track, and it passes through
            # the corner between the two cells it steps around. Testing only
            # where it lands lets it shave copper that sits on that corner.
            if dx and dy and not (grid.free(ix + dx, iy, L, net)
                                  and grid.free(ix, iy + dy, L, net)):
                continue
            ng = g + w
            if follow and not grid.corridor[ny_ * grid.nx + nx_]:
                ng += STRAY
            if ng < cost.get((nx_, ny_, L), 1 << 30):
                cost[(nx_, ny_, L)] = ng
                came[(nx_, ny_, L)] = (ix, iy, L)
                heapq.heappush(open_q, (ng + h(nx_, ny_), ng, nx_, ny_, L))
        # Change layer. Expensive, and barred inside the isolation band.
        other = 1 - L
        if (domain_of(ix * GRID) != 'barrier'
                and grid.disc_free(ix, iy, VIA_R + KEEP, net)
                and cost.get((ix, iy, other), 1 << 30) > g + via_cost):
            cost[(ix, iy, other)] = g + via_cost
            came[(ix, iy, other)] = (ix, iy, L)
            heapq.heappush(open_q,
                           (g + via_cost + h(ix, iy), g + via_cost,
                            ix, iy, other))
    return None


def simplify(path):
    """Drop collinear points so the board gets a few segments, not hundreds."""
    if len(path) < 3:
        return path
    out = [path[0]]
    for i in range(1, len(path) - 1):
        ax, ay, al = path[i - 1]
        bx, by, bl = path[i]
        cx, cy, cl = path[i + 1]
        if al != bl or bl != cl or (bx - ax, by - ay) != (cx - bx, cy - by):
            out.append(path[i])
    out.append(path[-1])
    return out


def main():
    max_len = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    text, bw, bh, pads = read_board(BOARD)
    print('board    : %.0f x %.0f mm, %d pads' % (bw, bh, len(pads)))

    nets = {}
    for p in pads:
        if p['net'] and p['front']:
            nets.setdefault(p['net'], []).append(p)

    grid = Grid(bw, bh)
    grid.block_border(bw, bh, EDGE_CLEAR + MAXHALF + GRID / 2.0)
    # The strips the edge connectors sit in, on the back only.
    EDGE_STRIP = 12.0
    grid.block_back(bw - EDGE_STRIP, 0.0, bw, bh)
    grid.block_back(0.0, bh - EDGE_STRIP, bw, bh)
    for p in pads:
        if not p['front']:
            continue
        grid.stamp_pad(p, KEEP, (0, 1) if p['tht'] else (0,))
        if p['tht']:
            grid.block_via(p['x'], p['y'], p['r'] + 0.5)

    net_ids = {}
    for m in re.finditer(r'\(net (\d+) "([^"]*)"\)', text):
        net_ids[m.group(2)] = int(m.group(1))

    # Shortest connections first: they are the local ones, they are the ones
    # worth doing automatically, and finishing them frees space rather than
    # consuming it.
    jobs = []
    for net, ps in nets.items():
        if net in ('GND_M', 'GND_PC'):
            continue            # the pours already carry these
        # Minimum spanning tree over the net's pads.
        rest = ps[1:]
        tree = [ps[0]]
        while rest:
            best = min(((math.hypot(a['x'] - b['x'], a['y'] - b['y']), a, b)
                        for a in tree for b in rest), key=lambda t: t[0])
            d, a, b = best
            jobs.append((d, net, a, b))
            tree.append(b)
            rest.remove(b)
    # Section first, then shortest within the section. A connection whose two
    # ends are in different sections waits until both have been laid out.
    sections = load_sections()
    rank = {n: i for i, n in enumerate(SECTION_ORDER)}

    def section_of(job):
        _d, net, pa, pb = job
        if net in POWER_NETS_FIRST:
            return -1
        # Everything else goes shortest-first across the whole board.
        #
        # Working section by section was tried and measured worse: 386 routed
        # against 405. Sections here are placement rectangles, but the signal
        # flow on this board runs BETWEEN them - optocoupler to pull-up to line
        # driver to terminal is three groups - so most real connections are
        # crossings, and deferring crossings to last hands the leftover space to
        # the connections that matter most. 83 of them were still unrouted.
        #
        # Power first survives that result on its own merits: it claimed 184
        # connections while the board was empty, so the rails are direct and
        # wide, and it costs the rest almost nothing.
        return 0

    jobs.sort(key=lambda j: (section_of(j), j[0]))

    # The differential pairs come first, while there is still room to put them
    # side by side. Left to the usual shortest-first order they would be routed
    # last - they are among the longest runs on the board - and by then the
    # corridor they need is full of everything else.
    pairs = []
    for net in sorted(nets):
        m = re.match(r'^(.*)_P$', net)
        if not m or (m.group(1) + '_N') not in nets:
            continue
        pn = m.group(1) + '_N'
        # Route driver to terminal; the fail-safe bias resistor taps on after.
        def ends(ps):
            u = [q for q in ps if q['ref'].startswith('U')]
            j = [q for q in ps if q['ref'].startswith('J')]
            return (u[0], j[0]) if u and j else None
        ep, en = ends(nets[net]), ends(nets[pn])
        if ep and en:
            pairs.append((net, pn, ep, en))

    segs, vias, done, skipped, failed, back = [], [], 0, 0, 0, 0
    paired, pair_lengths, retry, by_section = 0, [], [], {}

    def emit(path, net, width):
        """Turn a cell path into copper and make it an obstacle."""
        nonlocal back
        pts = simplify(path)
        for (x1, y1, l1), (x2, y2, l2) in zip(pts, pts[1:]):
            if l1 != l2:
                vias.append((x1 * GRID, y1 * GRID, net_ids.get(net, 0)))
                grid.stamp(x1 * GRID, y1 * GRID, VIA_R + KEEP, net)
                grid.block_via(x1 * GRID, y1 * GRID, VIA_R + 0.5)
                continue
            segs.append((x1 * GRID, y1 * GRID, x2 * GRID, y2 * GRID,
                         width, net_ids.get(net, 0), l1))
            if l1 == 1:
                back += 1
        for ix, iy, L in path:
            grid.stamp(ix * GRID, iy * GRID, width / 2.0 + KEEP, net, (L,))

    def length_mm(path):
        t = 0.0
        for (x1, y1, _a), (x2, y2, _b) in zip(path, path[1:]):
            t += math.hypot(x2 - x1, y2 - y1) * GRID
        return t

    for np_, nn_, (up, jp), (un, jn) in pairs:
        w = DEFAULT_W
        # The two halves of a pair leave adjacent pins - an AM26LS31's Y and Z
        # are pins 2 and 3 - so the first one routed can seal the second one
        # inside its own package. Reserving room around the partner's pads was
        # tried and made it strictly worse: any reservation large enough to
        # matter also covers the neighbouring pin, so the FIRST half could not
        # leave its own pad either, and all twelve pairs failed instead of six.
        # Measured, not reasoned: with no reservation six pairs route, and the
        # order they are attempted in changes nothing (6 alphabetical, 6 longest
        # first, 4 shortest first).
        pa = route_one(grid, up, jp, np_, w / 2.0 + KEEP, 120000, window=60)
        if not pa:
            failed += 1
            continue
        emit(pa, np_, w)
        grid.mark_corridor(pa, 1.5)
        pb = route_one(grid, un, jn, nn_, w / 2.0 + KEEP, 120000, follow=True,
                       window=60)
        if not pb:
            failed += 1
            done += 1
            continue
        emit(pb, nn_, w)
        grid.corridor = bytearray(grid.n)
        done += 2
        paired += 1
        pair_lengths.append((np_[:-2], length_mm(pa), length_mm(pb)))

    routed_pairs = {n for p in pairs for n in (p[0], p[1])}

    for d, net, a, b in jobs:
        if (net in routed_pairs
                and a['ref'][0] in 'UJ' and b['ref'][0] in 'UJ'):
            continue                    # already laid as half of a pair
        if d > max_len:
            skipped += 1
            continue
        width = track_width(net, a, b)
        half = width / 2.0 + KEEP
        sec = section_of((d, net, a, b))
        name = 'power' if sec < 0 else sections.get(a['ref'], 'other')
        by_section.setdefault(name, [0, 0])
        path = route_one(grid, a, b, net, half, 40000)
        if path is None:
            retry.append((net, a, b, width, half, name))
            by_section[name][1] += 1
            continue
        emit(path, net, width)
        by_section[name][0] += 1
        done += 1

    # Second pass over everything the first could not place. The first pass is
    # deliberately mean: a small search window and a via priced at 15 mm of
    # track, because the back copper is a ground plane and every via cuts a slot
    # in it. That is the right default and the wrong last word - a connection
    # left unrouted is not free either, it is work handed back. So the leftovers
    # get a window wide enough to leave a congested corner and come back, and a
    # via priced at 3 mm instead of 15.
    second = 0
    for net, a, b, width, half, name in retry:
        path = route_one(grid, a, b, net, half, 200000,
                         via_cost=120, window=110)
        if path is None:
            failed += 1
            continue
        emit(path, net, width)
        by_section[name][0] += 1
        by_section[name][1] -= 1
        done += 1
        second += 1

    import uuid
    body = []
    for x1, y1, x2, y2, w, n, L in segs:
        body.append('\t(segment (start %.4f %.4f) (end %.4f %.4f) (width %s)'
                    ' (layer "%s") (net %d) (uuid "%s"))'
                    % (x1, y1, x2, y2, w, 'F.Cu' if L == 0 else 'B.Cu',
                       n, uuid.uuid4()))
    for x, y, n in vias:
        body.append('\t(via (at %.4f %.4f) (size 0.8) (drill 0.4)'
                    ' (layers "F.Cu" "B.Cu") (net %d) (uuid "%s"))'
                    % (x, y, n, uuid.uuid4()))

    i = text.rstrip().rfind(')')
    out = text[:i] + '\n'.join(body) + '\n' + text[i:]
    with open(BOARD, 'w', encoding='utf-8', newline='') as f:
        f.write(out)

    total = done + failed + skipped
    print('connections: %d needing copper (ground pours excluded)' % total)
    print('  routed   : %d' % done)
    print('  too long : %d  (over %.0f mm - left for the interactive router)'
          % (skipped, max_len))
    print('  on retry : %d  (wider search, cheaper via)' % second)
    print('  by section:')
    for name in ('power',) + SECTION_ORDER + ('crossing',):
        if name in by_section:
            ok, bad = by_section.pop(name)
            print('     %-10s %4d routed  %4d left'
                  % (name, ok, max(bad, 0)))
    print('  no path  : %d' % failed)
    if pair_lengths:
        worst = max(abs(a - b) for _n, a, b in pair_lengths)
        print('diff pairs: %d of %d routed together, worst length mismatch %.1f mm'
              % (paired, len(pairs), worst))
        for n, la, lb in pair_lengths:
            print('           %-12s %6.1f / %6.1f mm  (%+.1f)'
                  % (n, la, lb, lb - la))
    print('copper   : %d segments, %d vias  (%d segments on the back, %.0f%%)'
          % (len(segs), len(vias), back,
             100.0 * back / len(segs) if segs else 0))
    print('written  : %s' % BOARD)


if __name__ == '__main__':
    main()
