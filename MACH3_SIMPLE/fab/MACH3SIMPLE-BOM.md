# MACH3-SIMPLE - order list

Generated from the netlist by `tools/bom.py`. Quantities are what the
board needs; buy spares of the 0603 passives and the optocouplers.

## Semiconductors - the ones to get right

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 3 | PC847 | DIP-16, SMD lead form (2.54 mm) | U10, U11, U12 | 4-channel opto, the SMD lead form (Sharp PC847XI, or LTV-847S) - there is no SOIC version |
| 2 | 74AC245 | SOIC-20W_7.5x12.8mm_P1.27mm | U1, U2 | AC, not HC: 24 mA per output for opto-input stepper drivers. 74HC245 fits the same pads but is overloaded by more than about 6 mA per output |
| 1 | 74HC14 | SOIC-14 | U16 | Schmitt inverter. Plain 74HC04 will not do |
| 1 | 74HC4053 | SOIC-16 | U3 |  |
| 1 | 78L05 | SOT-89-3 | U14 | SOT-89. Pin order OUT, GND, IN - not the TO-92 order |
| 1 | ATmega328P-AU | TQFP-32 | U21 | TQFP-32. Runs on the 16 MHz crystal Y1 |
| 1 | B2412S-1WR3 | SIP-4 isolated module | U13 | Mornsun 1 W isolated 24 V to 12 V, SIP-4. Pins 1 GND, 2 Vin, 3 0V, 4 +Vo |
| 1 | LM2596S-5 | TO-263-5 (D2PAK) | U4 | fixed 5 V version, not ADJ |
| 1 | LM358 | SOIC-8 | U15 | LM358 or LM2904, SOIC-8 |
| 1 | MAX3232 | SOIC-16 | U20 | 3 V version works on 5 V; MAX232 does NOT - wrong capacitor values |

## Transistors, diodes and LEDs

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 12 | 1N4148 | SOD-123 SMD | D20, D21, D22, D23, D24, D25, D40, D41, D42, D43, D44, D45 | plain small-signal, any maker |
| 9 | LED, indicator | 0603 SMD | D10, D11, D30, D50, D51, D52, D53, D54, D55 |  |
| 6 | 2N7002 | SOT-23 | Q1, Q2, Q3, Q4, Q5, Q6 |  |
| 2 | SS34 | SMA SMD | D2, D4 | 40 V 3 A Schottky, both places |
| 1 | SMAJ26A | SMA SMD | D3 | TVS on the 24 V input. Clamps at 42 V, under the 50 V rating of C2 |

## Relays

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 6 | JQC-3FF-024-1Z | JQC-3FF relay, THT | K1, K2, K3, K4, K5, K6 | 24 V coil, SPDT. Songle or Hongfa |

## Connectors

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 13 | connector | Phoenix MKDS 1,5 5.0 mm, 3 way | J10, J11, J12, J13, J14, J15 ... J50 |  |
| 2 | connector | Phoenix MKDS 1,5 5.0 mm, 4 way | J4, J30 |  |
| 2 | connector | DB25 socket, right angle, PCB | J1, J2 |  |
| 2 | connector | Phoenix MKDS 1,5 5.0 mm, 6 way | J5, J20 |  |
| 1 | connector | 2x5 shrouded box header, 2.54 mm | J60 |  |

## Resistors

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 31 | 10k | 0603 SMD | R2, R5, R30, R31, R32, R33 ... R102 |  |
| 8 | 1k | 0603 SMD | R1, R51, R60, R61, R62, R63, R64, R65 |  |
| 6 | 330R | 0603 SMD | R40, R41, R93, R94, R95, R103 |  |
| 6 | 4k7 | 1206 SMD | R10, R11, R12, R13, R14, R15 |  |
| 3 | 4x10k | 4 x 0603 array, convex (1206 size) | RN1, RN2, RN3 |  |
| 2 | 100k | 0603 SMD | R97, R98 |  |
| 2 | 4k7 | 0603 SMD | R42, R43 |  |
| 1 | 100R | 0603 SMD | R101 |  |
| 1 | 2k2 | 0603 SMD | R96 |  |
| 1 | 8k2 | 0603 SMD | R100 |  |

## Trimmers

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 1 | 5k | Bourns 3296W trimmer, THT | RV1 | multi-turn trimmer, sets 10.0 V at full speed |

## Capacitors

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 12 | 100nF | 0603 SMD | C20, C21, C22, C23, C30, C31, C32, C40, C41, C42, C60, C66 |  |
| 8 | 10nF | 0603 SMD | C10, C11, C12, C13, C14, C15, C35, C67 |  |
| 2 | 1uF 50V X7R | 1206 SMD | C5, C61 |  |
| 2 | 22pF | 0603 SMD | C33, C34 |  |
| 2 | 470nF | 0603 SMD | C64, C65 |  |
| 2 | 47uF 50V | electrolytic 6.3x7.7 SMD | C2, C4 | low-ESR electrolytic, 50 V - the largest a 6.3 x 7.7 can holds |
| 1 | 10uF 25V X7R | 1206 SMD | C62 |  |
| 1 | 1nF 2kV | disc ceramic, THT | C3 |  |
| 1 | 1uF | 0603 SMD | C63 |  |
| 1 | 220uF 16V | electrolytic 6.3x7.7 SMD | C1 | low-ESR electrolytic - the buck output capacitor |

## Inductor, fuse, crystal

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 1 | 16MHz | 3.2x2.5 mm SMD, 4 pad | Y1 | load capacitance CL 18-20 pF, to suit the 22 pF capacitors |
| 1 | 1A slow | 1206 SMD | F2 |  |
| 1 | 200mA hold PTC | 1206 SMD | F3 | resettable fuse, hold 0.2 A, 1206 (Bourns MF-MSMF020 or similar) |
| 1 | 47uH | 12x12x8 mm shielded SMD | L1 | shielded power inductor, saturation current 1.5 A or more (SRR1260-470M, or the 47 uH from an LM2596 module) |

## Mechanical

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 4 | M3 | M3 hole (no part) | H1, H2, H3, H4 |  |

## Not fitted - leave the pads empty

- R3 (0R link - DO NOT FIT)

**167 parts to fit** across 46 distinct lines.

Worth buying spare: the 0603 resistors and capacitors (they are pennies and
they get lost), one or two extra PC847, and one spare ATmega328P.
