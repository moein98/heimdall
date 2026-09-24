/*
 * Host test for commands.c - compiled with an ordinary PC compiler, no AVR.
 *
 * Every one of the 256 byte values is tried from a known state, not a handful
 * of chosen ones: the property that matters most is that nothing outside the
 * command set changes anything, and only an exhaustive pass shows that.
 */
#include <stdio.h>
#include <string.h>

#include "commands.h"

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

static const char *status(const board_state *s)
{
    static char buf[STATUS_LEN + 1];
    uint8_t n = board_status(s, buf);
    buf[n] = 0;
    return buf;
}

int main(void)
{
    board_state s;
    int c, i;

    /* Power-up state. */
    board_init(&s);
    CHECK(s.relays == 0 && s.thc == 0, "init: relays %02x thc %d", s.relays, s.thc);
    CHECK(!strcmp(status(&s), "R:abcdef M:jog\r\n"), "init status '%s'", status(&s));
    CHECK(strlen(status(&s)) < STATUS_LEN, "status overruns its buffer");

    /* Every byte, from a known mixed state. */
    for (c = 0; c < 256; c++) {
        uint8_t r, want_relays = 0x15, want_thc = 1, want_r = CMD_IGNORED;
        s.relays = 0x15;                /* A, C, E on */
        s.thc = 1;
        if (c >= 'A' && c <= 'F') {
            want_relays |= (uint8_t)(1u << (c - 'A'));
            want_r = CMD_CHANGED;
        } else if (c >= 'a' && c <= 'f') {
            want_relays &= (uint8_t)~(1u << (c - 'a'));
            want_r = CMD_CHANGED;
        } else if (c == 'T') {
            want_r = CMD_CHANGED;
        } else if (c == 't') {
            want_thc = 0;
            want_r = CMD_CHANGED;
        } else if (c == '?') {
            want_r = CMD_REPORT;
        }
        r = board_apply(&s, (uint8_t)c);
        CHECK(r == want_r, "byte 0x%02x: returned %d, want %d", c, r, want_r);
        CHECK(s.relays == want_relays, "byte 0x%02x: relays %02x, want %02x",
              c, s.relays, want_relays);
        CHECK(s.thc == want_thc, "byte 0x%02x: thc %d, want %d", c, s.thc, want_thc);
    }

    /* The relay bits never go past F, whatever is sent. */
    board_init(&s);
    for (c = 0; c < 256; c++)
        board_apply(&s, (uint8_t)c);
    CHECK((s.relays & 0xC0) == 0, "bits beyond relay F set: %02x", s.relays);

    /* A sequence Mach3 might really send. */
    board_init(&s);
    {
        const char *seq = "ACEt?T";
        for (i = 0; seq[i]; i++)
            board_apply(&s, (uint8_t)seq[i]);
    }
    CHECK(!strcmp(status(&s), "R:AbCdEf M:thc\r\n"), "sequence status '%s'", status(&s));

    /* Everything off again in one burst. */
    {
        const char *seq = "abcdef";
        for (i = 0; seq[i]; i++)
            board_apply(&s, (uint8_t)seq[i]);
    }
    CHECK(s.relays == 0, "abcdef left relays %02x", s.relays);

    /* Idempotent: turning on twice, or off twice, is the same as once. */
    board_init(&s);
    board_apply(&s, 'B');
    board_apply(&s, 'B');
    CHECK(s.relays == 0x02, "B twice: %02x", s.relays);
    board_apply(&s, 'b');
    board_apply(&s, 'b');
    CHECK(s.relays == 0, "b twice: %02x", s.relays);

    if (failures) {
        printf("%d check(s) failed\n", failures);
        return 1;
    }
    printf("commands  : all 256 byte values and 4 sequences behave\n");
    return 0;
}
