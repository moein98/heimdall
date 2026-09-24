/*
 * Host test for main.c: the real firmware source, compiled on the PC against
 * stand-in AVR headers (hoststub/) in which every register is a variable.
 *
 * test_commands.c checks what a byte means. This checks what the firmware
 * does to the chip because of it - which port bit a command moves, what the
 * UART is configured to, that a garbled byte is dropped by the interrupt
 * before it reaches the command logic, that a burst of commands all land.
 * The pin macros are the likeliest place for a bug that compiles cleanly,
 * and this is the only thing here that exercises them.
 *
 * What it cannot check is timing: the real clock, the real baud rate, the
 * real watchdog. Those need a chip.
 */
#include <stdio.h>
#include <string.h>

#define HOST_TEST 1
static char tx_log[4096];
static int tx_len;
#define UART_TX(c) (tx_len < (int)sizeof tx_log - 1 \
                    ? (void)(tx_log[tx_len++] = (char)(c), tx_log[tx_len] = 0) : (void)0)

#include "main.c"

static int failures;
#define CHECK(cond, ...)                                  \
    do {                                                  \
        if (!(cond)) {                                    \
            failures++;                                   \
            printf("FAIL line %d: ", __LINE__);           \
            printf(__VA_ARGS__);                          \
            printf("\n");                                 \
        }                                                 \
    } while (0)

/* A byte arriving at the UART, with whatever error flags it came with. */
static void receive(uint8_t c, uint8_t errors)
{
    UCSR0A = (uint8_t)(_BV(UDRE0) | _BV(RXC0) | errors);
    UDR0 = c;
    USART_RX_vect_handler();
    UCSR0A = _BV(UDRE0);
}

static void clear_tx(void)
{
    tx_len = 0;
    tx_log[0] = 0;
}

static int reports(void)
{
    int i, n = 0;
    tx_log[tx_len] = 0;
    for (i = 0; i < tx_len; i++)
        n += tx_log[i] == '\n';
    return n;
}

/* Where each relay lives, in the order A..F. */
static volatile uint8_t *const relay_port[6] = {&PORTD, &PORTD, &PORTD, &PORTD, &PORTD, &PORTB};
static const uint8_t relay_bit[6] = {PD3, PD4, PD5, PD6, PD7, PB0};

int main(void)
{
    board_state s;
    uint8_t led_off = 0, before_d, before_b;
    int i, n;

    /* ---- setup ------------------------------------------------------- */
    UCSR0A = _BV(UDRE0);
    setup(&s);
    CHECK(clock_divider == 1, "clock divider %d, want 1 (CKDIV8 not undone)", clock_divider);
    CHECK(DDRD == 0xF8, "DDRD %02x, want f8 (PD3-PD7 out)", DDRD);
    CHECK(DDRB == 0x07, "DDRB %02x, want 07 (PB0-PB2 out, ISP pins left in)", DDRB);
    CHECK(PORTD == _BV(PD2), "PORTD %02x: relays must start off, PD2 pulled up", PORTD);
    CHECK(PORTB == _BV(PB2), "PORTB %02x: relay F and select off, LED on", PORTB);
    CHECK(PORTC == 0x3F, "PORTC %02x: unused pins pulled up", PORTC);
    /* Worked out here, not taken from setbaud.h - that is what is under test. */
    n = (int)((F_CPU + 8UL * BAUD) / (16UL * BAUD) - 1);
    CHECK(((UBRR0H << 8) | UBRR0L) == n, "UBRR %d, want %d for %d baud at %lu Hz",
          (UBRR0H << 8) | UBRR0L, n, BAUD, (unsigned long)F_CPU);
    CHECK(!(UCSR0A & _BV(U2X0)), "U2X set: half the samples per bit, less margin");
    CHECK(UCSR0B == (_BV(RXEN0) | _BV(TXEN0) | _BV(RXCIE0)), "UCSR0B %02x", UCSR0B);
    CHECK(UCSR0C == (_BV(UCSZ01) | _BV(UCSZ00)), "UCSR0C %02x, want 8N1", UCSR0C);
    CHECK(wdt_on, "watchdog not enabled");
    CHECK(interrupts_on, "interrupts not enabled - nothing would be received");
    CHECK(!strcmp(tx_log, "R:abcdef M:jog\r\n"), "hello '%s'", tx_log);

    /* ---- each relay, on and off, alone ------------------------------- */
    for (i = 0; i < 6; i++) {
        before_d = PORTD;
        before_b = PORTB;
        clear_tx();
        receive((uint8_t)('A' + i), 0);
        poll(&s, &led_off);
        CHECK(*relay_port[i] & _BV(relay_bit[i]), "relay %c: its pin did not go high", 'A' + i);
        CHECK((uint8_t)(PORTD ^ before_d) == (relay_port[i] == &PORTD ? _BV(relay_bit[i]) : 0),
              "relay %c: PORTD %02x -> %02x, moved more than its own pin", 'A' + i, before_d, PORTD);
        CHECK((uint8_t)((PORTB ^ before_b) & ~_BV(PB2)) == (relay_port[i] == &PORTB ? _BV(relay_bit[i]) : 0),
              "relay %c: PORTB %02x -> %02x, moved more than its own pin", 'A' + i, before_b, PORTB);
        CHECK(reports() == 1, "relay %c: %d replies, want 1", 'A' + i, reports());

        receive((uint8_t)('a' + i), 0);
        poll(&s, &led_off);
        CHECK(!(*relay_port[i] & _BV(relay_bit[i])), "relay %c: its pin did not go low", 'A' + i);
    }
    CHECK((PORTD & 0xF8) == 0 && (PORTB & 0x03) == 0, "not all off: D %02x B %02x", PORTD, PORTB);

    /* ---- handwheel select -------------------------------------------- */
    receive('T', 0);
    poll(&s, &led_off);
    CHECK(PORTB & _BV(PB1), "'T' did not raise MPG_SEL");
    CHECK((PORTD & 0xF8) == 0, "'T' moved a relay");
    receive('t', 0);
    poll(&s, &led_off);
    CHECK(!(PORTB & _BV(PB1)), "'t' did not lower MPG_SEL");

    /* ---- garbled bytes are dropped in the interrupt ------------------- */
    {
        static const uint8_t errs[3] = {_BV(FE0), _BV(DOR0), _BV(UPE0)};
        static const char *name[3] = {"framing", "overrun", "parity"};
        for (i = 0; i < 3; i++) {
            before_d = PORTD;
            clear_tx();
            receive('A', errs[i]);
            poll(&s, &led_off);
            CHECK(PORTD == before_d, "%s error: an 'A' was acted on", name[i]);
            CHECK(tx_len == 0, "%s error: the board replied", name[i]);
        }
    }

    /* ---- bytes that are not commands ---------------------------------- */
    /* Let the LED finish its last blink first, so it does not count as a
     * pin the non-commands moved. */
    for (i = 0; i < LED_BLINK_MS; i++)
        poll(&s, &led_off);
    before_d = PORTD;
    before_b = PORTB;
    clear_tx();
    for (i = 0; i < 256; i++) {
        if (strchr("ABCDEFabcdefTt?", i) && i)
            continue;
        receive((uint8_t)i, 0);
        poll(&s, &led_off);
    }
    CHECK(PORTD == before_d && PORTB == before_b, "a non-command byte moved a pin");
    CHECK(tx_len == 0, "a non-command byte got a reply: '%s'", tx_log);

    /* ---- a burst, all received before the loop runs ------------------- */
    clear_tx();
    receive('A', 0);
    receive('C', 0);
    receive('E', 0);
    poll(&s, &led_off);
    CHECK((PORTD & 0xF8) == (_BV(PD3) | _BV(PD5) | _BV(PD7)), "burst ACE: PORTD %02x", PORTD);
    CHECK(reports() == 3, "burst ACE: %d replies, want 3", reports());
    clear_tx();
    for (i = 0; i < 6; i++)
        receive((uint8_t)('a' + i), 0);
    poll(&s, &led_off);
    CHECK((PORTD & 0xF8) == 0 && !(PORTB & 1), "burst abcdef left a relay on");

    /* ---- a flood: the buffer fills, nothing breaks -------------------- */
    clear_tx();
    for (i = 0; i < 40; i++)
        receive('B', 0);
    poll(&s, &led_off);
    n = reports();
    CHECK(n == RX_SIZE - 1, "flood: %d accepted, want %d", n, RX_SIZE - 1);
    CHECK(PORTD & _BV(PD4), "flood: relay B not on");
    receive('b', 0);
    poll(&s, &led_off);
    CHECK(!(PORTD & _BV(PD4)), "after a flood the buffer no longer accepts commands");

    /* ---- status query ------------------------------------------------- */
    receive('C', 0);
    poll(&s, &led_off);
    clear_tx();
    before_d = PORTD;
    receive('?', 0);
    poll(&s, &led_off);
    CHECK(!strcmp(tx_log, "R:abCdef M:jog\r\n"), "'?' replied '%s'", tx_log);
    CHECK(PORTD == before_d, "'?' moved a pin");

    /* ---- the activity LED --------------------------------------------- */
    receive('c', 0);
    poll(&s, &led_off);
    CHECK(!(PORTB & _BV(PB2)), "LED did not blink off on a command");
    for (i = 1; i < LED_BLINK_MS; i++)
        poll(&s, &led_off);
    CHECK(PORTB & _BV(PB2), "LED did not come back on after %d ms", LED_BLINK_MS);
    CHECK(wdt_kicks > 0, "the loop never kicks the watchdog");

    if (failures) {
        printf("%d check(s) failed\n", failures);
        return 1;
    }
    printf("firmware  : setup, 6 relays, select, 3 error kinds, 241 non-commands,\n"
           "            bursts, a flood, '?', the LED - all as intended\n");
    return 0;
}
