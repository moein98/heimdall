#!/bin/sh
# Board to PNG for review: copper + silk + courtyards, front view.
set -e
cd "$(dirname "$0")/.."
kicad-cli pcb export svg --mode-single --fit-page-to-board --exclude-drawing-sheet \
  --layers "Edge.Cuts,F.Cu,B.Cu,F.SilkS,F.CrtYd,F.Fab" -o review/place.svg hardware/MACH3SIMPLEETH.kicad_pcb >/dev/null
