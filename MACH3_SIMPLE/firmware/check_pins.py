#!/usr/bin/env python3
"""Check firmware/pins.h against the board's netlist.

The firmware is written against a pin map and the board is built from one, and
nothing in either toolchain compares them. A relay wired to PD4 and driven on
PD3 compiles, routes, passes DRC and clicks the wrong relay. So: read each
PIN_x line in pins.h, find the MCU pin the netlist puts on the net named in
its comment, and fail on any difference.

Run from the project directory, after tools/validate.sh has written the
netlist:  python firmware/check_pins.py
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PINS_H = os.path.join(HERE, 'pins.h')
NET = os.path.join(HERE, '..', 'review', 'net.net')
MCU = 'U21'


def firmware_map():
    """{net: 'PD3'} from lines like  #define PIN_REL_A  D, 3  /* REL_A ... */"""
    out = {}
    pat = re.compile(r'#define\s+PIN_\w+\s+([A-D])\s*,\s*(\d)\s*/\*\s*(\w+)')
    for line in open(PINS_H, encoding='utf-8'):
        m = pat.search(line)
        if m:
            out[m.group(3)] = 'P%s%s' % (m.group(1), m.group(2))
    return out


def board_map():
    """{net: 'PD3'} for every MCU pin the netlist wires to something."""
    t = open(NET, encoding='utf-8').read()
    out = collections.defaultdict(set)
    for net in re.finditer(r'\(net\s*\(code "\d+"\)\s*\(name "([^"]+)"\)(.*?)\n\t\t\)',
                           t, re.S):
        name = net.group(1).lstrip('/')
        for node in re.finditer(r'\(ref "%s"\)\s*\(pin "\d+"\)\s*'
                                r'\(pinfunction "([^"]+)"\)' % MCU, net.group(2)):
            port = re.match(r'(?:\w+/)?(P[A-D]\d)', node.group(1))
            if port:
                out[name].add(port.group(1))
    return out


def main():
    fw, hw = firmware_map(), board_map()
    if not fw:
        print('no PIN_ lines read from %s' % PINS_H)
        return 1
    bad = 0
    for net, port in sorted(fw.items()):
        on_board = hw.get(net, set())
        ok = on_board == {port}
        bad += not ok
        print('  %-8s firmware %-4s board %-6s %s'
              % (net, port, ','.join(sorted(on_board)) or 'none',
                 'ok' if ok else '<-- MISMATCH'))
    if bad:
        print('pins      : %d of %d disagree with the board' % (bad, len(fw)))
        return 1
    print('pins      : all %d agree with the board' % len(fw))
    return 0


if __name__ == '__main__':
    sys.exit(main())
