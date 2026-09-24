#include "commands.h"

void board_init(board_state *s)
{
    s->relays = 0;
    s->thc = 0;
}

uint8_t board_apply(board_state *s, uint8_t c)
{
    if (c >= 'A' && c < 'A' + RELAY_COUNT) {
        s->relays |= (uint8_t)(1u << (c - 'A'));
        return CMD_CHANGED;
    }
    if (c >= 'a' && c < 'a' + RELAY_COUNT) {
        s->relays &= (uint8_t)~(1u << (c - 'a'));
        return CMD_CHANGED;
    }
    if (c == 'T') {
        s->thc = 1;
        return CMD_CHANGED;
    }
    if (c == 't') {
        s->thc = 0;
        return CMD_CHANGED;
    }
    if (c == '?')
        return CMD_REPORT;
    return CMD_IGNORED;
}

uint8_t board_status(const board_state *s, char *buf)
{
    uint8_t n = 0, i;
    static const char mode_thc[] = " M:thc\r\n";
    static const char mode_jog[] = " M:jog\r\n";
    const char *m = s->thc ? mode_thc : mode_jog;

    buf[n++] = 'R';
    buf[n++] = ':';
    for (i = 0; i < RELAY_COUNT; i++)
        buf[n++] = (char)(((s->relays >> i) & 1u) ? 'A' + i : 'a' + i);
    while (*m)
        buf[n++] = *m++;
    return n;
}
