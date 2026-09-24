/*
 * What the board does with each byte Mach3 sends it. No hardware in here, so
 * the whole of it can be tested on a PC: see test_commands.c.
 *
 *   'A'..'F'  relay A..F on          'a'..'f'  relay A..F off
 *   'T'       handwheel to THC       't'       handwheel to jog
 *   '?'       report the state
 *
 * Anything else is ignored. That matters more than it looks: a byte that
 * picks up noise on the way, or is sent at the wrong speed, arrives as some
 * other byte. Fourteen of 256 values mean something, so a
 * corrupted byte is far more likely to be dropped than to switch the wrong
 * relay - and the UART's framing-error flag, checked in main.c, drops most of
 * the rest before they get here.
 */
#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>

#define RELAY_COUNT 6

typedef struct {
    uint8_t relays;   /* bit 0 = relay A ... bit 5 = relay F */
    uint8_t thc;      /* 1: handwheel on the THC pins, 0: on the jog pins */
} board_state;

/* What a byte did. */
enum {
    CMD_IGNORED = 0,  /* not a command */
    CMD_CHANGED = 1,  /* a command, and the outputs must be updated */
    CMD_REPORT  = 2,  /* '?': send the state back */
};

/* The state the board powers up in: every relay off, handwheel on jog.
 * It is also what the hardware holds while the MCU is in reset - the relay
 * gates and the select line each have a pull-down - so there is no step at
 * the moment the firmware takes over. */
void board_init(board_state *s);

/* Apply one received byte. */
uint8_t board_apply(board_state *s, uint8_t c);

/* "R:AbcdEf M:jog\r\n" - a capital for a relay that is on. buf must hold at
 * least STATUS_LEN bytes; returns the number written. */
#define STATUS_LEN 20
uint8_t board_status(const board_state *s, char *buf);

#endif
