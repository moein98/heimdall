#!/usr/bin/env sh
# Fabrication output for MACH3-SIMPLE.
#
# This REFUSES to run on a board with a DRC error, an unrouted connection or a
# difference from the schematic. Gerbers from a board like that are not a
# draft - they are a board that does not work, paid for and shipped, and no
# amount of looking at the Gerbers afterwards will find the missing track.
#
# Layers are named rather than taken from the board's own plot settings. The
# board is written by tools/build_pcb.py and nobody has ever opened its plot
# dialog, so whatever is stored there is a default nobody chose.
#
# Usage:  KICAD_CLI='/d/KiCad/bin/kicad-cli.exe' sh tools/fab.sh
set -eu
cd "$(dirname "$0")/.."

KICAD_CLI="${KICAD_CLI:-kicad-cli}"
command -v "$KICAD_CLI" >/dev/null 2>&1 || {
  echo "kicad-cli not on PATH. Set KICAD_CLI, e.g."
  echo "  KICAD_CLI='/d/KiCad/bin/kicad-cli.exe' sh tools/fab.sh"
  exit 1
}
PY="${PY:-$(dirname "$KICAD_CLI")/python.exe}"
PCB=hardware/MACH3SIMPLE.kicad_pcb
NAME=MACH3SIMPLE
OUT=fab
LAYERS=F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts

echo "== DRC, errors only, zones filled =="
"$KICAD_CLI" pcb drc --refill-zones --schematic-parity --severity-error \
  --format json -o review/DRC_fab.json "$PCB"

"$PY" -c "
import json, sys
d = json.load(open('review/DRC_fab.json', encoding='utf-8'))
v, u, p = (d.get(k, []) for k in ('violations', 'unconnected_items', 'schematic_parity'))
print('  errors %d   unconnected %d   parity %d' % (len(v), len(u), len(p)))
bad = [s for n, s in ((len(v), 'DRC errors'), (len(u), 'unrouted connections'),
                      (len(p), 'schematic-parity errors')) if n]
if bad:
    print()
    print('  REFUSING to write fabrication files: ' + ', '.join(bad) + '.')
    print('  Fix them and run this again.')
    sys.exit(1)
print('  clean - writing fabrication files')
"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "== Gerbers =="
"$KICAD_CLI" pcb export gerbers --layers "$LAYERS" --no-protel-ext \
  --subtract-soldermask -o "$OUT/" "$PCB"

echo "== Drill =="
"$KICAD_CLI" pcb export drill --format excellon --drill-origin absolute \
  --excellon-units mm --excellon-separate-th --generate-map \
  --map-format gerberx2 -o "$OUT/" "$PCB"

echo "== Placement, for assembly =="
"$KICAD_CLI" pcb export pos --format csv --units mm --side front \
  --exclude-dnp -o "$OUT/$NAME-pos.csv" "$PCB"

echo "== Bill of materials =="
cp docs/BOM_ORDER.md "$OUT/$NAME-BOM.md"
cp review/BOM.csv "$OUT/$NAME-BOM.csv"

echo "== Pictures to check against =="
"$KICAD_CLI" pcb export pdf --mode-multipage --layers F.Cu,B.Cu \
  --common-layers Edge.Cuts -o "$OUT/$NAME-copper.pdf" "$PCB"
"$KICAD_CLI" pcb export pdf --mode-single \
  --layers Edge.Cuts,F.Silkscreen,F.Fab --sketch-pads-on-fab-layers \
  -o "$OUT/$NAME-assembly.pdf" "$PCB"

echo "== Archive for the board house =="
"$PY" -c "
import os, zipfile
out, name = '$OUT', '$NAME'
keep = ('.gtl', '.gbl', '.gts', '.gbs', '.gtp', '.gto', '.gbo', '.gm1',
        '.gbr', '.drl')
# Not the drill maps. They are Gerbers too, and a board house that takes
# every .gbr in the archive as a layer will try to make one of them.
files = sorted(f for f in os.listdir(out) if f.lower().endswith(keep)
               and 'drl_map' not in f)
with zipfile.ZipFile(os.path.join(out, name + '-gerbers.zip'), 'w',
                     zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(os.path.join(out, f), f)
print('  %s-gerbers.zip: %d files' % (name, len(files)))
for f in files:
    print('    %-44s %8d bytes' % (f, os.path.getsize(os.path.join(out, f))))
"

echo
echo "Done. Send fab/$NAME-gerbers.zip to the board house: 2 layers, 1.6 mm FR4,"
echo "1 oz copper, $(sed -n 's/.*BOARD_W, BOARD_H = \(.*\)/\1/p' tools/build_pcb.py) mm."
