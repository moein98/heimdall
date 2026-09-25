#!/usr/bin/env python3
"""Check the schematic against the grblHAL board map, from the netlist.

The pin map lives in three places: docs/SPEC.md for people, the grblHAL
board map (firmware/grblHAL/boards/my_machine_map.h) for the firmware, and
GPIO in tools/build_project.py for the schematic. This reads the second from
the header and the third back out of the netlist KiCad exports - not out of
build_project.py, so it checks what was actually drawn - and fails on any
difference.

It then follows each signal to where it must arrive (ETH_CS to the W5500's
SCS pin, UART1_TX to the handwheel MCU's RXD, each STEP line into a buffer
and out to its terminal, ...), and lists nets with a single node: a label
spelled differently at its two ends is a net of one on each side, which ERC
does not report.

Usage: python3 tools/check_pinmap.py   (after exporting review/net.net)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NETLIST = os.path.join(ROOT, 'review', 'net.net')
BOARDMAP = os.path.join(ROOT, 'firmware', 'grblHAL', 'boards', 'my_machine_map.h')
AXES = ['X', 'Y', 'Z', 'A', 'B', 'C', 'U', 'V']


def _sexpr(text):
    """Parse an s-expression into nested lists of strings."""
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


def _field(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x[1] if len(x) > 1 else ''
    return ''


def read_netlist(path):
    """{net name: [(ref, pin, pinfunction)]}, from KiCad's s-expression netlist."""
    root = _sexpr(open(path, encoding='utf-8').read())
    nets = {}
    for sec in root:
        if isinstance(sec, list) and sec and sec[0] == 'nets':
            for net in sec[1:]:
                name = _field(net, 'name').lstrip('/')
                nodes = []
                for n in net:
                    if isinstance(n, list) and n[0] == 'node':
                        pin, func = _field(n, 'pin'), _field(n, 'pinfunction')
                        # KiCad 10 writes the function as NAME_<pin number>.
                        if func.endswith('_' + pin):
                            func = func[:-len(pin) - 1]
                        nodes.append((_field(n, 'ref'), pin, func))
                nets[name] = nodes
    return nets


def read_boardmap(path):
    """#define NAME value, with (A + n) sums and NAME references resolved."""
    defs = {}
    for line in open(path, encoding='utf-8'):
        m = re.match(r'\s*#define\s+(\w+)\s+(.+?)\s*(//.*)?$', line)
        if m:
            defs.setdefault(m.group(1), m.group(2).strip())

    def val(name, depth=0):
        v = defs[name]
        m = re.fullmatch(r'\((\w+)\s*\+\s*(\d+)\)', v)
        if m:
            return val(m.group(1), depth + 1) + int(m.group(2))
        if re.fullmatch(r'\d+', v):
            return int(v)
        return val(v, depth + 1)
    return defs, val


def main():
    if not os.path.exists(NETLIST):
        print('no %s - export the netlist first' % NETLIST)
        return 1
    nets = read_netlist(NETLIST)
    defs, val = read_boardmap(BOARDMAP)
    fails = []

    # ---- 1. RP2350B GPIO -> net, from the netlist
    drawn = {}
    for name, nodes in nets.items():
        for ref, pin, func in nodes:
            if ref == 'U201' and func.startswith('GPIO'):
                drawn[int(func.split('/')[0][4:])] = name
    if sorted(drawn) != list(range(48)):
        fails.append('RP2350B GPIO missing from netlist: %s'
                     % sorted(set(range(48)) - set(drawn)))

    # ---- 2. what the firmware expects on each GPIO
    want = {}

    def expect(gpio, net, why):
        if gpio in want and want[gpio][0] != net:
            fails.append('GP%d claimed twice in the board map: %s and %s'
                         % (gpio, want[gpio][1], why))
        want[gpio] = (net, why)

    base = val('STEP_PINS_BASE')
    dbase = val('X_DIRECTION_PIN')
    shift = defs.get('DIRECTION_OUTMODE', '')
    if shift != 'GPIO_SHIFT%d' % dbase:
        fails.append('DIRECTION_OUTMODE is %s but X_DIRECTION_PIN is %d'
                     % (shift, dbase))
    for i, a in enumerate(AXES):
        expect(base + i, '%s_STEP3' % a, 'step %s (STEP_PINS_BASE+%d)' % (a, i))
        expect(dbase + i, '%s_DIR3' % a, 'dir %s' % a)
    for a, key in zip('XYZ', ('X_LIMIT_PIN', 'Y_LIMIT_PIN', 'Z_LIMIT_PIN')):
        expect(val(key), '%s_LIM' % a, key)
    for m, a in zip(range(3, 8), AXES[3:]):
        expect(val('M%d_LIMIT_PIN' % m), '%s_LIM' % a, 'M%d_LIMIT_PIN' % m)
        if val('M%d_STEP_PIN' % m) != base + m:
            fails.append('M%d_STEP_PIN is not STEP_PINS_BASE + %d' % (m, m))
        if val('M%d_DIRECTION_PIN' % m) != dbase + m:
            fails.append('M%d_DIRECTION_PIN is not X_DIRECTION_PIN + %d' % (m, m))
    expect(val('STEPPERS_ENABLE_PIN'), 'EN3', 'STEPPERS_ENABLE_PIN')
    for n, net in enumerate(('ESTOP', 'FEED_HOLD', 'CYCLE_START', 'PROBE',
                             'ARC_OK', 'THC_UP', 'THC_DOWN')):
        expect(val('AUXINPUT%d_PIN' % n), net, 'AUXINPUT%d_PIN' % n)
    for n, net in enumerate(('RS485_DE', 'SP_PWM_IN', 'SP_FWD_IN', 'SP_REV_IN')):
        expect(val('AUXOUTPUT%d_PIN' % n), net, 'AUXOUTPUT%d_PIN' % n)
    for key, net in (('SPI_SCK_PIN', 'SPI_SCK'), ('SPI_MOSI_PIN', 'SPI_MOSI'),
                     ('SPI_MISO_PIN', 'SPI_MISO'), ('SD_CS_PIN', 'SD_CS'),
                     ('SPI_CS_PIN', 'ETH_CS'), ('SPI_IRQ_PIN', 'ETH_INT'),
                     ('I2C_SDA', 'I2C_SDA'), ('I2C_SCL', 'I2C_SCL'),
                     ('UART_TX_PIN', 'RS485_DI'), ('UART_RX_PIN', 'RS485_RO'),
                     ('UART_1_TX_PIN', 'UART1_TX'), ('UART_1_RX_PIN', 'UART1_RX')):
        expect(val(key), net, key)
    if defs.get('MODBUS_DIR_AUX') != '0':
        fails.append('MODBUS_DIR_AUX should be aux output 0 (GP25)')
    for gpio in range(48):
        if gpio not in want:
            fails.append('GP%d (%s in the schematic) has no job in the board map'
                         % (gpio, drawn.get(gpio)))
        elif drawn.get(gpio) != want[gpio][0]:
            fails.append('GP%d: schematic %s, board map %s (%s)'
                         % (gpio, drawn.get(gpio), want[gpio][0], want[gpio][1]))

    # ---- 3. each signal arrives where it must
    def has(net, ref, pinfunc):
        return any(r == ref and (f == pinfunc or p == pinfunc)
                   for r, p, f in nets.get(net, []))

    arrive = [('ETH_CS', 'U301', '~{SCS}'), ('ETH_INT', 'U301', '~{INT}'),
              ('SPI_SCK', 'U301', 'SCLK'), ('SPI_MOSI', 'U301', 'MOSI'),
              ('SPI_MISO', 'U301', 'MISO'), ('NRST', 'U301', '~{RST}'),
              ('SD_CS', 'J203', 'DAT3/CD'), ('SPI_MOSI', 'J203', 'CMD'),
              ('SPI_MISO', 'J203', 'DAT0'), ('SPI_SCK', 'J203', 'CLK'),
              ('RS485_DI', 'U801', 'DI'), ('RS485_RO', 'U801', 'RO'),
              ('RS485_DE', 'U801', 'DE'), ('RS485_DE', 'U801', '~{RE}'),
              ('UART1_TX', 'U802', 'PD0'), ('UART1_RX', 'U802', 'PD1'),
              ('I2C_SDA', 'U601', 'SDA'), ('I2C_SCL', 'U601', 'SCK'),
              ('SP_PWM_IN', 'U701', '1'), ('SP_FWD_IN', 'U701', '3'),
              ('SP_REV_IN', 'U701', '5'), ('SP_AUX_IN', 'U701', '9'),
              ('SP_AUX_IN', 'U601', 'GPA6'), ('NRST', 'U201', 'RUN')]
    for i, ch in enumerate('ABCDEF'):
        arrive.append(('REL_%s' % ch, 'U601', 'GPA%d' % i))
    for net, ref, pf in arrive:
        if not has(net, ref, pf):
            fails.append('%s does not reach %s %s' % (net, ref, pf))
    # Step, dir and enable: MCU -> buffer A pin, buffer B pin -> terminal.
    lines = [x for a in AXES for x in ('%s_STEP' % a, '%s_DIR' % a)] + ['EN']
    for n in lines:
        a_side = [r for r, p, f in nets.get(n + '3', []) if r.startswith('U40')]
        b_side = [r for r, p, f in nets.get(n, []) if r.startswith('U40')]
        term = [r for r, p, f in nets.get(n, []) if r.startswith('J4')]
        if not (a_side and b_side and term):
            fails.append('%s: not MCU -> 74ACT245 -> terminal' % n)
    # Every opto input: MCU pin, pull-up, filter cap, opto collector.
    for gpio in range(26, 41):
        n = drawn.get(gpio)
        refs = {r[:2] for r, p, f in nets.get(n, [])}
        if not {'U5', 'R5', 'C5'} <= refs:
            fails.append('%s (GP%d): missing opto, pull-up or filter' % (n, gpio))

    # ---- 4. nets of one node
    lone = sorted(n for n, nodes in nets.items()
                  if len(nodes) == 1 and not n.startswith('unconnected-')
                  and not n.startswith('Net-('))
    for n in lone:
        fails.append('net %s has one node only (%s)' % (n, nets[n][0][0]))

    print('RP2350B pins in the netlist: %d / 48' % len(drawn))
    print('board map: %d GPIO jobs' % len(want))
    if fails:
        print('\nFAIL (%d):' % len(fails))
        for f in fails:
            print('  ' + f)
        return 1
    print('pin map: schematic and grblHAL board map agree on all 48 GPIO')
    print('signal paths: %d checked, all arrive' % (len(arrive) + len(lines) + 15))
    return 0


if __name__ == '__main__':
    sys.exit(main())
