#ifndef HOSTSTUB_AVR_WDT_H
#define HOSTSTUB_AVR_WDT_H
static int wdt_on, wdt_kicks;
#define WDTO_1S 6
#define wdt_enable(t) (wdt_on = (t) + 1)
#define wdt_disable() (wdt_on = 0)
#define wdt_reset() (wdt_kicks++)
#endif
