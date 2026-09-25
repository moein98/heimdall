#!/usr/bin/env python3
"""Grouped bill of materials for ordering, from the netlist.

`kicad-cli sch export bom` gives one line per reference, which is what you want
for assembly and useless for buying. This groups identical parts, strips the
notes the schematic carries in its value field - "100nF U10" says which chip a
bypass capacitor belongs to and is not a different part - and prints a package
for each line so a shop can find it.

Writes docs/BOM_ORDER.md and prints the same table.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_design as C                                     # noqa: E402

# What a footprint means to someone ordering parts.
PKG = [
    (r'R_0603|C_0603|LED_0603', '0603 SMD'),
    (r'R_1206|C_1206', '1206 SMD'),
    (r'R_Array_Convex_4x0603', '4 x 0603 array, convex (1206 size)'),
    (r'CP_Elec_6.3x7.7', 'electrolytic 6.3x7.7 SMD'),
    (r'C_Disc', 'disc ceramic, THT'),
    (r'SOIC-8', 'SOIC-8'),
    (r'SOIC-14', 'SOIC-14'),
    (r'SOIC-16', 'SOIC-16'),
    (r'TQFP-32', 'TQFP-32'),
    (r'TO-263', 'TO-263-5 (D2PAK)'),
    (r'SOT-89', 'SOT-89-3'),
    (r'SMDIP-16', 'DIP-16, SMD lead form (2.54 mm)'),
    (r'SOT-23', 'SOT-23'),
    (r'D_SOD-123', 'SOD-123 SMD'),
    (r'D_SMA', 'SMA SMD'),
    (r'L_12x12mm', '12x12x8 mm shielded SMD'),
    (r'Fuse_1206', '1206 SMD'),
    (r'Crystal_SMD_3225', '3.2x2.5 mm SMD, 4 pad'),
    (r'Potentiometer_Bourns_3296W', 'Bourns 3296W trimmer, THT'),
    # This board uses the Phoenix 5.0 mm blocks; the MetzConnect 3.5 mm
    # patterns are the sister board's, kept because the generator is shared.
    (r'RT06302HBWC', 'MetzConnect Type059 3.5 mm, 2 way'),
    (r'RT06303HBWC', 'MetzConnect Type059 3.5 mm, 3 way'),
    (r'RT06304HBWC', 'MetzConnect Type059 3.5 mm, 4 way'),
    (r'RT06306HBWC', 'MetzConnect Type059 3.5 mm, 6 way'),
    (r'MKDS-1,5-6', 'Phoenix MKDS 1,5 5.0 mm, 6 way'),
    (r'MKDS-1,5-2', 'Phoenix MKDS 1,5 5.0 mm, 2 way'),
    (r'MKDS-1,5-3', 'Phoenix MKDS 1,5 5.0 mm, 3 way'),
    (r'MKDS-1,5-4', 'Phoenix MKDS 1,5 5.0 mm, 4 way'),
    (r'MKDS-1,5-5', 'Phoenix MKDS 1,5 5.0 mm, 5 way'),
    (r'DSUB-25', 'DB25 socket, right angle, PCB'),
    (r'DSUB-9', 'DE9 socket, right angle, PCB'),
    (r'PinHeader_2x03', '2x3 pin header, 2.54 mm'),
    (r'IDC-Header_2x05', '2x5 shrouded box header, 2.54 mm'),
    (r'Relay_SPDT_Hongfa_JQC-3FF', 'JQC-3FF relay, THT'),
    (r'Converter_DCDC', 'SIP-4 isolated module'),
    (r'MountingHole', 'M3 hole (no part)'),
]

# Sections, in the order a shop would walk them.
SECTIONS = [
    ('Semiconductors - the ones to get right', ('U',)),
    ('Transistors, diodes and LEDs', ('Q', 'D')),
    ('Relays', ('K',)),
    ('Connectors', ('J',)),
    ('Resistors', ('R', 'RN')),
    ('Trimmers', ('RV',)),
    ('Capacitors', ('C',)),
    ('Inductor, fuse, crystal', ('L', 'F', 'Y')),
    ('Mechanical', ('H',)),
]

# Notes worth carrying to the counter.
NOTES = {
    '6N137': 'high-speed opto. Do NOT substitute a PC817 - it is far too slow for step pulses',
    'PC847': '4-channel opto, the SMD lead form (Sharp PC847XI, or LTV-847S) - there is no SOIC version',
    'AM26LS31CD': 'RS-422 line driver. SN65LBC174 or DS26LS31 are drop-ins',
    'B2405S-2W': 'VERIFY THE PIN ORDER against the module in hand before power-up',
    'LM2596S-5': 'fixed 5 V version, not ADJ',
    '74AC245': 'AC, not HC: 24 mA per output for opto-input stepper drivers. 74HC245 fits the same pads but is overloaded by more than about 6 mA per output',
    'PTC': 'resettable fuse, hold 0.2 A, 1206 (Bourns MF-MSMF020 or similar)',
    'B2412S-1WR3': 'Mornsun 1 W isolated 24 V to 12 V, SIP-4. Pins 1 GND, 2 Vin, 3 0V, 4 +Vo',
    '78L05': 'SOT-89. Pin order OUT, GND, IN - not the TO-92 order',
    'LM358': 'LM358 or LM2904, SOIC-8',
    '47uH': 'shielded power inductor, saturation current 1.5 A or more (SRR1260-470M, or the 47 uH from an LM2596 module)',
    '220uF 16V': 'low-ESR electrolytic - the buck output capacitor',
    '47uF 50V': 'low-ESR electrolytic, 50 V - the largest a 6.3 x 7.7 can holds',
    '5k': 'multi-turn trimmer, sets 10.0 V at full speed',
    'ATmega328P-AU': 'TQFP-32. Runs on the 16 MHz crystal Y1',
    '16MHz': 'load capacitance CL 18-20 pF, to suit the 22 pF capacitors',
    'MAX3232': '3 V version works on 5 V; MAX232 does NOT - wrong capacitor values',
    '74HC123': 'HC, not HCT and not LS - the timing depends on it',
    '74HC14': 'Schmitt inverter. Plain 74HC04 will not do',
    'SMAJ26A': 'TVS on the 24 V input. Clamps at 42 V, under the 50 V rating of C2',
    'SS34': '40 V 3 A Schottky, both places',
    '1N4148': 'plain small-signal, any maker',
    'JQC-3FF-024-1Z': '24 V coil, SPDT. Songle or Hongfa',
    '0R link': 'DO NOT FIT - the shell bonding option',
}


def clean(value, ref='', fp=''):
    """Strip the schematic's annotations from a value.

    A bypass capacitor's value reads "100nF U10" so the layout and the BOM can
    say which chip it belongs beside. For ordering, they are all 100nF.

    Indicator LEDs and connectors carry their *function* as the value - "X_HOME",
    "Y axis" - because that is what has to be silkscreened next to them. For
    ordering they are all the same part, so those collapse to the package.
    """
    if re.match(r'D\d', ref) and 'LED' in fp:
        return 'LED, indicator'
    if re.match(r'J\d', ref):
        return 'connector'
    v = value.strip()
    v = re.sub(r'\s+(U\d+|[A-Z]\d+)$', '', v)          # "100nF U10"
    v = re.sub(r'\s+(C0G|Y5P|1206|filter|slow|bleed|flyback|reverse|'
               r'anti-parallel|LED reverse|reset discharge|catch|'
               r'pull-down|fail-safe|trimmer FS|AREF|link.*|'
               r'1\.5A shielded|low ESR|10\.0V trim|MPG_SEL pull-down|'
               r'spare pull-down)$', '', v)
    return v.strip() or value.strip()


def package(fp):
    for pat, name in PKG:
        if re.search(pat, fp):
            return name
    return fp.split(':')[-1][:34] if fp else '-'


def prefix(ref):
    return re.match(r'[A-Za-z]+', ref).group(0)


def main():
    vals, _ = C.load_nets()
    fps = {}
    s = open(C.NET, encoding='utf-8').read()
    for b in C.blocks(s, '(comp\n'):
        r = re.search(r'\(ref "([^"]+)"\)', b)
        f = re.search(r'\(footprint "([^"]*)"\)', b)
        if r:
            fps[r.group(1)] = f.group(1) if f else ''

    groups, unfitted = {}, []
    for ref, (value, _part) in vals.items():
        if ref.startswith('TP'):
            continue                    # test points: bare pads, nothing to buy
        if 'DO NOT FIT' in value.upper():
            unfitted.append((ref, value))
            continue
        key = (clean(value, ref, fps.get(ref, '')), package(fps.get(ref, '')))
        groups.setdefault(key, []).append(ref)

    lines = ['# MACH3-SIMPLE - order list',
             '',
             'Generated from the netlist by `tools/bom.py`. Quantities are what the',
             'board needs; buy spares of the 0603 passives and the optocouplers.',
             '']
    total = 0
    for title, prefixes in SECTIONS:
        rows = [(k, v) for k, v in groups.items()
                if prefix(v[0]) in prefixes]
        if not rows:
            continue
        rows.sort(key=lambda kv: (-len(kv[1]), kv[0][0]))
        lines.append('## %s' % title)
        lines.append('')
        lines.append('| Qty | Part | Package | Refs | Note |')
        lines.append('|---:|---|---|---|---|')
        for (value, pkg), refs in rows:
            refs.sort(key=lambda r: (prefix(r), int(re.sub(r'\D', '', r) or 0)))
            note = ''
            for k, n in NOTES.items():
                if k.lower() in value.lower():
                    note = n
                    break
            shown = ', '.join(refs) if len(refs) <= 12 else (
                '%s ... %s' % (', '.join(refs[:6]), refs[-1]))
            lines.append('| %d | %s | %s | %s | %s |'
                         % (len(refs), value, pkg, shown, note))
            if 'no part' not in pkg:
                total += len(refs)
        lines.append('')

    if unfitted:
        lines.append('## Not fitted - leave the pads empty')
        lines.append('')
        for ref, value in sorted(unfitted):
            lines.append('- %s (%s)' % (ref, value))
        lines.append('')
    lines.append('**%d parts to fit** across %d distinct lines.'
                 % (total, sum(1 for k, v in groups.items()
                               if 'no part' not in k[1])))
    lines.append('')
    lines.append('Worth buying spare: the 0603 resistors and capacitors (they '
                 'are pennies and')
    lines.append('they get lost), one or two extra PC847, and one spare '
                 'ATmega328P.')
    out = '\n'.join(lines) + '\n'
    path = os.path.join('docs', 'BOM_ORDER.md')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(out)
    print(out)
    print('written: %s' % path)


if __name__ == '__main__':
    main()
