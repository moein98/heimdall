#!/usr/bin/env sh
# Verify the MACH3-SIMPLE schematic and board.
#
# ERC alone proves very little. Two defects on the sister project passed ERC
# cleanly: a reverse-protection diode fitted backwards, and three indicator LEDs
# fitted backwards - both because pin 1 of a KiCad diode is the CATHODE. A
# third, on the EC9 project, was a wrong 74HC123 pin numbering that ERC could
# not see because the hand-made symbol declared matching wrong pin types.
#
# So this script also checks, by pin function rather than pin number, what
# check_design.py knows how to check, and then runs DRC on the board with
# schematic parity on - which is the check that catches a board that is legal
# geometry for the wrong circuit.
#
# There is no isolation barrier on this board and one ground, so the sister
# project's GND_PC / GND_M bridging test does not apply here.
#
# Usage:  KICAD_CLI='/d/KiCad/bin/kicad-cli.exe' sh tools/validate.sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p review

KICAD_CLI="${KICAD_CLI:-kicad-cli}"
command -v "$KICAD_CLI" >/dev/null 2>&1 || {
  echo "kicad-cli not on PATH. Set KICAD_CLI, e.g."
  echo "  KICAD_CLI='/d/KiCad/bin/kicad-cli.exe' sh tools/validate.sh"
  exit 1
}
PY="${PY:-$(dirname "$KICAD_CLI")/python.exe}"
SCH=hardware/MACH3SIMPLE.kicad_sch

echo "== ERC =="
"$KICAD_CLI" sch erc --severity-all -o review/ERC.rpt "$SCH"
"$KICAD_CLI" sch erc --severity-all --format json -o review/ERC.json "$SCH"

echo "== Netlist =="
"$KICAD_CLI" sch export netlist --format kicadsexpr -o review/net.net "$SCH"

echo "== Structural checks =="
"$PY" tools/check_design.py

echo "== Exports =="
"$KICAD_CLI" sch export pdf -o review/MACH3SIMPLE_schematic.pdf "$SCH"
"$KICAD_CLI" sch export bom --fields 'Reference,Value,Footprint' \
  --exclude-dnp -o review/BOM.csv "$SCH"

echo "== Coverage =="
# Undefined nodes, and a census against the drawing of the board in service.
# Not a pass/fail gate: the census lists every difference in part mix, and
# most are deliberate. Read it.
"$PY" tools/check_coverage.py || true

echo "== Bypass capacitors =="
# Each one must reach its own supply pin through its own copper; the
# schematic cannot say which pin a +5V-to-GND capacitor is for.
"$(dirname "$KICAD_CLI")/python.exe" tools/autoroute.py bypass || true

echo "== DRC =="
"$KICAD_CLI" pcb drc --refill-zones --schematic-parity --format json \
  -o review/DRC.json hardware/MACH3SIMPLE.kicad_pcb

# Are the custom rules being read at all? KiCad drops the whole .kicad_dru,
# without a message, if one rule in it will not parse - and a DRC run without
# them looks like an ordinary run with a few more findings. The rules make
# every surface-mount pad connect solid, so a surface-mount pad reported with
# thermal spokes means they are not in effect.
"$PY" -c "
import json
d = json.load(open('review/DRC.json', encoding='utf-8'))
smd = [v for v in d.get('violations', []) if v['type'] == 'starved_thermal'
       and any(i['description'].startswith('Pad ') for i in v['items'])]
if smd:
    print('  RULES NOT IN EFFECT: %d surface-mount pads report thermal spokes.' % len(smd))
    print('  hardware/MACH3SIMPLE.kicad_dru did not parse - KiCad ignored all of it.')
"

echo
echo "Expected: ERC 0 errors and 0 warnings; zero off-grid coordinates; DRC 0"
echo "unconnected items, 0 parity issues and no errors - only silkscreen warnings,"
echo "which are screw terminals whose bodies overhang the edge by design."
echo "A clean run does NOT mean the board works. Read docs/SPEC.md."
