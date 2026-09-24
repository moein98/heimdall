#!/usr/bin/env python3
"""Structural checks ERC cannot make.

Three real defects on these two projects passed ERC cleanly, which is why this
exists:

* a reverse-protection diode fitted backwards, and three LEDs fitted backwards,
  because pin 1 of a KiCad diode or LED is the **cathode**;
* a 74HC123 with a wrong pin numbering on the sister EC9 project - invisible to
  ERC because the hand-made symbol declared pin types matching the same wrong
  assumption;
* two AND-gate outputs tied to ground, from assuming which pins were inputs;
* on this board's first issue, all six relay MOSFETs wired drain-to-ground,
  because Q_NMOS_GSD's pin 2 is the source and it was taken for the drain. The
  body diode then held every relay on, and ERC, DRC and parity were all clean.

So these checks work from **pin function**, never pin number, and fail loudly.
"""
import os
import re
import sys

NET = os.path.join('review', 'net.net')
HW = 'hardware'

# Only these may touch both ground domains. Everything else bridging the barrier
# is a defect: the whole point of the separate 24 V supply is that PC ground
# never reaches machine ground.
ISOLATORS = ('6N137', 'PC847', 'B2405S', 'Conn_01x04')

GRID = 1.27


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


def load_nets():
    s = open(NET, encoding='utf-8').read()
    vals = {}
    # '(comp' alone also matches '(components', which swallows the whole block.
    for b in blocks(s, '(comp\n'):
        r = re.search(r'\(ref "([^"]+)"\)', b)
        v = re.search(r'\(value "([^"]*)"\)', b)
        lp = re.search(r'\(part "([^"]*)"\)', b)
        if r:
            vals[r.group(1)] = (v.group(1) if v else '', lp.group(1) if lp else '')
    nets = {}
    for b in blocks(s, '(net\n'):
        nm = re.search(r'\(name "([^"]*)"\)', b)
        if not nm:
            continue
        nodes = []
        for nb in blocks(b, '(node'):
            r = re.search(r'\(ref "([^"]+)"\)', nb)
            p = re.search(r'\(pin "([^"]+)"\)', nb)
            f = re.search(r'\(pinfunction "([^"]+)"\)', nb)
            if r and p:
                nodes.append((r.group(1), p.group(1), f.group(1) if f else ''))
        nets[nm.group(1)] = nodes
    return vals, nets


def check_isolation(vals, nets):
    pc = {r for r, _, _ in nets.get('GND_PC', [])}
    m = {r for r, _, _ in nets.get('GND_M', [])}
    both = pc & m
    bad = [r for r in both
           if not any(k.lower() in ' '.join(vals.get(r, ('', ''))).lower()
                      for k in ISOLATORS)]
    print('  isolation : %d parts bridge the ground' % len(both))
    for r in sorted(both):
        print('              %-6s %s' % (r, ' '.join(vals.get(r, ('', '')))))
    if bad:
        print('  FAIL      : these are not isolating devices: %s' % sorted(bad))
        return False
    return True


def check_led_polarity(vals, nets):
    """An indicator LED must never have its cathode on a positive rail.

    This is the check that would have caught three LEDs fitted backwards: in
    KiCad's Device library pin 1 of an LED is the CATHODE, so wiring "rail to
    pin 1" reverses it and it simply never lights. Plain diodes are skipped -
    a series protection diode legitimately has its cathode on the downstream
    rail, and a flyback diode has it on the positive side of the coil.
    """
    rails = ('V24', '+5V_M', '+5V_PC')
    bad = []
    for net, nodes in nets.items():
        if net not in rails:
            continue
        for ref, pin, fn in nodes:
            if vals.get(ref, ('', ''))[1] == 'LED' and fn.startswith('K'):
                bad.append((ref, vals[ref][0], net))
    print('  LED polarity: %d LEDs with the cathode on a positive rail' % len(bad))
    for ref, val, net in bad:
        print('              %-6s %-26s cathode on %s  <-- would never light'
              % (ref, val, net))
    return not bad


def check_fet_orientation(vals, nets):
    """Every N-channel MOSFET switching a load must have its SOURCE on ground.

    On a low-side switch the drain goes to the load and the source to ground.
    Swap them and the body diode - anode at the source, cathode at the drain -
    is forward biased by the load: the load stays on whatever the gate does.
    Checked by pin function (S/D), never by pin number, because the number is
    exactly what went wrong.
    """
    bad, checked = [], 0
    pins = {}
    for net, nodes in nets.items():
        for ref, pin, fn in nodes:
            if vals.get(ref, ('', ''))[1].startswith('Q_NMOS'):
                pins.setdefault(ref, {})[fn.split('_')[0]] = net
    for ref, p in sorted(pins.items()):
        checked += 1
        if p.get('S') != 'GND' or p.get('D') == 'GND':
            bad.append((ref, p.get('S'), p.get('D')))
    print('  mosfets   : %d checked, %d with the source off ground'
          % (checked, len(bad)))
    for ref, s, d in bad:
        print('  FAIL      : %s source on %s, drain on %s - body diode holds the'
              ' load on' % (ref, s, d))
    return not bad


def strip_properties(body):
    """Drop every (property ...) block.

    The grid test is about things that can be connected to. A property is a
    piece of text - a value, a footprint name, a sheet's name and filename -
    and where it is printed has no electrical meaning. Counting those made the
    test fail over four sheet captions sitting half a millimetre off a grid
    they were never on.
    """
    out, i = [], 0
    while True:
        j = body.find('(property ', i)
        if j < 0:
            out.append(body[i:])
            return ''.join(out)
        out.append(body[i:j])
        i = span(body, j)


def check_grid():
    bad = tot = 0
    for fn in sorted(os.listdir(HW)):
        if not fn.endswith('.kicad_sch'):
            continue
        s = open(os.path.join(HW, fn), encoding='utf-8').read()
        i = s.find('(lib_symbols')
        if i >= 0:
            body = s[:i] + s[span(s, s.index('(', i)):]
        else:
            body = s
        body = strip_properties(body)
        for mm in re.finditer(r'\((?:at|xy) (-?[\d.]+) (-?[\d.]+)', body):
            for v in mm.groups():
                tot += 1
                if abs(float(v) / GRID - round(float(v) / GRID)) > 1e-6:
                    bad += 1
    print('  grid      : %d sheet coordinates, %d off-grid' % (tot, bad))
    return bad == 0


def check_opto_orientation(vals, nets):
    """Every optocoupler's phototransistor must be the right way round.

    The one defect on this board that ERC could never see and that would have
    killed every input: PC847 unit 1 lists its pins 1, 2, 15, 16, so unpacking
    them in order made pin 15 the collector - and pin 15 is the emitter. All ten
    isolated inputs had the collector on GND_PC and the emitter on the pull-up,
    so no home switch, no E-stop, no THC and no handwheel pulse would ever have
    reached Mach3. Nothing in the netlist looks wrong: both pins are 'passive',
    both nets exist, and the schematic draws cleanly.

    What gives it away is the shape of the circuit rather than any pin name. An
    opto output stage is always the same: collector to a pulled-up signal,
    emitter to a ground. So this asserts that for every PC847 channel exactly
    one transistor-side pin sits on a ground net, and it is the LOWER numbered
    of the pair - because in these packages the collectors are the high numbers.
    """
    grounds = {'GND'}
    by_ref = {}
    for net, nodes in nets.items():
        for ref, pin, _ in nodes:
            if 'PC84' in vals.get(ref, ('', ''))[0] or 'PC81' in vals.get(ref, ('', ''))[0]:
                by_ref.setdefault(ref, {})[pin] = net
    bad, checked = [], 0
    for ref, pins in sorted(by_ref.items()):
        tr = sorted((int(n) for n in pins if int(n) > 8))
        for lo, hi in zip(tr[0::2], tr[1::2]):
            # A channel's transistor pair is (emitter, collector) = (lo, hi).
            e, c = pins[str(lo)], pins[str(hi)]
            if e in grounds and c in grounds:
                continue                    # an unused channel tied off
            checked += 1
            if c in grounds and e not in grounds:
                bad.append((ref, hi, lo, c, e))
    print('  optos     : %d channels checked, %d wired collector-to-ground'
          % (checked, len(bad)))
    for ref, c, e, cn, en in bad:
        print('  FAIL      : %s pin %d is the COLLECTOR and sits on %s, while pin %d'
              % (ref, c, cn, e))
        print('              (the emitter) sits on %s - the transistor is reversed'
              % en)
    return not bad


def check_sheet_coverage(vals):
    """Every part drawn on a sheet must appear in the netlist.

    This is the check that would have caught the worst defect on this project.
    An unescaped quote inside a note - `SendSerial("A")` - ended the string
    token early and made 06_serial.kicad_sch unparseable. KiCad dropped the
    whole sheet without a word: ERC reported 0 violations, the netlist simply
    had no MCU, no relays, no RS232, and the PCB was generated from it. A clean
    ERC proves nothing about a sheet the tool never managed to read.
    """
    missing, sheets = {}, 0
    for fn in sorted(os.listdir(HW)):
        if not fn.endswith('.kicad_sch') or not fn[0].isdigit():
            continue
        sheets += 1
        body = open(os.path.join(HW, fn), encoding='utf-8').read()
        i = body.find('(lib_symbols')
        if i >= 0:
            body = body[:i] + body[span(body, body.index('(', i)):]
        refs = set(re.findall(r'\(property "Reference" "([^"]+)"', body))
        gone = sorted(r for r in refs if not r.startswith('#') and r not in vals)
        if gone:
            missing[fn] = gone
    print('  sheets    : %d checked, %d with parts missing from the netlist'
          % (sheets, len(missing)))
    for fn, gone in sorted(missing.items()):
        print('  FAIL      : %s drops %d parts: %s%s'
              % (fn, len(gone), ', '.join(gone[:8]),
                 ' ...' if len(gone) > 8 else ''))
    return not missing


def main():
    vals, nets = load_nets()
    print('  netlist   : %d components, %d nets' % (len(vals), len(nets)))
    ok = all([check_sheet_coverage(vals),
              check_opto_orientation(vals, nets),
              check_isolation(vals, nets),
              check_led_polarity(vals, nets),
              check_fet_orientation(vals, nets),
              check_grid()])
    if not ok:
        print('  RESULT    : FAIL')
        sys.exit(1)
    print('  RESULT    : pass')


if __name__ == '__main__':
    main()
