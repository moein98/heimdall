#!/bin/sh
# Build grblHAL for MACH3-SIMPLE-ETH (RP2350B, 8 axes, W5500).
#
# Needs: git, cmake, make, arm-none-eabi-gcc (with newlib), and a Pico SDK
# 2.1.1 or later with the lwip and tinyusb submodules - set PICO_SDK_PATH.
# Output: build/grblHAL.uf2 - hold BOOT, plug in USB, copy it to the drive.
#
# The driver is pinned to the commit this board map was tested against.
# Bumping GRBLHAL_REV is fine, but rebuild and read the warnings.
set -e

GRBLHAL_REV=12327965f03c0218afd51d248ee166cfbe902f1e
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$HERE/work}
: "${PICO_SDK_PATH:?set PICO_SDK_PATH to a Pico SDK 2.1.1+ checkout}"

if [ ! -d "$WORK/RP2040" ]; then
    mkdir -p "$WORK"
    git clone -q https://github.com/grblHAL/RP2040 "$WORK/RP2040"
fi
cd "$WORK/RP2040"
git checkout -q -f "$GRBLHAL_REV"
git submodule update -q --init --depth 1
git apply "$HERE/my_machine.patch" "$HERE/cmake-n-axis.patch"
cp "$HERE/boards/my_machine_map.h" boards/

# PICO_BOARD pimoroni_pga2350 is an RP2350B with 16 MB flash - the same
# chip and flash size as this board. N_AXIS goes to CMake, not my_machine.h:
# some files include grbl.h first and would otherwise build for 3 axes.
rm -rf "$HERE/build"
cmake -S . -B "$HERE/build" -DPICO_BOARD=pimoroni_pga2350 \
      -DADD_ETHERNET=ON -DN_AXIS=8 > "$HERE/build.log" 2>&1
make -C "$HERE/build" -j"$(nproc)" >> "$HERE/build.log" 2>&1 || {
    grep -E 'error' "$HERE/build.log" | head -20; exit 1; }
arm-none-eabi-size "$HERE/build/grblHAL.elf"
echo "built $HERE/build/grblHAL.uf2"
