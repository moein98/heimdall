#!/usr/bin/env python3
"""Two checks that do not take the designer's word for it.

The resistor networks on the buffer inputs were missing from this board for
days. Nothing caught them: ERC passed, DRC passed, and the placement matched
the drawing to a tenth of a millimetre. The owner of the original board found
them by looking at it. That is the failure worth fixing - not the resistors.

* **Undefined nodes.** A net that reaches a chip input and has nothing on it
  but a connector pin has no defined level: unplug the cable and it follows
  whatever the air says. ERC cannot see this, because a connector pin is
  passive and a passive pin satisfies an input. This check needs only the
  schematic, so it would have found the missing pull-downs on a board with no
  original to copy from.

* **Part census.** Every part on the drawing, classified by its reference and
  its pad pattern, counted against the parts here. It answers "what does that
  board have that this one does not" by counting rather than by looking.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb as bp                                        # noqa: E402

NET = os.path.join('review', 'net.net')
REF = os.path.join('review', 'ref.json')

# Pin types that put a level on a net by themselves.
DRIVING = ('output', 'power_out', 'bidirectional')


def nodes():
    """{net: [(ref, pin, pinfunction, pintype)]} straight from the netlist."""
    t = open(NET, encoding='utf-8').read()
    out, cur = collections.defaultdict(list), None
    # pinfunction is optional. A resistor's pins have no function name, and
    # the first version of this pattern required one - it read 263 of the 443
    # nodes, dropped every resistor, and then reported the handwheel lines as
    # having nothing on them when each has a 10k pull-up. A check for missing
    # parts that cannot see parts is the failure it exists to catch.
    pat = (r'\(name "([^"]+)"\)'
           r'|\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)\s*'
           r'(?:\(pinfunction "([^"]*)"\)\s*)?\(pintype "([^"]+)"\)')
    for m in re.finditer(pat, t):
        if m.group(1) is not None:
            cur = m.group(1).lstrip('/')
        elif cur is not None:
            ref, pin, fn, kind = m.group(2, 3, 4, 5)
            out[cur].append((ref, pin, fn or '', kind))
    n = sum(len(v) for v in out.values())
    tags = t.count('(pintype ')
    if n != tags:
        raise SystemExit('read %d nodes of %d in %s - the parser is wrong, '
                         'not the design' % (n, tags, NET))
    return out


def drivers(comps, pins):
    """Which references can put a level on this net.

    A tri-state pin is the awkward case: it drives only while its output
    enable says so, and on a bus transceiver only on the side the direction
    pin selects. Both are read off the schematic here rather than assumed -
    a 74HC245 with DIR high drives its B pins and listens on its A pins, and
    with /OE parked low it does that always. Any other tri-state part is given
    the benefit of the doubt, so this check under-reports rather than crying
    wolf.
    """
    drive = set()
    for ref, _pin, fn, kind in pins:
        if kind in DRIVING:
            drive.add(ref)
        elif kind == 'tri_state' and ref in comps:
            pads = comps[ref]['pads']
            if '245' in comps[ref]['value'].upper():
                if pads.get('19') != 'GND':
                    drive.add(ref)
                elif (pads.get('1') == '+5V') == fn.startswith('B'):
                    drive.add(ref)
            else:
                drive.add(ref)
    return drive


def held_inside(comps, ref, fn):
    """True for a pin the chip holds itself, so a floating net is not floating.

    A MAX3232's transmitter inputs have their own 400 k pull-ups and its
    receiver inputs their own 5 k pull-downs. Without this the RS232 receive
    line showed up on every run as a node with nothing on it.
    """
    v = comps.get(ref, {}).get('value', '').upper()
    if 'MAX3232' in v or 'MAX232' in v:
        return bool(re.match(r'[TR]\dIN', fn))
    return False


def is_mcu(comps, ref):
    return 'ATMEGA' in comps.get(ref, {}).get('value', '').upper()


def reset_floats(comps, net_map):
    """Nets an MCU pin drives, that a chip listens to, with nothing to hold them.

    An MCU pin is marked bidirectional, which the check above counts as a
    driver - and it is one, once the firmware is running. Through reset, at
    every power-up, and on a chip nobody has programmed yet, it is an input
    and drives nothing. A chip listening on the far end then sees whatever the
    net picks up. The handwheel select line was one of these: it could hand
    the handwheel to the THC pins at random until the firmware woke up.
    """
    bad = []
    for n, pins in sorted(net_map.items()):
        refs = {r for r, _p, _f, _k in pins}
        mcus = {r for r in refs if is_mcu(comps, r)}
        if not mcus or any(r[0] in 'RCDLQ' for r in refs):
            continue
        others = [(r, p, f, k) for r, p, f, k in pins if r not in mcus]
        if drivers(comps, others):
            continue                             # something else drives it
        listeners = [(r, f) for r, _p, f, k in others
                     if r[0] == 'U' and k == 'input'
                     and not held_inside(comps, r, f)]
        if listeners:
            bad.append((n, sorted(refs)))
    return bad


def undefined(comps, net_map):
    """Nets that leave the board, reach a chip, and nothing sets their level."""
    bad = []
    for n, pins in sorted(net_map.items()):
        if n in ('GND', '+5V', 'V24', 'CHASSIS') or n.startswith('unconnected'):
            continue
        refs = {r for r, _p, _f, _k in pins}
        if not any(r[0] == 'J' for r in refs):
            continue                             # never leaves the board
        if any(r[0] in 'RCDLQ' for r in refs):
            continue                             # something holds it
        if drivers(comps, pins):
            continue                             # something drives it
        if any(r[0] == 'U' and not held_inside(comps, r, f)
               for r, _p, f, _k in pins):
            bad.append((n, sorted(refs)))
    return bad


def their_class(ref, pads):
    """What a part on the drawing is.

    The reference tells most of it - that board names terminals T, relays K,
    resistors R and so on - and the pad pattern settles the rest. Geometry
    alone put every two-pin through-hole passive in the terminal column,
    because a pair of pads 7 mm apart in a line looks exactly like one.
    """
    n = len(pads)
    m = re.match(r'[A-Za-z]+', ref)
    head = m.group(0).upper() if m else ''
    if head == 'J':
        return 'D-sub 25'
    if head == 'T':
        return '%d-way terminal' % n
    if head == 'K':
        return 'relay'
    if head.startswith('RS'):
        return '%d-way terminal' % n
    if head == 'R':
        return 'resistor network' if n >= 8 else 'resistor'
    if head == 'C' or head.startswith('CVCC'):
        return 'capacitor'
    if head == 'LED':
        return 'LED'
    if head == 'D':
        return 'diode'
    if head in ('U', 'MAX'):
        if n >= 40:
            return 'QFP/PLCC-%d' % n
        if n == 4:
            return 'DIP-4 optocoupler'
        return 'DIP-%d' % n
    if head == 'P':
        return '%d-pin header' % n
    if head == 'BEAD':
        return 'ferrite bead'
    return '%d pads (%s)' % (n, ref)


def our_class(ref, fp, pads):
    """The same question, for a footprint in this design."""
    n = len(pads)
    if 'DSUB' in fp:
        return 'D-sub 25'
    if 'TerminalBlock' in fp:
        return '%d-way terminal' % n
    if 'Relay' in fp:
        return 'relay'
    if 'MountingHole' in fp:
        return 'mounting hole'
    if 'Crystal' in fp:
        return 'crystal'
    if 'IDC-Header' in fp or 'PinHeader' in fp:
        return '%d-pin header' % n
    if 'LED' in fp:
        return 'LED'
    if 'R_Array' in fp or 'R_Pack' in fp or 'R_Network' in fp:
        return 'resistor network'
    if ref[0] == 'D':
        return 'diode'
    if ref[0] == 'C':
        return 'capacitor'
    if ref[0] == 'R':
        return 'resistor'
    if ref[0] == 'F':
        return 'fuse'
    if ref[0] == 'Q':
        return 'transistor'
    if 'QFP' in fp or 'QFN' in fp:
        return 'QFP/PLCC-%d' % n
    if 'SOIC' in fp or 'SO-' in fp or 'DIP' in fp:
        return 'DIP-%d' % n
    return '%d pads' % n


def main():
    comps = bp.read_netlist()
    net_map = nodes()

    print('== nodes with nothing to drive or hold them ==')
    bad = undefined(comps, net_map)
    for n, refs in bad:
        print('  %-14s %s' % (n, ' '.join(refs)))
    print('  %d net%s' % (len(bad), '' if len(bad) == 1 else 's'))

    print()
    print('== nets only an MCU pin drives - floating through reset ==')
    rf = reset_floats(comps, net_map)
    for n, refs in rf:
        print('  %-14s %s' % (n, ' '.join(refs)))
    print('  %d net%s' % (len(rf), '' if len(rf) == 1 else 's'))
    bad = bad + rf

    print()
    print('== part census, drawing against this board ==')
    if not os.path.exists(REF):
        print('  no review/ref.json - run tools/read_ref.py')
        return 1 if bad else 0
    ref = json.load(open(REF))
    theirs = collections.Counter(
        their_class(r, list(v.values())) for r, v in ref['pads'].items() if v)
    ours = collections.Counter(
        our_class(r, c['fp'], c['pads']) for r, c in comps.items() if c['fp'])
    gaps = 0
    print('  %-28s %8s %8s' % ('', 'drawing', 'here'))
    for k in sorted(set(theirs) | set(ours)):
        t, o = theirs.get(k, 0), ours.get(k, 0)
        flag = ''
        if t and not o:
            flag = '   <-- nothing here does this'
            gaps += 1
        print('  %-28s %8d %8d%s' % (k, t, o, flag))
    return 1 if (bad or gaps) else 0


if __name__ == '__main__':
    sys.exit(main())
