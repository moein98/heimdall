/* Host stand-in for <avr/io.h>: the registers main.c touches, as plain
 * variables, with the bit numbers from the ATmega328P datasheet. */
#ifndef HOSTSTUB_AVR_IO_H
#define HOSTSTUB_AVR_IO_H
#include <stdint.h>
#define _BV(b) (1u << (b))
static volatile uint8_t PORTB, DDRB, PORTC, DDRC, PORTD, DDRD, MCUSR;
static volatile uint8_t UCSR0A, UCSR0B, UCSR0C, UBRR0H, UBRR0L, UDR0;
enum { PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7 };
enum { PD0, PD1, PD2, PD3, PD4, PD5, PD6, PD7 };
/* UCSR0A */
#define MPCM0 0
#define U2X0  1
#define UPE0  2
#define DOR0  3
#define FE0   4
#define UDRE0 5
#define TXC0  6
#define RXC0  7
/* UCSR0B */
#define TXB80  0
#define RXB80  1
#define UCSZ02 2
#define TXEN0  3
#define RXEN0  4
#define UDRIE0 5
#define TXCIE0 6
#define RXCIE0 7
/* UCSR0C */
#define UCPOL0 0
#define UCSZ00 1
#define UCSZ01 2
#endif
