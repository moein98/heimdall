# MACH3-SIMPLE - order list

Generated from the netlist by `tools/bom.py`. Quantities are what the
board needs; buy spares of the 0603 passives and the optocouplers.

## Semiconductors - the ones to get right

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 2 | 74HC245 | SOIC-20W_7.5x12.8mm_P1.27mm | U1, U2 |  |
| 2 | PC847 | SOIC-16 | U10, U11 | 4-channel opto, DIP-16 outline in SOIC. PC844 is the same part |
| 1 | 74HC4053 | SOIC-16 | U3 |  |
| 1 | ATmega328P-AU | TQFP-32 | U21 | TQFP-32. Runs on the 16 MHz crystal Y1 |
| 1 | MAX3232 | SOIC-16 | U20 | 3 V version works on 5 V; MAX232 does NOT - wrong capacitor values |

## Transistors, diodes and LEDs

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 9 | LED, indicator | 0603 SMD | D10, D11, D30, D50, D51, D52, D53, D54, D55 |  |
| 6 | 1N4148 | SOD-123 SMD | D40, D41, D42, D43, D44, D45 | plain small-signal, any maker |
| 6 | 2N7002 | SOT-23 | Q1, Q2, Q3, Q4, Q5, Q6 |  |
| 2 | SS34 | SMA SMD | D1, D2 | 40 V 3 A Schottky, both places |
| 1 | SMAJ26A | SMA SMD | D3 | TVS on the 24 V input. Clamps at 42 V, under the 50 V rating of C2 |

## Relays

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 6 | JQC-3FF-024-1Z | JQC-3FF relay, THT | K1, K2, K3, K4, K5, K6 | 24 V coil, SPDT. Songle or Hongfa |

## Connectors

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 13 | connector | Phoenix MKDS 1,5 5.0 mm, 3 way | J10, J11, J12, J13, J14, J15 ... J50 |  |
| 2 | connector | Phoenix MKDS 1,5 5.0 mm, 2 way | J3, J4 |  |
| 2 | connector | DB25 socket, right angle, PCB | J1, J2 |  |
| 1 | connector | Phoenix MKDS 1,5 5.0 mm, 6 way | J20 |  |
| 1 | connector | Phoenix MKDS 1,5 5.0 mm, 4 way | J30 |  |
| 1 | connector | 2x5 shrouded box header, 2.54 mm | J60 |  |

## Resistors

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 18 | 10k | 0603 SMD | R2, R30, R31, R32, R33, R34 ... R75 |  |
| 8 | 1k | 0603 SMD | R1, R51, R60, R61, R62, R63, R64, R65 |  |
| 8 | 4k7 | 0603 SMD | R42, R43, R80, R81, R82, R83, R84, R85 |  |
| 6 | 4k7 | 1206 SMD | R10, R11, R12, R13, R14, R15 |  |
| 3 | 4x10k | 4 x 0603 array, convex (1206 size) | RN1, RN2, RN3 |  |
| 2 | 330R | 0603 SMD | R40, R41 |  |
| 1 | 10k MPG_SEL | 0603 SMD | R52 |  |
| 1 | 10k spare | 0603 SMD | R5 |  |

## Capacitors

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 10 | 100nF | 0603 SMD | C20, C21, C22, C23, C30, C31, C32, C40, C41, C42 |  |
| 6 | 10nF | 0603 SMD | C10, C11, C12, C13, C14, C15 |  |
| 2 | 22pF | 0603 SMD | C33, C34 |  |
| 1 | 100uF 16V | electrolytic 6.3x7.7 SMD | C1 |  |
| 1 | 100uF 50V | electrolytic 6.3x7.7 SMD | C2 |  |
| 1 | 1nF 2kV | disc ceramic, THT | C3 |  |

## Inductor, fuse, crystal

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 2 | 1A slow | 1206 SMD | F1, F2 |  |
| 1 | 16MHz | 3.2x2.5 mm SMD, 4 pad | Y1 | load capacitance CL 18-20 pF, to suit the 22 pF capacitors |

## Mechanical

| Qty | Part | Package | Refs | Note |
|---:|---|---|---|---|
| 4 | M3 | M3 hole (no part) | H1, H2, H3, H4 |  |

## Not fitted - leave the pads empty

- R3 (0R link - DO NOT FIT)

**128 parts to fit** across 33 distinct lines.

Worth buying spare: the 0603 resistors and capacitors (they are pennies and
they get lost), one or two extra PC847, and one spare ATmega328P.
