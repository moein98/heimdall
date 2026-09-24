/*
 * MACH3-SIMPLE firmware: six relays and the handwheel switch, driven by
 * single characters Mach3 sends with SendSerial. See commands.h for the
 * command set and pins.h for where everything is.
 *
 * ATmega328P on the board's 16 MHz crystal, Y1. The chip leaves the factory
 * on its internal RC oscillator, divided by 8; build.sh sets the fuses for
 * the crystal when it programs the chip (low FF, high D9, extended FD).
 * setup() also takes the clock divider off in software, so a chip whose
 * CKDIV8 fuse was left set still runs at full speed rather than at an eighth
 * of it with every baud rate wrong.
 *
 * Three things here exist for the machine's sake rather than the code's:
 *
 *  - Reception is interrupt-driven into a ring buffer. Mach3 can send several
 *    commands at once ("abcdef" to drop every relay), and the UART holds only
 *    two bytes; polled, anything that arrived while a reply was going out
 *    would be lost, and a lost 'a' is a relay left on.
 *  - A byte with a framing, overrun or parity error is thrown away, not
 *    acted on. Noise on a long RS232 run, or a PC port set to the wrong
 *    speed, is the difference between ignoring a garbled byte and switching
 *    whichever relay it happens to look like.
 *  - A watchdog. If the program ever stops, the chip resets, every pin goes
 *    back to an input, and the pull-downs on the board turn every relay off
 *    and put the handwheel on jog. Off is the safe state for a spindle or a
 *    coolant pump.
 */
#include <avr/interrupt.h>
#include <avr/io.h>
#include <avr/power.h>
#include <avr/wdt.h>
#include <util/delay.h>

#include "commands.h"
#include "pins.h"

#ifndef F_CPU
#define F_CPU 16000000UL
#endif
#ifndef BAUD
#define BAUD 9600
#endif
#include <util/setbaud.h>   /* UBRR_VALUE and USE_2X, checked at build time */

/* A pin in pins.h is "D, 3". Every macro that takes one is variadic: the
 * argument is expanded to two before it reaches the inner macro, and a
 * one-argument macro would then be handed two. */
#define WRITE(...)       WRITE_(__VA_ARGS__)
#define WRITE_(p, b, v)                                      \
    do {                                                     \
        if (v)                                               \
            PORT##p |= (uint8_t)_BV(b);                      \
        else                                                 \
            PORT##p &= (uint8_t)~_BV(b);                     \
    } while (0)
#define MAKE_OUTPUT(...) MAKE_OUTPUT_(__VA_ARGS__)
#define MAKE_OUTPUT_(p, b)                                   \
    do {                                                     \
        PORT##p &= (uint8_t)~_BV(b);  /* low before driven */ \
        DDR##p |= (uint8_t)_BV(b);                           \
    } while (0)

#define LED_BLINK_MS 60

/* After a watchdog reset the watchdog is still running, at its shortest
 * timeout, and would reset the chip again before main() got to it. This runs
 * before main, clears it, and reads why the chip reset. */
#ifndef HOST_TEST
uint8_t reset_cause __attribute__((section(".noinit")));
void early_init(void) __attribute__((naked, used, section(".init3")));
void early_init(void)
{
    reset_cause = MCUSR;
    MCUSR = 0;
    wdt_disable();
}
#endif

/* Received bytes, from the interrupt to the main loop. 32 is several full
 * bursts of commands; head and tail are single bytes, so each is read and
 * written atomically. */
#define RX_SIZE 32
static volatile uint8_t rx_buf[RX_SIZE];
static volatile uint8_t rx_head, rx_tail;

ISR(USART_RX_vect)
{
    /* The status has to be read before the data - reading UDR0 moves the
     * next byte's flags into UCSR0A. */
    uint8_t status = UCSR0A;
    uint8_t c = UDR0;
    uint8_t next = (uint8_t)((rx_head + 1) % RX_SIZE);

    if (status & (_BV(FE0) | _BV(DOR0) | _BV(UPE0)))
        return;                         /* garbled: drop it */
    if (next == rx_tail)
        return;                         /* full: drop the newest */
    rx_buf[rx_head] = c;
    rx_head = next;
}

static int rx_get(void)
{
    uint8_t c;
    if (rx_tail == rx_head)
        return -1;
    c = rx_buf[rx_tail];
    rx_tail = (uint8_t)((rx_tail + 1) % RX_SIZE);
    return c;
}

static void uart_init(void)
{
    UBRR0H = UBRRH_VALUE;
    UBRR0L = UBRRL_VALUE;
#if USE_2X
    UCSR0A |= _BV(U2X0);
#else
    UCSR0A &= (uint8_t)~_BV(U2X0);
#endif
    UCSR0C = _BV(UCSZ01) | _BV(UCSZ00);               /* 8N1 */
    UCSR0B = _BV(RXEN0) | _BV(TXEN0) | _BV(RXCIE0);
}

/* The one write to UDR0. A macro so firmware/test_main.c can catch what the
 * board sends back without a real UART. */
#ifndef UART_TX
#define UART_TX(c) (UDR0 = (c))
#endif

static void uart_put(uint8_t c)
{
    while (!(UCSR0A & _BV(UDRE0)))
        wdt_reset();
    UART_TX(c);
}

static void report(const board_state *s)
{
    char line[STATUS_LEN];
    uint8_t i, n = board_status(s, line);
    for (i = 0; i < n; i++)
        uart_put((uint8_t)line[i]);
}

static void drive(const board_state *s)
{
    WRITE(PIN_REL_A, s->relays & 0x01);
    WRITE(PIN_REL_B, s->relays & 0x02);
    WRITE(PIN_REL_C, s->relays & 0x04);
    WRITE(PIN_REL_D, s->relays & 0x08);
    WRITE(PIN_REL_E, s->relays & 0x10);
    WRITE(PIN_REL_F, s->relays & 0x20);
    WRITE(PIN_MPG_SEL, s->thc);
}

/* Everything main() does before its loop. Separate so the host test can run
 * it and then look at what it left in the registers. */
static void setup(board_state *state)
{
    clock_prescale_set(clock_div_1);    /* in case CKDIV8 is still set */

    /* Unused pins get their pull-ups rather than floating. PC6 is RESET. */
    PORTC |= 0x3F;
    PORTD |= _BV(PD2);

    board_init(state);
    MAKE_OUTPUT(PIN_REL_A);
    MAKE_OUTPUT(PIN_REL_B);
    MAKE_OUTPUT(PIN_REL_C);
    MAKE_OUTPUT(PIN_REL_D);
    MAKE_OUTPUT(PIN_REL_E);
    MAKE_OUTPUT(PIN_REL_F);
    MAKE_OUTPUT(PIN_MPG_SEL);
    MAKE_OUTPUT(PIN_LED);
    drive(state);

    uart_init();
    wdt_enable(WDTO_1S);
    sei();

    WRITE(PIN_LED, 1);                  /* on: running */
    report(state);                      /* say hello, and what state it is in */
}

/* One pass of the main loop, a millisecond's worth. */
static void poll(board_state *state, uint8_t *led_off)
{
    int c;

    wdt_reset();
    while ((c = rx_get()) >= 0) {
        uint8_t r = board_apply(state, (uint8_t)c);
        if (r == CMD_IGNORED)
            continue;
        if (r == CMD_CHANGED)
            drive(state);
        report(state);
        WRITE(PIN_LED, 0);              /* blink off: a command arrived */
        *led_off = LED_BLINK_MS;
    }
    if (*led_off && --*led_off == 0)
        WRITE(PIN_LED, 1);
}

#ifndef HOST_TEST
int main(void)
{
    board_state state;
    uint8_t led_off = 0;

    setup(&state);
    for (;;) {
        poll(&state, &led_off);
        _delay_ms(1);
    }
}
#endif
