#!/usr/bin/env sh
# Build and test the MACH3-SIMPLE firmware.
#
# Four steps, and the hex is written only if the first three pass:
#   1. the command logic, compiled and run on the PC
#   2. main.c on the PC, with the chip's registers as plain variables
#   3. the pin map, compared with the board's netlist
#   4. the firmware itself, for the ATmega328P
#
# Usage:  sh firmware/build.sh
# Then program it:  sh firmware/build.sh flash     (USBasp on J60)
set -eu
cd "$(dirname "$0")"

AVR="${AVR:-/d/software/avr-gcc/avr-gcc-16.1.0-x64-windows/bin}"
HOSTCC="${HOSTCC:-/d/software/mingw64/bin/gcc}"
AVRDUDE="${AVRDUDE:-/d/software/avrdude/avrdude.exe}"
PY="${PY:-python}"
OUT=build
mkdir -p "$OUT"

echo "== 1. command logic, on the PC =="
"$HOSTCC" -std=c99 -Wall -Wextra -Werror -O1 -o "$OUT/test_commands.exe" \
  test_commands.c commands.c
"$OUT/test_commands.exe"

echo "== 2. the firmware itself, registers modelled on the PC =="
# main.c unchanged, against hoststub/ in place of the AVR headers; the real
# avr-libc headers are still searched after it, for util/setbaud.h.
"$HOSTCC" -std=gnu99 -Wall -Wextra -Werror -O1 -DHOST_TEST \
  -Ihoststub -idirafter "$AVR/../avr/include" \
  -DF_CPU=16000000UL -DBAUD=9600 \
  -o "$OUT/test_main.exe" test_main.c commands.c
"$OUT/test_main.exe"

echo "== 3. pin map against the board =="
"$PY" check_pins.py

echo "== 4. firmware =="
"$AVR/avr-gcc" -mmcu=atmega328p -std=gnu99 -Os -Wall -Wextra -Werror \
  -DF_CPU=16000000UL -DBAUD=9600 \
  -o "$OUT/mach3simple.elf" main.c commands.c
"$AVR/avr-objcopy" -O ihex -R .eeprom "$OUT/mach3simple.elf" "$OUT/mach3simple.hex"
"$AVR/avr-size" --format=berkeley "$OUT/mach3simple.elf"
echo "hex       : firmware/$OUT/mach3simple.hex"

if [ "${1:-}" = "flash" ]; then
  echo "== 5. program, USBasp on J60 =="
  # Fuses first, then the flash, in one session. A new chip runs at 1 MHz
  # (internal RC, CKDIV8), too slow for the USBasp's default clock, hence
  # -B 32; the new fuses take effect only when avrdude lets go of the chip.
  #   low  FF  16 MHz crystal (Y1), full start-up delay, CKDIV8 off
  #   high D9  the factory value: ISP on, no bootloader
  #   ext  FD  brown-out reset at 2.7 V
  # Once the low fuse selects the crystal, the chip runs only with one fitted
  # and working: without it, even ISP stops answering.
  "$AVRDUDE" -c usbasp -p m328p -B 32 \
    -U lfuse:w:0xFF:m -U hfuse:w:0xD9:m -U efuse:w:0xFD:m \
    -U "flash:w:$OUT/mach3simple.hex:i"
fi
