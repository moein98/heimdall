/*
 * MCU pin map for MACH3-SIMPLE.
 *
 * This file and the board must agree, and nothing in the compiler can tell
 * whether they do. firmware/check_pins.py reads these lines and the board's
 * netlist and fails if a single one differs - run it after any change to
 * either. The schematic pins are fixed in tools/build_project.py (MCU_PINS).
 *
 * Every output here is active high.
 */
#ifndef PINS_H
#define PINS_H

/* name       port  bit    net on the board */
#define PIN_REL_A    D, 3  /* REL_A    relay A driver gate */
#define PIN_REL_B    D, 4  /* REL_B    relay B */
#define PIN_REL_C    D, 5  /* REL_C    relay C */
#define PIN_REL_D    D, 6  /* REL_D    relay D */
#define PIN_REL_E    D, 7  /* REL_E    relay E */
#define PIN_REL_F    B, 0  /* REL_F    relay F */
#define PIN_MPG_SEL  B, 1  /* MPG_SEL  high: handwheel to the THC pins */
#define PIN_LED      B, 2  /* MCU_LED  D30, "SERIAL" */

#endif
