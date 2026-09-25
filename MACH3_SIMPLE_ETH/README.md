# MACH3-SIMPLE-ETH (draft 0)

MACH3-SIMPLE with Ethernet instead of the parallel ports: an RP2350B runs
grblHAL on the board, eight independent coordinated axes, W5500 Ethernet,
the A1 relays, inputs and isolated VFD port, plus RS485 Modbus, SD card and
a web UI served by the board.

So far: architecture and pin map (`docs/SPEC.md`), a grblHAL build that
proves the pin map, and the schematic (ERC clean, checked against the
firmware's pin map). No board layout yet.

| Folder | What is in it |
|---|---|
| `docs/SPEC.md` | the design, the RP2350B pin map, circuit notes, schematic status |
| `hardware/` | KiCad 10 schematic, 8 sheets - generated, do not edit by hand |
| `tools/` | `build_project.py` (generates the schematic), `check_pinmap.py`, `validate.sh` |
| `review/` | ERC report, netlist, schematic PDF, BOM |
| `firmware/grblHAL/` | board map, `my_machine.h` and CMake patches, `build.sh` |
| `firmware/remora/` | a three-line patch that builds Remora (LinuxCNC) for RP2350 - untested |

    PICO_SDK_PATH=/path/to/pico-sdk sh firmware/grblHAL/build.sh

    python3 tools/build_project.py     # KICAD_SYMBOL_DIR = KiCad's symbol library
    KICAD_CLI=kicad-cli sh tools/validate.sh
