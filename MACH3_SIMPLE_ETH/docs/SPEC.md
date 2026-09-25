# MACH3-SIMPLE-ETH - specification (draft 0)

MACH3-SIMPLE with the parallel ports replaced by Ethernet. The PC no longer
makes step pulses: an RP2350B on the board runs grblHAL, plans the motion and
makes the pulses itself, and the PC (or a tablet, or nothing, from SD card)
only sends G-code and shows status.

This draft fixes the architecture and the pin map, and proves the pin map
with a real grblHAL build (`firmware/grblHAL/build.sh`). There is no
schematic or board yet.

## What it keeps from A1

- 24 V single supply, 5 V made on board (LM2596S-5.0), same input terminal.
- Opto-isolated 24 V sensor inputs (PC847, reverse diode across each LED).
- Buffered 5 V step/dir outputs on 3-way terminals, PUL / 0V / DIR.
- Six relays with their terminal legends.
- The isolated VFD port: 0-10 V (`AVI`/`ACM`), `FWD`, `REV`, `AUX`, `DCM`,
  B2412S isolated supply, PC847 across the barrier, LM358 output, `RV1` trim.
- Handwheel, switchable between jog and THC.

## What changes

| | A1 | ETH |
|---|---|---|
| Link to the PC | two LPT ports + RS232 | **Ethernet** (W5500, 10/100), plus USB-C for setup |
| Motion | Mach3 on the PC | **grblHAL on the board**; PC runs any sender, or none |
| Axes | 6 | **8 independent, coordinated**: X Y Z A B C U V |
| Relays | ATmega328P over RS232, `SendSerial` | MCP23017 over I2C, G-code `M62`-`M65` |
| Spindle | 0-10 V from LPT PWM | same 0-10 V, **plus RS485 Modbus** for VFDs that take it |
| THC | handwheel lines to Mach3 | grblHAL plasma plugin: Arc OK, THC up, THC down |
| Handwheel | A/B lines to Mach3 | a small MCU reads it and jogs grblHAL over UART (MPG mode 2) |
| Stand-alone | no | SD card: run a job with no PC |
| UI | Mach3 | any grblHAL sender, the built-in web UI, or our own |

The ATmega328P and MAX232 go. So do the LPT connectors and the pull-ups on
their lines.

## Firmware

grblHAL, RP2040/RP2350 driver, board map `firmware/grblHAL/boards/my_machine_map.h`.
Built with `N_AXIS=8` and:

| Option | Setting | For |
|---|---|---|
| `ADD_ETHERNET` + `_WIZCHIP_ 5500` | on | Telnet (23), WebSocket, FTP |
| `WEBUI_ENABLE 3` | on | ESP3D-WebUI served from the board's flash |
| `SDCARD_ENABLE 1` | on | jobs from SD |
| `SPINDLE0` / `SPINDLE1` | `PWM0` / `MODVFD` | 0-10 V spindle, Modbus spindle; picked with `$395` |
| `MODBUS_ENABLE 2` | stream 0, DE/RE on aux out 0 | RS485 |
| `MPG_ENABLE 2`, `MPG_STREAM 1` | UART1 | handwheel MCU; `0x8B` toggles MPG mode |
| `PLASMA_ENABLE 1` | on | THC |
| `MCP23017_ENABLE 1` | port A out, port B in | relays, spare inputs |

Checked in the build, not only in the source: `N_MOTORS == 8`,
`MPG_STREAM == 1`, `MODBUS_RTU_STREAM == 0`, V axis on GP9 / GP17 / GP33, and
the plasma, MCP23017, WebUI, SD, W5500, Telnet, WebSocket, FTP and Modbus
code all linked in. Flash 527 KB, RAM 110 KB static, of 520 KB.

`N_AXIS` must come from CMake (`-DN_AXIS=8`, `cmake-n-axis.patch`), not from
`my_machine.h`. Some driver files include `grbl.h` before `my_machine.h` and
were built for 3 axes when it was set there - the image was 25 KB smaller and
would have mixed 3-axis and 8-axis structures.

## RP2350B pin map

All 48 GPIO are used. Pins that grblHAL needs consecutive are marked.

| GPIO | Signal | Notes |
|---|---|---|
| 0, 1 | UART0 TX, RX | RS485 transceiver, Modbus VFD |
| 2-9 | STEP X Y Z A B C U V | PIO, **consecutive** |
| 10-17 | DIR X Y Z A B C U V | **consecutive** (`GPIO_SHIFT10`) |
| 18 | ENABLE | all drivers |
| 19 | SD CS | |
| 20-23 | SPI0 MISO, W5500 CS, SCK, MOSI | W5500 and SD share SPI0 |
| 24 | W5500 INT | |
| 25 | RS485 DE/RE | aux output 0 |
| 26-33 | LIMIT X Y Z A B C U V | |
| 34 | E-STOP | grblHAL reset input |
| 35 | FEED HOLD | |
| 36 | CYCLE START | |
| 37 | PROBE | |
| 38 | ARC OK | plasma plugin |
| 39 | THC UP | plasma plugin |
| 40 | THC DOWN | plasma plugin |
| 41 | SPINDLE PWM | to the isolated 0-10 V stage |
| 42, 43 | UART1 TX, RX | handwheel MCU |
| 44 | SPINDLE ENABLE | VFD `FWD` |
| 45 | SPINDLE DIR | VFD `REV` |
| 46, 47 | I2C1 SDA, SCL | MCP23017, optional FRAM |

W5500 reset is on the board reset, so it needs no GPIO. Every alternate
function above was checked against the SDK's pin-function table
(`io_bank0.h`): UART0 on 0/1, UART1 on 42/43, SPI0 on 20-23, I2C1 on 46/47.
GP44/45 look like UART1 by the RP2040 pattern but are UART0 on the
RP2350B - the first draft had that wrong.

MCP23017 port A: relays A-F, spindle `AUX`, status LED. Port B: 8 spare
inputs (door, tool setter, ...).

## Circuit notes for the schematic

- **3.3 V logic.** The RP2350 is a 3.3 V part. A1's 74AC245 and 74HC14 see
  3.3 V as low-ish (V<sub>IH</sub> 3.5 V at 5 V supply). Use **74ACT245**
  (TTL thresholds, 24 mA) for step/dir, three of them for 17 lines, and
  **74HCT14** in the spindle channel.
- **Inputs.** 15 opto inputs (8 limits, E-stop, hold, start, probe, Arc OK,
  THC up, THC down) = four PC847, one channel spare. Pull-ups to **3.3 V**,
  not 5 V.
- **Relays.** MCP23017 on 3.3 V gives a 3.3 V gate: use a logic-level FET
  (AO3400A class) instead of 2N7002.
- **Power.** 24 V -> LM2596S-5.0 (as A1) -> 3.3 V LDO, 800 mA class. W5500
  alone is about 130 mA. The RP2350's core supply is its internal switcher:
  3.3 uH inductor and the layout from the RP2350 hardware design guide.
- **Clock and flash.** 12 MHz crystal, W25Q128 (16 MB) QSPI flash, matching
  the `pimoroni_pga2350` board file the firmware is built with.
- **Ethernet.** W5500, 25 MHz crystal, a magjack with integrated magnetics
  (HR911105A class), the W5500 reference layout for the differential pairs.
- **Handwheel.** A small MCU (an RP2040, or an ATmega328P as on A1) reads the
  quadrature wheel and axis/step switches and sends jog commands on UART1.
  grblHAL's RP driver has no quadrature input of its own for this.
- **ESD / EMC.** TVS on the Ethernet and RS485 lines; the RS485 port gets a
  termination jumper.

## LinuxCNC

Remora (LinuxCNC firmware for microcontrollers) has no RP2350 port. Its
RP2040 + W5500 port builds for RP2350A and RP2350B after renaming three
interrupt constants (`firmware/remora/remora-rp2350.patch`). It is untested on
hardware, its pins would need remapping to this board, and its step
generator tops out near 20 kHz per axis (40 kHz base thread) against grblHAL's
hundreds of kHz from PIO. It is an option for later, not a design goal.

## Licences

grblHAL is GPLv3: firmware shipped on a board must come with its source. A
UI that talks to the board over the network is a separate program and is not
bound by that. Reference designs looked at: PicoCNC (MIT), PicoBOB-DLX and
Flexi-HAL (CERN-OHL-S, copying circuits from them makes this board
CERN-OHL-S too). Nothing has been copied from them.

## Next

1. Schematic, sheet by sheet, generated like A1's (`tools/build_project.py`).
2. Board: same 24 V corner and VFD corner as A1, Ethernet and USB where the
   LPT ports were.
3. Handwheel MCU firmware.
4. Our own UI: can start now against the grblHAL simulator, before hardware.
