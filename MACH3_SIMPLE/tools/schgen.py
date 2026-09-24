#!/usr/bin/env python3
"""Emit KiCad 10 hierarchical schematics from Python.

Design notes, mostly learned the hard way on the EC9 project:

* **Everything lands on the 1.27 mm grid.** EC9 was generated on integer
  millimetre origins, which is not a multiple of 1.27, so all 2453 of its
  connectable endpoints were off-grid and had to be snapped afterwards. Here
  `snap()` is applied to every coordinate at emit time, and placements are
  chosen as grid multiples to begin with.
* **Symbols come from KiCad's validated libraries** via `kilib`, never
  hand-drawn. A hand-made 74HC123 with a wrong pin numbering silently broke the
  EC9 watchdog and ERC could not catch it, because the same wrong assumption set
  both the pin numbers and the pin types ERC checks against.
* **Connections are by global label**, not by routed wire geometry. Each pin gets
  a short stub wire to a label. This keeps generation robust and diffable, and
  is the idiom the EC9 sheets already use.
"""
import math
import os
import re
import uuid

import kilib

GRID = 1.27


def snap(v):
    """Nearest 1.27 mm grid point. floor(v/g+0.5) keeps ties shift-invariant."""
    return round(math.floor(v / GRID + 0.5) * GRID, 6)


def fmt(v):
    return ('%.4f' % v).rstrip('0').rstrip('.') or '0'


def esc(s):
    """Escape a string being emitted inside a quoted s-expression token.

    Not cosmetic. A note reading `SendSerial("A")` was written out with its
    inner quotes bare, which ended the token early and made 06_serial.kicad_sch
    unparseable. KiCad then dropped the whole sheet **silently**: ERC still
    reported 0 violations and the netlist simply lacked all 64 parts - the MCU,
    the relays, the RS232 transceiver. Every caller-supplied string goes through
    here so that cannot happen again.
    """
    return str(s).replace('\\', '\\\\').replace('"', '\\"')


def uid():
    return str(uuid.uuid4())


class Placed:
    """One placed symbol; knows where each of its pins ended up."""

    def __init__(self, sheet, lib, name, ref, value, x, y, footprint, fields,
                 unit=1, rot=0):
        self.sheet, self.lib, self.name = sheet, lib, name
        self.ref, self.value, self.unit = ref, value, unit
        self.x, self.y = snap(x), snap(y)
        self.rot = int(rot) % 360
        self.footprint = footprint if footprint is not None else (
            kilib.prop(lib, name, 'Footprint') or '')
        self.fields = fields or {}
        self.uuid = uid()
        # Multi-unit parts split their gates across units, so only this unit's
        # pins exist at this placement.
        # Take the BOM/board flags from the library symbol. Hard-coding
        # "in_bom yes" makes a mounting hole disagree with its own footprint,
        # which the board's schematic-parity check then reports.
        body = kilib.resolve(lib, name)
        self.in_bom = 'no' if '(in_bom no)' in body else 'yes'
        self.on_board = 'no' if '(on_board no)' in body else 'yes'
        self.dnp = 'no'         # set to 'yes' for a footprint left empty
        multi = len(kilib.units(lib, name)) > 1
        self.pins = kilib.pins(lib, name, unit=unit if multi else None)
        self._by_num = {p['num']: p for p in self.pins}
        self.used = set()
        self.nets = {}          # pin number -> net name, filled in by Sheet.net

    def at(self, num):
        """Absolute (x, y) of a pin, after the symbol's own rotation.

        Symbol space has Y up and the sheet has Y down, and KiCad rotates a
        symbol counter-clockwise in symbol space before that flip. Working the
        two together by eye is how pins end up a few millimetres from where the
        wire was drawn, which reads as a broken net and looks like a routing
        bug, so the four cases are written out rather than derived.
        """
        p = self._by_num[str(num)]
        px, py = p['x'], p['y']
        if self.rot == 90:
            return snap(self.x - py), snap(self.y - px)
        if self.rot == 180:
            return snap(self.x - px), snap(self.y + py)
        if self.rot == 270:
            return snap(self.x + py), snap(self.y + px)
        return snap(self.x + px), snap(self.y - py)

    def dir_of(self, num):
        """(dx, dy) the pin leaves along, in sheet space, after rotation."""
        p = self._by_num[str(num)]
        dx, dy = self._STUB.get(int(p['angle']) % 360,
                                (1, 0) if p['x'] >= 0 else (-1, 0))
        for _ in range(self.rot // 90):
            # Counter-clockwise, to match at(). Sheet space has Y down, so a
            # visual counter-clockwise turn takes (dx, dy) to (dy, -dx) - right
            # becomes up. Writing the other one sent every rotated pin's stub
            # out of the wrong side of its symbol, straight across whatever was
            # there: the switch node of the buck ended up merged into ground.
            dx, dy = dy, -dx
        return dx, dy

    # Stub direction in SHEET space (y down), keyed by the pin's own angle.
    # A KiCad pin's `at` is its connection end and its angle points from there
    # back into the symbol body, so the stub must run the opposite way.
    _STUB = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}

    def dirn(self, num):
        """(dx, dy) the stub wire should leave this pin along, in sheet space.

        Reading this off the pin's x sign instead - "left of centre means it
        exits left" - is wrong for any symbol with pins on its top or bottom
        edge, and it shorted every relay on this board: JQC-3FF pins 12 and 14
        both sit at y=+7.62 pointing down, so two horizontal stubs from them
        overlapped and tied NC to NO. The contacts would have done nothing.
        """
        return self.dir_of(num)

    def side(self, num):
        """-1 if the pin leaves to the left, +1 to the right."""
        return -1 if self._by_num[str(num)]['x'] < 0 else 1

    def pin_name(self, num):
        return self._by_num[str(num)]['name']

    def render(self):
        pins = ''.join('(pin "%s" (uuid "%s"))' % (p['num'], uid()) for p in self.pins)
        extra = ''.join(
            '(property "%s" "%s" (at %s %s 0) (effects (font (size 1 1)) hide))'
            % (esc(k), esc(v), fmt(self.x), fmt(self.y))
            for k, v in self.fields.items())
        return (
            '(symbol (lib_id "%s:%s") (at %s %s %d) (unit %d) (in_bom %s)'
            ' (on_board %s) (dnp %s) (uuid "%s")'
            '(property "Reference" "%s" (at %s %s 0) (effects (font (size 1.27 1.27))))'
            '(property "Value" "%s" (at %s %s 0) (effects (font (size 1.27 1.27))))'
            '(property "Footprint" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) hide))'
            '%s%s'
            '(instances (project "%s" (path "/%s/%s" (reference "%s") (unit %d)))))'
            % (self.lib, self.name, fmt(self.x), fmt(self.y), self.rot,
               self.unit, self.in_bom, self.on_board, self.dnp, self.uuid,
               esc(self.ref), fmt(self.x), fmt(self.y - 12.7),
               esc(self.value), fmt(self.x), fmt(self.y - 10.16),
               esc(self.footprint), fmt(self.x), fmt(self.y),
               extra, pins,
               self.sheet.project, self.sheet.root_uuid, self.sheet.uuid,
               esc(self.ref), self.unit))


def opto_pins(u):
    """(anode, cathode, collector, emitter) of one optocoupler channel.

    Resolved from the symbol's geometry, never from the order the pins happen to
    appear in. Unpacking `u.pins` positionally looks harmless and is what was
    here before, but PC847 unit 1 lists its pins as 1, 2, 15, 16 - so it made
    pin 15 the collector when pin 15 is the emitter. That tied every collector
    to GND_PC and every emitter to the pull-up, reverse-biasing the
    phototransistor on all ten isolated inputs: six home/E-stop sensors, THC up
    and down, and both MPG channels. No input would have reached Mach3.

    PC847 pins carry empty names, so there is no pin function to ask for. What
    the symbol does define is the drawing: the LED is the low-numbered pair and
    the transistor the high-numbered one, and anode and collector are the pins
    drawn at the top. That is what this reads.
    """
    led = sorted((q for q in u.pins if int(q['num']) <= 8), key=lambda q: -q['y'])
    tr = sorted((q for q in u.pins if int(q['num']) > 8), key=lambda q: -q['y'])
    if len(led) != 2 or len(tr) != 2:
        raise ValueError('%s: expected 2 LED and 2 transistor pins, got %d/%d'
                         % (u.ref, len(led), len(tr)))
    return led[0]['num'], led[1]['num'], tr[0]['num'], tr[1]['num']


class Sheet:
    """One .kicad_sch file."""

    def __init__(self, filename, title, project, root_uuid, sheet_uuid,
                 rev='A0 ENGINEERING ONLY', paper='A3'):
        self.filename, self.title = filename, title
        self.project, self.root_uuid, self.uuid = project, root_uuid, sheet_uuid
        self.rev, self.paper = rev, paper
        self.symbols, self.body, self.libs = [], [], {}
        # Every wire segment laid down so far, as (x1, y1, x2, y2, net). Two
        # collinear overlapping wires are one node in KiCad, and so is a wire
        # whose end lands on another wire - which is how six relays ended up
        # with NC tied to NO. `net()` consults this before committing a stub.
        self._segs = []
        self._anchors = {}
        self._pinpts = {}
        self._clashes = []

    # -- placement ---------------------------------------------------------
    def place(self, lib, name, ref, value, x, y, footprint=None, fields=None,
              unit=1, rot=0):
        self.libs[(lib, name)] = True
        p = Placed(self, lib, name, ref, value, x, y, footprint, fields, unit,
                   rot)
        self.symbols.append(p)
        for q in p.pins:
            self._pinpts[p.at(q['num'])] = '%s.%s' % (ref, q['num'])
        return p

    def place_all_units(self, lib, name, ref, value, positions, footprint=None,
                        fields=None):
        """Place every unit of a multi-unit part. `positions` maps unit -> (x, y).

        The last unit of a 74xx or op-amp symbol usually holds only VCC/GND, so
        it still has to be placed somewhere for those pins to exist.
        """
        return {u: self.place(lib, name, ref, value, xy[0], xy[1],
                              footprint=footprint, fields=fields, unit=u)
                for u, xy in positions.items()}

    # -- connections -------------------------------------------------------
    @staticmethod
    def _touches(a, b):
        """True if two segments would be one electrical node in KiCad.

        Crossing wires do not connect without a junction, so only collinear
        overlap and an endpoint landing on the other segment count.
        """
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        eps = 0.01

        def on(px, py, s):
            x1, y1, x2, y2 = s
            if abs((x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)) > eps:
                return False
            return (min(x1, x2) - eps <= px <= max(x1, x2) + eps
                    and min(y1, y2) - eps <= py <= max(y1, y2) + eps)

        if abs(ax1 - ax2) < eps and abs(bx1 - bx2) < eps and abs(ax1 - bx1) < eps:
            return (min(ay1, ay2) - eps < max(by1, by2)
                    and min(by1, by2) - eps < max(ay1, ay2))
        if abs(ay1 - ay2) < eps and abs(by1 - by2) < eps and abs(ay1 - by1) < eps:
            return (min(ax1, ax2) - eps < max(bx1, bx2)
                    and min(bx1, bx2) - eps < max(ax1, ax2))
        return (on(ax1, ay1, b) or on(ax2, ay2, b)
                or on(bx1, by1, a) or on(bx2, by2, a))

    def _clear(self, seg, net):
        """No segment of a different net would join this one."""
        for x1, y1, x2, y2, other in self._segs:
            if other != net and self._touches(seg, (x1, y1, x2, y2)):
                return False
        return True

    def wire(self, x1, y1, x2, y2, net=None):
        x1, y1, x2, y2 = snap(x1), snap(y1), snap(x2), snap(y2)
        self._segs.append((x1, y1, x2, y2,
                           net if net is not None else '#w%d' % len(self._segs)))
        self.body.append(
            '(wire (pts (xy %s %s)(xy %s %s)) (stroke (width 0) (type default))'
            ' (uuid "%s"))' % (fmt(x1), fmt(y1), fmt(x2), fmt(y2), uid()))

    def link(self, a, pa, b, pb, net=None, via_y=None):
        """Draw an orthogonal wire from one pin to another.

        This is what makes a sheet readable as a circuit rather than as a
        netlist: a fuse wired to the diode it feeds, not two labels that happen
        to share a name. Labels still carry the rails and anything that fans out
        widely, because a schematic that draws every ground connection as a wire
        is no easier to follow than one that draws none.
        """
        x1, y1 = a.at(pa)
        x2, y2 = b.at(pb)
        name = net or '#link%d' % len(self._segs)
        if abs(y1 - y2) < 0.01:
            self.wire(x1, y1, x2, y2, net=name)
        elif abs(x1 - x2) < 0.01:
            self.wire(x1, y1, x2, y2, net=name)
        else:
            # Break at a chosen height so the corner lands somewhere sensible
            # instead of always under whichever pin came first.
            my = snap(via_y) if via_y is not None else y2
            self.wire(x1, y1, x1, my, net=name)
            self.wire(x1, my, x2, my, net=name)
            self.wire(x2, my, x2, y2, net=name)
        a.used.add(str(pa))
        b.used.add(str(pb))
        if net and not net.startswith('#'):
            # Without a label KiCad names the net after whichever pin it found
            # first, so VIN_RAW comes back as Net-(J1-Pin_1) and the PWR_FLAG
            # that was meant to feed it is left attached to nothing.
            self.label(net, x2, y2, 0)
            self._anchors[(x2, y2)] = net
            a.nets[str(pa)] = net
            b.nets[str(pb)] = net

    def label(self, net, x, y, rot=0):
        self.body.append(
            '(global_label "%s" (shape passive) (at %s %s %d)'
            ' (effects (font (size 1.27 1.27)) (justify left)) (uuid "%s"))'
            % (esc(net), fmt(snap(x)), fmt(snap(y)), rot, uid()))

    def net(self, placed, num, name, stub=7.62):
        """Stub wire from a pin out to a global label, along the pin's own axis.

        The stub grows in 1.27 mm steps until it neither overlaps another net's
        wire nor lands on another net's label, so adding a part can no longer
        silently short two nets together.
        """
        x, y = placed.at(num)
        dx, dy = placed.dirn(num)
        rot = {(-1, 0): 0, (1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        mine = '%s.%s' % (placed.ref, num)

        def free(lx, ly, segs):
            return (self._anchors.get((lx, ly), name) == name
                    and self._pinpts.get((lx, ly)) in (None, mine)
                    and all(self._clear(sg, name) for sg in segs))

        # Straight out along the pin's own axis: what you want whenever it fits.
        run, chosen = None, None
        for k in range(0, 24):
            lx, ly = snap(x + dx * (stub + k * GRID)), snap(y + dy * (stub + k * GRID))
            if free(lx, ly, [(x, y, lx, ly)]):
                chosen, run = [(x, y, lx, ly)], (lx, ly)
                break
        # Otherwise jog: a short lead along the pin axis, then off sideways.
        # Densely stacked parts - ten 6N137s in a column, all wanting +5V_M out
        # of pin 8 - leave no room straight ahead, and a stub that gives up and
        # overlaps its neighbour silently merges two nets.
        if run is None:
            px, py = (0, 1) if dx else (1, 0)
            for lead in (2.54, 1.27, 3.81, 5.08, 7.62):
                mx, my = snap(x + dx * lead), snap(y + dy * lead)
                for sgn in (1, -1):
                    for k in range(2, 20):
                        lx = snap(mx + px * sgn * k * GRID)
                        ly = snap(my + py * sgn * k * GRID)
                        segs = [(x, y, mx, my), (mx, my, lx, ly)]
                        if free(lx, ly, segs):
                            chosen, run = segs, (lx, ly)
                            rot = 180 if (px * sgn if px else py * sgn) > 0 else 0
                            if py:
                                rot = 270 if sgn > 0 else 90
                            break
                    if run:
                        break
                if run:
                    break
        if run is None:
            run = (snap(x + dx * stub), snap(y + dy * stub))
            chosen = [(x, y, run[0], run[1])]
            self._clashes.append('%s pin %s -> %s' % (placed.ref, num, name))
        for sg in chosen:
            self.wire(sg[0], sg[1], sg[2], sg[3], net=name)
        self._anchors[run] = name
        self.label(name, run[0], run[1], rot)
        placed.used.add(str(num))
        placed.nets[str(num)] = name

    def nc(self, placed, num):
        x, y = placed.at(num)
        self.body.append('(no_connect (at %s %s) (uuid "%s"))'
                         % (fmt(x), fmt(y), uid()))
        placed.used.add(str(num))

    def nc_rest(self, placed):
        """No-connect every pin not yet wired - keeps ERC honest."""
        for p in placed.pins:
            if p['num'] not in placed.used:
                self.nc(placed, p['num'])

    RAILS = ('+5V_M', '+5V_PC', 'V24')
    GROUNDS = ('GND_M', 'GND_PC')

    def decouple(self, first, cap='100nF', footprint=None, rails=None,
                 at=None, per_row=12, pitch=(27.94, 30.48)):
        """One local bypass cap per IC supply pin, in a column below the sheet.

        The board had bulk capacitors on each rail and nothing at all beside any
        logic IC. That is not a tidiness point: a 6N137's datasheet requires a
        0.1 uF between pins 8 and 5 because its output stage switches hard, and
        an ATmega or an AM26LS31 with no bypass is exactly what turns VFD noise
        into false steps. Schematically the cap only needs the right two nets;
        keeping it physically next to its IC is the layout's job, so the value
        carries the owning reference into the BOM and the placement pass.
        """
        rails = rails or self.RAILS
        if at:
            x, y = at
        else:
            x = 25.4
            y = max([p.y for p in self.symbols] or [100.0]) + 38.1
            self.text('LOCAL DECOUPLING - one per IC supply pin. Each must be',
                      x, y - 20.32)
            self.text('placed within a few mm of the pin it names, on the PCB.',
                      x, y - 15.24)
        x0, n, seen = x, 0, set()
        for p in sorted(self.symbols, key=lambda q: q.ref):
            if not p.ref.startswith('U'):
                continue
            sup = sorted({v for v in p.nets.values() if v in rails})
            gnd = sorted({v for v in p.nets.values() if v in self.GROUNDS})
            if not sup or not gnd:
                continue
            for rail in sup:
                # Pair each supply with the ground of its own domain.
                g = 'GND_PC' if rail.endswith('_PC') else 'GND_M'
                if g not in gnd:
                    g = gnd[0]
                if (p.ref, rail, g) in seen:
                    continue
                seen.add((p.ref, rail, g))
                c = self.place('Device', 'C', 'C%d' % (first + n),
                               '%s %s' % (cap, p.ref),
                               x0 + (n % per_row) * pitch[0],
                               y + (n // per_row) * pitch[1],
                               footprint=footprint)
                self.net(c, 1, rail)
                self.net(c, 2, g)
                n += 1
        return n

    def box(self, x1, y1, x2, y2, title=None, size=2.0):
        """A dashed rectangle round a functional block, with a heading.

        A sheet reads as a circuit only if the eye can find where one job ends
        and the next begins. Without these, a page of correctly drawn parts is
        still a page you have to trace with a finger.
        """
        self.body.append(
            '(rectangle (start %s %s) (end %s %s)'
            ' (stroke (width 0.2) (type dash)) (fill (type none))'
            ' (uuid "%s"))'
            % (fmt(snap(x1)), fmt(snap(y1)), fmt(snap(x2)), fmt(snap(y2)),
               uid()))
        if title:
            self.text(title, x1 + 2.54, y1 - 2.54, size)

    def text(self, s, x, y, size=1.27):
        self.body.append(
            '(text "%s" (at %s %s 0) (effects (font (size %s %s)) (justify left))'
            ' (uuid "%s"))' % (esc(s), fmt(snap(x)), fmt(snap(y)), size, size, uid()))

    # -- output ------------------------------------------------------------
    # Landscape width x height, largest last so the first fit is the smallest.
    PAPERS = (('A4', 297.0, 210.0), ('A3', 420.0, 297.0), ('A2', 594.0, 420.0),
              ('A1', 841.0, 594.0), ('A0', 1189.0, 841.0))
    # Border, plus the title block in the bottom right corner.
    FRAME = 24.0

    def paper_for(self, content):
        """Smallest sheet size the drawing actually fits on.

        Left at a fixed A3 this generator produced sheets 654 mm tall. KiCad does
        not complain and neither does ERC - the parts are simply drawn past the
        frame, so the PDF and the Eeschema page show maybe half the circuit and
        the rest is only findable by scrolling into empty space. Five of the
        seven sheets were in that state.
        """
        xs, ys = [], []
        for m in re.finditer(r'\((?:at|xy) (-?[\d.]+) (-?[\d.]+)', content):
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
        if not xs:
            return self.paper, ''
        w, h = max(xs) + self.FRAME, max(ys) + self.FRAME
        for name, pw, ph in self.PAPERS:
            if w <= pw and h <= ph:
                return name, ''
            if w <= ph and h <= pw:
                return name, ' portrait'
        return 'A0', ' portrait' if h > w else ''

    def render(self):
        libs = ''.join(kilib.embedded(l, n) for (l, n) in sorted(self.libs))
        content = ''.join(self.body) + ''.join(s.render() for s in self.symbols)
        # Measure the drawing, not the embedded library symbols: those carry
        # their own local coordinates and would size every sheet at A4.
        paper, orient = self.paper_for(content)
        self.paper = paper
        return ('(kicad_sch (version 20231120) (generator "eeschema")'
                ' (uuid "%s") (paper "%s"%s)'
                '(title_block (title "%s") (rev "%s"))'
                '(lib_symbols %s)%s)'
                % (self.uuid, paper, orient, esc(self.title), esc(self.rev),
                   libs, content))

    def write(self, outdir):
        path = os.path.join(outdir, self.filename)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(self.render())
        return path
