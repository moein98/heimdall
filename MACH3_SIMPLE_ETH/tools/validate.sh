#!/usr/bin/env sh
# Verify the MACH3-SIMPLE-ETH schematic.
#
#   ERC            no errors, and no "multiple net names" warning: that is
#                  KiCad's only report of two labelled nets joined by a stray
#                  wire, and it is how +1V1 met +3V3 in the first draft.
#   check_pinmap   netlist vs the grblHAL board map, GPIO by GPIO, and each
#                  signal followed to the pin it must reach.
#
# Usage:  KICAD_CLI=kicad-cli sh tools/validate.sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p review
KICAD_CLI="${KICAD_CLI:-kicad-cli}"
PY="${PY:-python3}"
SCH=hardware/MACH3SIMPLEETH.kicad_sch

echo "== ERC =="
"$KICAD_CLI" sch erc --severity-all -o review/ERC.rpt "$SCH"
"$KICAD_CLI" sch erc --severity-all --format json -o review/ERC.json "$SCH"
"$PY" - <<'EOF'
import json, sys
d = json.load(open('review/ERC.json'))
bad, warn = [], []
# lib_symbol_mismatch: MAX3485 is a derived symbol (extends LTC2850xS8) that
# kilib embeds flattened; its pinout is checked in check_pinmap.
accepted = {'lib_symbol_mismatch'}
for sh in d['sheets']:
    for v in sh['violations']:
        line = '%s %s: %s %s' % (sh['path'], v['type'], v['description'],
                                 [i['description'] for i in v['items']])
        if v['severity'] == 'error' or v['type'] == 'multiple_net_names':
            bad.append(line)
        elif v['type'] not in accepted:
            warn.append(line)
for w in warn:
    print('warning:', w)
for b in bad:
    print('ERROR:', b)
print('ERC: %d errors, %d unexpected warnings' % (len(bad), len(warn)))
sys.exit(1 if bad else 0)
EOF

echo "== Netlist =="
"$KICAD_CLI" sch export netlist --format kicadsexpr -o review/net.net "$SCH"

echo "== Pin map vs grblHAL =="
"$PY" tools/check_pinmap.py

echo "== Exports =="
"$KICAD_CLI" sch export pdf -o review/MACH3SIMPLEETH_schematic.pdf "$SCH"
"$KICAD_CLI" sch export bom --fields 'Reference,Value,Footprint' \
  --exclude-dnp -o review/BOM.csv "$SCH"
echo "OK"
