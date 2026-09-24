#ifndef HOSTSTUB_AVR_INTERRUPT_H
#define HOSTSTUB_AVR_INTERRUPT_H
/* An interrupt handler becomes a function the test can call. */
#define ISR(vector) void vector##_handler(void)
static int interrupts_on;
#define sei() (interrupts_on = 1)
#define cli() (interrupts_on = 0)
#endif
