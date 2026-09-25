# MACH3-SIMPLE — what this board is (revision A1)

A reproduction of the Mach3 breakout board already in service on this machine,
rebuilt in KiCad so it can be re-ordered and, later, extended. It is deliberately
**not** the sister project (`MACH3_BOB_A0`): no isolation of the axis outputs,
no charge pump, no THC pulse generator. Those were taken out on request and can
be added back one at a time. A1 added back two things - an on-board 5 V supply
and the 0-10 V spindle output, with direction - and fixed four A0 defects;
see *What A1 changed*.

## At a glance

| | |
|---|---|
| Board | 150.5 × 137.9 mm, 2 layers, 1.6 mm |
| Parts | 178 (167 to buy; 6 test points, 4 mounting holes, 1 not fitted) |
| Nets | 184 |
| Ground | one, continuous. **No galvanic isolation**, except the VFD port |
| Supplies | **24 V only**, from outside. +5V is made on the board by an LM2596S-5.0 buck (`U4`) |
| VFD port | `J5`: isolated 0-10 V speed (`AVI`/`ACM`) and FWD/REV/AUX contacts (`FWD`/`REV`/`AUX`/`DCM`) |

## What A1 changed

| | A0 | A1 | Why |
|---|---|---|---|
| 5 V supply | a terminal of its own, `J3`, with a fuse and a series Schottky that left the rail at 4.6 V | gone; `U4` makes 5.0 V from V24 | one supply for the cabinet, at the owner's request |
| Relay drivers | `Q1`-`Q6` with drain and source swapped | fixed | see *Relay drive* - every relay was stuck on |
| Top-edge legends | reversed on `J4`, `J30` and `J20` | fixed | see *Terminal legends* |
| Input optocouplers | PC847 on SOIC-16 | on SMD DIP-16 (2.54 mm) | PC847 is not made in a 1.27 mm package; A0's footprint fitted nothing |
| Opto LED protection | promised, not there | `D20`-`D25` | a sensor lead that goes negative puts more than the LED's 6 V reverse rating across it |
| Spindle | none | isolated 0-10 V and FWD/REV | see *Spindle* |
| Input layout | passives packed into a band | a column per channel, under its own screw | the band no longer fitted; see *Inputs* |

### And from A1's own design review

| | Before | After | Why |
|---|---|---|---|
| Relay terminal legends | on F.Fab only - not printed | `RELAY A` and `NO COM NC` under each screw on the back silkscreen, `RELAY A`-`F` on the front | the six relay terminals carried no marking at all |
| `R80`-`R85` | 4k7 0603 | 10k | (24-2)²/4700 = 103 mW in a 100 mW part, for as long as a relay is on. Now 48 mW; the LED runs at 2 mA |
| `U1`, `U2` | 74HC245 | 74AC245, same pads | an opto-input stepper driver takes 10-15 mA; a 74HC245 is specified to 6 mA an output and 70 mA through its supply pins, and `U1` has eight outputs |
| `J4` | 2 screws | 4: `+24 0V` sensors, `+24 0V` in | a PNP sensor takes its supply from here, and seven wires do not go under one screw. The sensor pair is after `F2` and `D2`; the input pair is where the board in service has its 24 V terminal |
| `C2` | 100 µF 50 V, 6.3 × 7.7 | 47 µF 50 V | the larger part is not made in that can |
| Indicators | designators only | `5V`, `24V`, `SERIAL`, `A`-`F`, `10V ADJ` | a designator says which part, not what it means |
| Test points | none | `TP1`-`TP3` GND/5V/24V, `TP4`-`TP6` ACM/12V/AVI | bring-up without probing component legs |
| Isolation | a pour boundary only | a dashed line and `ISOLATED` on the silkscreen | so nobody ties the VFD side to the board's ground |
| Buck switch node | 17 mm, two vias, autorouted | 14 mm on the top layer, no vias (`SW_ROUTE`, locked) | the one net that swings 24 V at 150 kHz |
| Handwheel supply | +5V straight out | through `F3`, a 200 mA PTC | a short in the handwheel cable no longer takes down the MCU |
| MCU reset | 10k only | 10k and 10 nF | relay coils switching on a shared ground |
| Spare opto channel | unused | `AUX`: a fourth VFD contact, port 2 pin 6 | a fault input back to Mach3 would have been the other use, but no port input pin is free |

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
pins 10, 11, 12, 13 and 15 — X, Y, Z and A home, and C home on 15; E-stop on
port 2 pin 15. All six arrive on one 6-way terminal,
one wire per channel, marked EMG C A Z Y X. There is no third screw per channel:
a **PNP** sensor takes its +24 V and 0 V from the 24 V supply terminal, exactly
as on the board in service.

Each channel is 4k7 (1206, for the 0.11 W) into the LED, a 1N4148 back across
the LED (`D20`-`D25`), and on the PC side a 10k pull-up to +5V and 10 nF to
ground. The two optocouplers lie on their side under the terminal, LEDs up,
and their units are numbered in reverse in the schematic so that the channels
run left to right in the terminal's own order, 5.08 mm apart under screws
5.0 mm apart. Each channel's four passives sit in a column over its own pins
(`INPUT_ROW` in `build_pcb.py`).

**Spindle.** Port 2 pins 7, 8 and 9 carry spindle PWM, M3 and M4 to the VFD
port `J5`, through a Schmitt buffer and optocouplers; see *Spindle* below.

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
all the anchored parts land within 0.4 mm of it, apart from the few moved on
purpose, each listed with its reason in `NUDGE` in `build_pcb.py` - the 24 V
diode, for one, sat on its terminal's legend.

- **Left edge** — LPT port 1 (top), LPT port 2 (bottom), 62.8 mm apart.
- **Top edge** — the VFD port (5-way, new in A1) in the top-left corner,
  which is empty on the board in service; then EMG & HOME (6-way), handwheel
  (4-way) and 24 V in, on the drawing's positions. The drawing's 5 V terminal
  position between the last two is left empty: 5 V is made on the board.
- **Right edge** — the six axis terminals at a 16.1 mm pitch, and RS232 below
  them, set apart.
- **Bottom edge** — six relays at a 16.2 mm pitch, each directly above its own
  NO/COM/NC terminal, with its flyback diode and driver in the rows above.
- **Interior** — the input channels in a row under EMG & HOME; the VFD
  port's isolated block under its terminal; the whole power supply, buck
  included, in the top-right corner under 24 V in; the spindle buffer `U16`
  beside the lower D-sub; the two 74HC245 beside the axis
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
(sheet coverage, optocoupler orientation, LED polarity, MOSFET orientation,
grid), the coverage checks in `check_coverage.py`, the bypass-capacitor
distances, the VFD isolation barrier, and DRC with schematic parity. ERC, the
structural checks, the barrier and parity pass with zero findings, and DRC
finds nothing but silkscreen.

Beyond that, for A1: the firmware's own tests and its pin map against the
netlist pass, and the shipped `build/mach3simple.elf` was run in simavr at
16 MHz - it greets with `R:abcdef M:jog`, every command moves exactly its own
pin, garbage is ignored, and the watchdog stays quiet. None of that says the
analog stages are right; the buck and the spindle output are checked on the
bench, `COMMISSIONING.md` steps 1 and 6.

`check_coverage.py` exists because the missing pull-downs passed every one of
the others. It looks for nets that reach a chip input with nothing to drive or
hold them - which ERC cannot see, since a connector pin is passive and satisfies
an input - and it counts the parts on the drawing against the parts here. Of
the nets it finds, `RS232_RX` is held by the MAX3232's own internal pull-down,
and `SP_FWD`, `SP_REV` and `SP_DCM` by the VFD at the far end; the check knows
both. `check_placement.py` measures the placement against the drawing.

That is worth less than it sounds. A clean ERC proves nothing about a sheet
KiCad never managed to read — on the sister project an unescaped quote made a
whole sheet unparseable and 64 parts vanished from the netlist while ERC
reported zero violations. That is why `check_design.py` counts parts per sheet.
DRC says the geometry is legal, not that it is good.

**Nothing here has been built or powered.**

## State of the routing

**Fully routed.** Every connection, ground included, with 0 unconnected
items, 0 clearance violations and 0 differences from the schematic. What DRC
still reports is silkscreen warnings only: terminal bodies that overhang the
board edge by design, and the outlines of neighbouring relays, which sit on
the drawing's 16.2 mm pitch and so share an edge.

The route comes from Freerouting 2.4.1, run headless: `tools/autoroute.py`
exports a Specctra DSN through KiCad's own `pcbnew` module, Freerouting routes
it, and the session is imported back. 1886 track segments - 1373 on the front,
513 on the back - and 345 vias, 140 of them ground.

It takes two passes, because of the VFD port's isolation barrier. The first
routes the board with the VFD side fenced off: its pads lose their nets on
the exported copy, so the router sees them as obstacles, and a keepout over
`SP_ZONE` keeps every board-side track and via outside. The second locks all
of that - a locked track goes into the DSN as fixed wiring - and routes the
VFD side alone. Freerouting's session then holds only what it routed itself,
and importing a session replaces every track on the board, so `vfd-import`
copies the first pass out, imports, keeps only the VFD side's wires, and puts
the first pass back. After the review round the first pass left one
board-side connection open, `C_DIR_IN` (port 1 pin 16 to `U2`), and a
finishing Freerouting pass over a board with everything locked made no
headway - it reads locked ends a hair off their pads and chases them. That
one connection was drawn by `tools/route_one.py`, a grid A* over both layers
that keeps clear of every other net and of the VFD side: 137 mm, six vias,
DRC-clean. Two more things learned there, recorded in the code: a
zone or track taken off a board in KiCad's Python and let go crashes the next
call into the board, and so does a point read off a track that has since been
deleted.

Four things were learned getting to the A0 route, and each is recorded in the code:

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
| Power | 0.6 mm | 0.2 mm | +5V, V24, GND, VIN*, BUCK_SW |
| Contact | 0.8 mm | 0.3 mm | relay contacts, K?_* - low voltage only |

To re-route after a placement change:

    python tools/build_pcb.py --force
    D:/KiCad/bin/python.exe tools/autoroute.py export
    java -jar freerouting.jar --gui.enabled=false -de review/route/MACH3SIMPLE.dsn -do review/route/MACH3SIMPLE.ses -mp 100
    D:/KiCad/bin/python.exe tools/autoroute.py import
    D:/KiCad/bin/python.exe tools/autoroute.py vfd-export
    java -jar freerouting.jar --gui.enabled=false -de review/route/MACH3SIMPLE_vfd.dsn -do review/route/MACH3SIMPLE_vfd.ses -mp 100
    D:/KiCad/bin/python.exe tools/autoroute.py vfd-import
    D:/KiCad/bin/python.exe tools/autoroute.py stitch
    D:/KiCad/bin/python.exe tools/autoroute.py barrier
    # only if DRC then reports a board-side connection still open:
    D:/KiCad/bin/python.exe tools/route_one.py NET FROM_REF

Java 25 and Freerouting live in `D:\software`. `tools/route.py`, the earlier
router, is superseded and no longer used for this board.

## Power

One supply comes in: 24 V on `J4`, through `F2` (1 A slow), the series
Schottky `D2` for reverse polarity, and the TVS `D3`, to V24 with `C2` as
bulk. V24 feeds the relay coils, the sensor loops, the VFD port's isolated
module and the 5 V buck.

+5V comes from `U4`, an LM2596S-5.0: `C4` (47 µF 50 V) and `C5` (1 µF) at
its input, `D4` (SS34) as catch diode, `L1` 47 µH shielded, `C1` 220 µF
low-ESR at the output, and the -5.0 part's own feedback on +5V. A buck, not a
7805: the 5 V load is up to about 0.4 A with stepper drivers on the axis
outputs and a handwheel on `J30`, and a linear regulator would drop 19 V of it
- 7.6 W. At 150 kHz the buck loses about 0.4 W.

The whole supply is in the top-right corner, beside `J4`, where A0's 5 V
terminal and its parts used to be. It was first placed in the middle of the
board, next to what uses +5V; the owner asked for it by its input, and that
is the better place - the buck's switch node, the one net on the board that
swings 24 V at 150 kHz, is then as far from the MCU's crystal and the
parallel-port lines as the board allows. `U4`'s pins face left: `C5` sits
straight above VIN, `D4` beside the SW pin with its cathode down, `L1` below.
The switch node is drawn by `build_pcb.py` itself (`SW_ROUTE`), not left to
the router: 14 mm on the top layer, no vias, locked, and carried through
every route import by `autoroute.py`.

## Spindle

Mach3 makes spindle speed as PWM on a port pin; a VFD wants 0-10 V on its
analog input and contacts on FWD / REV. `J5` provides both, isolated from
this board:

| `J5` | VFD terminal | |
|---|---|---|
| `AVI` | AVI / VI / AI1 | 0-10 V, 100 Ω out of an LM358 |
| `ACM` | ACM / GND (analog) | the isolated side's ground |
| `FWD` | FWD | phototransistor to `DCM` |
| `REV` | REV | phototransistor to `DCM` |
| `DCM` | DCM / COM (digital) | |

**Why isolated, when nothing else here is.** The VFD is the noisiest thing in
the cabinet, and on many inexpensive ones the control terminals are not
isolated from the drive's own electronics. Tying `ACM` to this board's ground
would tie it to the PC's ground through the parallel cable, which is the one
connection that most often ends with a dead parallel port.

**Board side.** Port 2 pins 7 (PWM), 8 (M3/FWD) and 9 (M4/REV), each pulled
down by 10k (`R90`-`R92`) so the PC off or the cable out means no speed and no
direction, into a 74HC14 (`U16`) beside the lower D-sub. The 74HC14 sinks
the LED current of `U12`, a third PC847, through 330 Ω from +5V
(`R93`-`R95`): an LED lights only when its port pin is high.

**VFD side.** Powered by `U13`, a 1 W 24 V to 12 V isolated module (Mornsun
B2412S-1WR3, SIP-4), so the output does not depend on the VFD's own +10 V or
what it can supply. `U14`, a 78L05, makes a 5 V reference from it. The PWM
channel's phototransistor switches that reference onto a chopper node that
`R96` (2k2) pulls to `ACM` when it is off; two RC poles (100k / 470 nF, twice)
average it to 0-4.9 V, and `U15`, an LM358, multiplies by 1 + (8k2 + `RV1`) /
10k = 1.82 to 2.32. Trim `RV1` for 10.0 V at 100 % PWM; the LM358 on 12 V
reaches about 10.5 V. `R96` is small beside the filter's 100k, so the node is
driven nearly as stiffly low as high and the average stays linear in duty.

The filter is for a PWM base frequency of about 100 Hz: ripple at the output
is some 10 mV and the output settles in about a third of a second, which a
VFD's own ramp hides. Mach3's PWMBase Freq should be set to 100.
`COMMISSIONING.md` has the full Mach3 and VFD settings.

FWD and REV are the other two channels' phototransistors, collector on the
terminal and emitter on `DCM`: a contact to the VFD's digital common, which is
what a VFD in its usual NPN (sink) input mode wants. PC847: 35 V, 50 mA.

**The barrier on the board.** The VFD side - `J5`, `U12`'s phototransistor
row, `U13`'s output pins, `U14`, `U15` and the filter - sits in the top-left
corner above the upper D-sub, in its own `SP_ACM` pour (`SP_ZONE` in
`build_pcb.py`). Nothing of the board may enter it, and a clearance check
cannot see that: the first routing put a home-switch line and a handwheel line
straight through, 0.22 mm from the VFD's copper, and DRC passed. So the board
is routed in two passes (see *State of the routing*) and `autoroute.py
barrier` - run by `validate.sh`, and by `fab.sh`, which refuses to write
Gerbers without it - fails if any board-side track or via is inside the
outline or any VFD-side one outside. The closest board copper to the VFD's is
now 1.04 mm, and that is `U13`'s own pins 2 and 3.

## Terminal legends

The terminals along the top edge are turned 180 degrees so the wire enters
from the edge, and that puts pin 1 at the **right-hand** end. A0 wired pin 1
to the first word of each legend, printed at the left, so all three top
legends were reversed: `24V IN` read `+24` over 0 V (the series diode would
have saved the board, which would simply not have worked), `HANDWHEEL` read
`+5` over the B input - wired by its legend, an open-collector encoder would
have been driven straight into +5V - and `EMG & HOME` read `EMG` over X home.

A1 assigns the signals left to right, as printed and as on the board in
service (`TOP_PIN` in `build_project.py`), and prints one word under each
screw rather than one string across the block. `build_pcb.py` prints the
signal under every word (`legend : J4 +24=VIN24`) so it can be read against
the schematic.

## Relay drive

Each relay is switched by a 2N7002 MOSFET straight off an MCU pin: 1 kΩ in the
gate to slow the edges, 10 kΩ gate to ground so every relay stays off while the
MCU is in reset or unprogrammed, and a 1N4148 across each coil.

**A0 had every one of them backwards.** KiCad's `Q_NMOS_GSD` numbers its pins
gate, source, drain - the 2N7002's own SOT-23 order - and A0 put the relay coil
on pin 2 and ground on pin 3, which is the source on the coil and the drain on
ground. An N-channel MOSFET's body diode runs from source to drain, so the
coil current flowed through it whatever the gate did: every relay on from the
moment 24 V arrived, spindle and coolant included. ERC, DRC and parity were
all clean. A1 swaps the two pins, and `check_design.py` now checks every
N-channel MOSFET for its source on ground, by pin function, and fails the run
if one is not.

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
to the pour solid, and a through-hole pad on GND or on the VFD side's
`SP_ACM` needs only one thermal spoke, since its own track is what connects
it.

**KiCad ignores the whole file, without a word, if one rule in it will not
parse.** The spoke rule was first written `(min 1)` - the form for distances,
not counts - and DRC carried on as if the file were empty: the solid-SMD rule
went too, and surface-mount pads started failing for want of spokes they were
never meant to have. `validate.sh` now checks for exactly that symptom and says
so.

## Fabrication

    KICAD_CLI='/d/KiCad/bin/kicad-cli.exe' sh tools/fab.sh

It refuses to write anything if DRC finds a single error, an unrouted
connection or a difference from the schematic, or if board-side copper
crosses into the VFD side. Otherwise `fab/` gets:

- `MACH3SIMPLE-gerbers.zip` - **this is what goes to the board house.** Eight
  Gerber layers (copper, mask, paste and silkscreen front and back, outline)
  and the plated and unplated drill files. 2 layers, 1.6 mm FR4, 1 oz copper,
  150.5 x 137.9 mm.
- `MACH3SIMPLE-pos.csv` - part positions, for machine assembly.
- `MACH3SIMPLE-BOM.md` / `.csv` - the bill of materials.
- `MACH3SIMPLE-copper.pdf`, `-assembly.pdf` - to check against.

The drill files were checked against the board: 513 plated holes, which is 345
vias and 168 pad holes exactly, and 4 unplated - the mounting holes. The drill
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
