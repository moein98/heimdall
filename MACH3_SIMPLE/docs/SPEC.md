# MACH3-SIMPLE — what this board is

A reproduction of the Mach3 breakout board already in service on this machine,
rebuilt in KiCad so it can be re-ordered and, later, extended. It is deliberately
**not** the sister project (`MACH3_BOB_A0`): no isolation, no charge pump, no
THC pulse generator, no 0–10 V spindle output. Those were taken out on request
and can be added back one at a time.

## At a glance

| | |
|---|---|
| Board | 150.5 × 137.9 mm, 2 layers, 1.6 mm |
| Parts | 133 |
| Nets | 159 |
| Ground | one, continuous. There is **no galvanic isolation** on this board |
| Supplies | +5 V and +24 V, both from outside. Nothing is generated on board |

## Signal path

**Outputs — six axes.** LPT port 1 drives two 74HC245 buffers (`U1`, `U2`), and
each axis leaves on a 3-way terminal as PUL / 0V / DIR at 5 V. Port 1 pins are, as PUL/DIR:
X 1/2, Y 3/4, Z 5/6, A 7/8, B 9/14, C 17/16.

Each of the twelve buffer inputs is held to ground by 10 kΩ, in three
four-resistor arrays (`RN1`–`RN3`) beside the buffers. With the PC off or the
cable out, an input with nothing on it floats, and a floating STEP line is a
buffer that can step a motor with no computer attached. The board in service
has a resistor network beside each buffer for this; it was missing here until
its owner noticed.

**Inputs — homes and E-stop.** Sensor returns come in through two PC847
four-channel optocouplers (`U10`, `U11`) and go back to the PC on port 1
pins 10, 11, 12, 13 and 15 — X, Y, Z and A home, and C home on 15. All six arrive on one 6-way terminal,
one wire per channel, marked EMG C A Z Y X. There is no third screw per channel:
a **PNP** sensor takes its +24 V and 0 V from the 24 V supply terminal, exactly
as on the board in service.

**Handwheel.** One encoder, two jobs. `U3`, a 74HC4053 analog switch, sends MPG
A and B either to port 2 pins 12 and 13, where Mach3 reads them as the
handwheel, or to pins 10 and 11, where it reads them as THC up and down. The
MCU picks, on `SendSerial('T')` for THC and `SendSerial('t')` for jog. All four
LPT pins are pulled up, so whichever pair is not selected sits high and inactive
rather than floating. This is the trick the board in service uses, and it is why
there is no separate THC terminal.

**Relays.** Six SPDT relays, each on its own 3-way NO / COM / NC terminal, each
driven by a 2N7002 from an ATmega328P (`U21`) over RS232 (`U20`, MAX3232).
The macros are printed on the board beside each terminal: `'A'`…`'F'` turn a
relay on, `'a'`…`'f'` turn it off.

## Where the geometry came from

Not from a guess. The owner supplied the assembly drawing of the board in
service, and every connector, relay and identifiable chip here is placed on the
position of its counterpart there. `tools/check_placement.py` measures it:
all 51 anchored parts land within 0.4 mm of it, apart from the few moved on
purpose, each listed with its reason in `NUDGE` in `build_pcb.py` - the 24 V
diode, for one, sat on its terminal's legend.

- **Left edge** — LPT port 1 (top), LPT port 2 (bottom), 62.8 mm apart.
- **Top edge** — EMG & HOME (6-way), handwheel (4-way), 5 V in, 24 V in.
  The top left is empty because the upper D-sub's shell is in the way.
- **Right edge** — the six axis terminals at a 16.1 mm pitch, and RS232 below
  them, set apart.
- **Bottom edge** — six relays at a 16.2 mm pitch, each directly above its own
  NO/COM/NC terminal, with its flyback diode and driver in the rows above.
- **Interior** — the input channels in a row under EMG & HOME; protection and
  bulk under the two supply terminals; the two 74HC245 beside the axis
  terminals, each with its input pull-down arrays alongside; the MCU in the
  middle; the RS232 transceiver beside its own terminal.

### How it was measured

`tools/read_ref.py` reads the drawing as vectors and writes `review/ref.json`.
Three things about that drawing had to be found before the numbers were right,
and each one had produced a wrong board first:

1. **The board outline is in it.** Fourteen purple strokes, the only thing on
   the page in that ink. Earlier the board size was inferred from how far apart
   the outermost parts were, plus a margin; that gave 168 × 145.
2. **Scale comes from a long baseline.** The drawing rounds positions to about
   a third of a point, so neighbouring D-sub pins read 6.00, 6.31 and 6.69 pt
   apart in turn. The scale is taken from pins 1 to 13 as one span - exactly
   12 × 2.77 mm - not from any single gap.
3. **The labels and the geometry are two frames.** Every visible label is
   drawn in strokes; the searchable text is an invisible overlay, printed 3.5 %
   larger than the geometry it sits on. The two are tied together by features
   in both - the six relay bodies for x, the two D-subs for y - and the two
   fits agree to 0.22 %, which is the check that they mean something.

The part numbers of the chips are not in the drawing at all, visible or
otherwise. See *Open questions*.

## One deliberate departure

**The relays are turned on their side.** A JQC-3FF is 19.8 × 16.2 mm; the
relays on the drawing sit at a 16.2 mm pitch with their pad field 12.0 × 14.7 -
which is a JQC-3FF's 14.2 × 12.0 turned through 90 degrees. So the board in
service turns them too, and their courtyards touch there as they do here.

## What has been checked, and what that is worth

`sh tools/validate.sh` runs: ERC, the structural checks in `check_design.py`
(sheet coverage, optocoupler orientation, LED polarity, grid), the coverage
checks in `check_coverage.py`, and DRC with schematic parity. ERC, the
structural checks and parity pass with zero findings, and DRC finds nothing but
silkscreen.

`check_coverage.py` exists because the missing pull-downs passed every one of
the others. It looks for nets that reach a chip input with nothing to drive or
hold them - which ERC cannot see, since a connector pin is passive and satisfies
an input - and it counts the parts on the drawing against the parts here. The
one net it still reports, `RS232_RX`, is held by the MAX3232's own internal
pull-down. `check_placement.py` measures the placement against the drawing.

That is worth less than it sounds. A clean ERC proves nothing about a sheet
KiCad never managed to read — on the sister project an unescaped quote made a
whole sheet unparseable and 64 parts vanished from the netlist while ERC
reported zero violations. That is why `check_design.py` counts parts per sheet.
DRC says the geometry is legal, not that it is good.

**Nothing here has been built or powered.**

## State of the routing

**Fully routed.** 342 of 342 connections, ground included, with 0 unconnected
items, 0 clearance violations and 0 differences from the schematic. What DRC
still reports is silkscreen warnings only: terminal bodies that overhang the
board edge by design, and the outlines of neighbouring relays, which sit on
the drawing's 16.2 mm pitch and so share an edge.

The route comes from Freerouting 2.4.1, run headless: `tools/autoroute.py`
exports a Specctra DSN through KiCad's own `pcbnew` module, Freerouting routes
it, and the session is imported back. 1486 track segments - 1005 on the front,
481 on the back - and 307 vias, 129 of them ground stitching.

Four things were learned getting there, and each is recorded in the code:

- **Neck-downs.** The minimum track width is 0.15 mm, not 0.2. The only tracks
  below 0.2 are where the router narrows a track to 0.19 mm to reach a SOIC or
  TQFP pad, and all of them are signals at a few milliamps.
- **Power clearance.** The Power class runs at 0.2 mm clearance, not 0.25. At
  0.25 a supply track cannot enter a 0.8 mm-pitch TQFP pad at all, and the
  MCU's three supply pins went unrouted.
- **Ground is routed, not assumed.** With the pour in place KiCad exports
  ground as a plane and Freerouting never draws a ground track; once the
  signals were in, the pour was cut into islands and 25 ground pads reached
  nothing. Ground is now routed like any other net and the pour filled over it.
- **Contact class.** Relay A's NC contact, beside the lower D-sub, is the
  tightest route on the board. At 1.0 mm and 0.5 mm clearance it would not
  route; the owner confirmed these relays never switch mains, so the clearance
  came down to 0.3. It then routed - until the mounting holes moved, and it
  stopped again. At 0.8 mm it routes with room to spare. That is about 2.4 A
  on 1 oz copper against 2.8 A at 1.0 mm; neither is the relay's 10 A, so a
  load that draws more than a couple of amps wants its own wiring to the relay.

Net classes, in `hardware/MACH3SIMPLE.kicad_pro`:

| Class | Width | Clearance | Nets |
|---|---|---|---|
| Default | 0.25 mm | 0.2 mm | everything else |
| Power | 0.6 mm | 0.2 mm | +5V, V24, GND, VIN* |
| Contact | 0.8 mm | 0.3 mm | relay contacts, K?_* - low voltage only |

To re-route after a placement change:

    python tools/build_pcb.py --force
    D:/KiCad/bin/python.exe tools/autoroute.py export
    java -jar freerouting.jar --gui.enabled=false -de review/route/MACH3SIMPLE.dsn -do review/route/MACH3SIMPLE.ses -mp 100
    D:/KiCad/bin/python.exe tools/autoroute.py import
    D:/KiCad/bin/python.exe tools/autoroute.py stitch

Java 25 and Freerouting live in `D:\software`. `tools/route.py`, the earlier
router, is superseded and no longer used for this board.

## Relay drive

Each relay is switched by a 2N7002 MOSFET straight off an MCU pin: 1 kΩ in the
gate to slow the edges, 10 kΩ gate to ground so every relay stays off while the
MCU is in reset or unprogrammed, and a 1N4148 across each coil.

The board in service puts an optocoupler in each of these, and that was
considered and not copied. An optocoupler isolates only if the side it drives
has a ground of its own, and this board has one ground by design. The coil
current would return through the same copper either way; six optocouplers
would buy nothing but six more parts and a current-transfer ratio that falls
with age. What keeps a coil's turn-off spike away from the MCU is the diode
across the coil - the spike circulates in that loop and goes no further.

What the optocouplers would have given, and this does not, is protection
against one failure: a MOSFET that dies gate-to-drain puts 24 V on an MCU pin
through 1 kΩ.

### Decoupling

A 100 nF sits against every supply pin that matters: MCU pins 4 and 6 (VCC)
and 18 (AVCC), pin 20 of each 74HC245, and pin 16 of the MAX3232. That last
one was missed at first: the MAX3232's four capacitors are all its charge
pump's, and one of them sits on +5V as V+'s reservoir, which looks like a
bypass and is not one. The board in service has it, and names it for its pin -
Cvcc16. The capacitor count now matches that board's: 19. These were offered early on as
extras and declined, and put back when the drawing of the board in service
turned out to have them - four round its MCU, one beside each buffer. On a
board with one ground and six relay coils switching on it, they are what keeps
the MCU's supply clean, and they matter more than an optocoupler would have.

A bypass capacitor is only as good as the copper between it and its pin, and
nothing in the schematic can check that - they are all +5V to GND.
`build_pcb.py` places each one against a named pin (`PIN_CAPS`), and
`autoroute.py bypass` walks the routed copper afterwards: every one reaches its
own pin in 1.4 to 1.8 mm.

### Lines an MCU pin drives

An MCU pin drives nothing through reset - at every power-up, and for good on a
chip that has not been programmed yet. Anything listening on such a line needs
its own resistor. The relay gates had one each from the start (`R70`-`R75`);
the handwheel select line did not, and until the firmware woke up the 4053
could hand the handwheel to the THC pins at random. `R52` now holds it low -
jog, the same state `SendSerial 't'` selects. `check_coverage.py` looks for this
now; it did not before, because an MCU pin is marked bidirectional and was
being counted as a driver.

AREF, pin 20 of the MCU, is open. It had been tied to ground when its
capacitor was removed, which is not the same as removing a part: an internal
switch connects the selected ADC reference to that pin, and on ground it would
short AVCC the first time any firmware called `analogRead`.

## Open questions

`tools/check_coverage.py` counts every part on the drawing against this board.
These are the differences it cannot explain, and they need someone with the
board in service in front of them:

- **`U17` and `U18`** — two 20-pin chips beside the parallel ports, each paired
  with a resistor network. Nothing here stands in for them. They may buffer the
  port lines; they may do something else.
- **`U24`** — a 14-pin chip near the MCU. If it is a 74HC14, the sensor inputs
  there pass through Schmitt triggers and here they do not.
- **A ferrite bead** on a supply rail there, none here.

The part numbers printed on `U17`, `U18` and `U24` would settle the first two.

Known and intended, not open: the MCU is a 32-pin ATmega where that board has a
44-pin part; the 10-pin programming header there was left out on request; eight
single-channel input optocouplers there are two four-channel parts here;
and the relays are driven by MOSFETs rather than optocouplers, for the
reasons under *Relay drive*.

## Mounting

Four M3 holes, one in each corner, 4 mm in from both edges. The drawing does
not show the holes on the board in service - every 3.2 mm circle in it is an
LED - so this is the usual inset for an M3 standoff rather than a measurement.
If the board has to drop onto the old standoffs, measure them first.

## Design rules

`hardware/MACH3SIMPLE.kicad_dru` holds two rules: surface-mount pads connect
to the pour solid, and a through-hole ground pad needs only one thermal spoke,
since its own ground track is what connects it.

**KiCad ignores the whole file, without a word, if one rule in it will not
parse.** The spoke rule was first written `(min 1)` - the form for distances,
not counts - and DRC carried on as if the file were empty: the solid-SMD rule
went too, and surface-mount pads started failing for want of spokes they were
never meant to have. `validate.sh` now checks for exactly that symptom and says
so.

## Fabrication

    KICAD_CLI='/d/KiCad/bin/kicad-cli.exe' sh tools/fab.sh

It refuses to write anything if DRC finds a single error, an unrouted
connection or a difference from the schematic. Otherwise `fab/` gets:

- `MACH3SIMPLE-gerbers.zip` - **this is what goes to the board house.** Eight
  Gerber layers (copper, mask, paste and silkscreen front and back, outline)
  and the plated and unplated drill files. 2 layers, 1.6 mm FR4, 1 oz copper,
  150.5 x 137.9 mm.
- `MACH3SIMPLE-pos.csv` - part positions, for machine assembly.
- `MACH3SIMPLE-BOM.md` / `.csv` - the bill of materials.
- `MACH3SIMPLE-copper.pdf`, `-assembly.pdf` - to check against.

The drill files were checked against the board: 456 plated holes, which is 307
vias and 149 pad holes exactly, and 4 unplated - the mounting holes. The drill
maps are left out of the archive; they are Gerbers too, and a board house that
takes every Gerber it is sent as a layer would try to make one.

## Firmware

`firmware/` - C for avr-gcc, no Arduino. `sh firmware/build.sh` builds it;
`sh firmware/build.sh flash` also programs it, with a USBasp on `J60` (the
standard 10-pin AVR ISP header): fuses and flash in one session. The fuses
are low `FF` (16 MHz crystal, CKDIV8 off), high `D9` (factory value) and
extended `FD` (brown-out reset at 2.7 V). Once the low fuse is written the
chip runs only with `Y1` fitted and working - without it even ISP stops
answering - so the crystal has to be on the board before the first flash.

| Byte | Does |
|---|---|
| `A`...`F` | relay on |
| `a`...`f` | relay off |
| `T` | handwheel to the THC pins (`MPG_SEL` high) |
| `t` | handwheel to jog (`MPG_SEL` low) |
| `?` | report only |

Every accepted command is answered with the whole state, e.g.
`R:AbcdEf M:thc`, and blinks `D30`. Anything else is ignored and gets no
reply. 9600 8N1 - the Mach3 serial port must match.

Three things are there for the machine rather than the code: reception is
interrupt-driven into a 32-byte buffer, so `abcdef` sent at once all lands; a
byte that arrives with a framing, overrun or parity error is dropped rather
than acted on; and a 1 s watchdog, so if the program stops the chip resets,
its pins go to inputs and the gate and select resistors turn every relay off
and put the handwheel on jog.

`build.sh` will not write a hex unless three checks pass first:

1. `test_commands.c` - every one of the 256 byte values, from a known state.
2. `test_main.c` - `main.c` itself, compiled on the PC against
   `firmware/hoststub/`, where every AVR register is a plain variable. It
   checks what setup leaves in the registers (directions, pull-ups, UBRR 51,
   8N1, watchdog, interrupts), that each command moves exactly its own pin,
   that garbled bytes are dropped in the interrupt, bursts, a buffer flood,
   and the LED.
3. `check_pins.py` - each pin in `pins.h` against the MCU pin the netlist
   puts on that net.

None of this checks timing; that needs a chip.

### Clock

A 16 MHz crystal, `Y1`, with 22 pF load capacitors (`C33`, `C34`). It was left
off at first and put back before the first order: the internal RC oscillator
is trimmed only to within 10 % at the factory, and a UART needs both ends
within about 2 % of each other. At 16 MHz, 9600 baud is UBRR 103, 0.2 % off.

Buy a crystal specified for a load capacitance of 18 to 20 pF; the 22 pF
capacitors suit that (C = 2 x (CL - about 5 pF of stray)). `build_pcb.py`
places the three against pins 7 and 8 (`NEAR_MCU`), turned so that both
signals reach their pads on the top layer, 8 mm each, with no via.
