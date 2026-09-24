#ifndef HOSTSTUB_AVR_POWER_H
#define HOSTSTUB_AVR_POWER_H
static int clock_divider = 8;           /* as shipped: CKDIV8 */
#define clock_div_1 1
#define clock_prescale_set(d) (clock_divider = (d))
#endif
