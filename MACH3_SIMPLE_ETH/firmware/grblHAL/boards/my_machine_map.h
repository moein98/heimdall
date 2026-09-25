/*
  my_machine_map.h - MACH3-SIMPLE-ETH, RP2350B (80-pin, GPIO0-47), W5500 Ethernet

  Eight independent axes (X Y Z A B C U V), every GPIO used:

    GP0  GP1        UART0 TX/RX   -> RS485 transceiver, Modbus VFD   (stream 0)
    GP2  .. GP9     STEP X Y Z A B C U V (PIO, must be consecutive)
    GP10 .. GP17    DIR  X Y Z A B C U V (consecutive, GPIO_SHIFT10)
    GP18            stepper enable, all axes
    GP19            SD card CS
    GP20 .. GP23    SPI0 MISO, W5500 CS, SCK, MOSI (W5500 and SD share SPI0)
    GP24            W5500 INT
    GP25            RS485 DE/RE (Modbus direction, aux out 0)
    GP26 .. GP33    LIMIT X Y Z A B C U V
    GP34 .. GP37    E-STOP, FEED HOLD, CYCLE START, PROBE
    GP38 .. GP40    ARC OK, THC UP, THC DOWN (plasma plugin, aux in)
    GP41            spindle PWM (-> isolated 0-10 V)
    GP42 GP43       UART1 TX/RX   -> handwheel MCU, MPG mode 2       (stream 1)
    GP44 GP45       spindle enable (FWD), direction (REV)
    GP46 GP47       I2C1 SDA/SCL  -> MCP23017: port A = 6 relays + spindle AUX + LED,
                                                port B = 8 spare inputs

  W5500 reset is tied to the board reset, so it needs no GPIO.
  UART, SPI and I2C pins checked against the SDK FUNCSEL table (io_bank0.h):
  UART0 0/1, UART1 42/43 (UART_AUX on RP2350), SPI0 20-23, I2C1 46/47.

  Part of grblHAL, GPLv3 - see COPYING.
*/

#if TRINAMIC_ENABLE
#error Trinamic plugin not supported!
#endif

#if N_ABC_MOTORS > 5
#error "Axis configuration is not supported!"
#endif

#if RP_MCU != 2350
#error "Board has a RP2350B processor! Build with PICO_BOARD=pimoroni_pga2350 or a RP2350B board file."
#endif

#define BOARD_NAME "MACH3-SIMPLE-ETH"

#undef I2C_ENABLE
#define I2C_ENABLE              1

// Step pulses: PIO, eight consecutive pins from STEP_PINS_BASE.
#define STEP_PORT               GPIO_PIO
#define STEP_PINS_BASE          2

// Direction: eight consecutive pins from X_DIRECTION_PIN.
#define DIRECTION_PORT          GPIO_OUTPUT
#define X_DIRECTION_PIN         10
#define Y_DIRECTION_PIN         11
#define Z_DIRECTION_PIN         12
#define DIRECTION_OUTMODE       GPIO_SHIFT10

#define ENABLE_PORT             GPIO_OUTPUT
#define STEPPERS_ENABLE_PIN     18

#define X_LIMIT_PIN             26
#define Y_LIMIT_PIN             27
#define Z_LIMIT_PIN             28
#define LIMIT_INMODE            GPIO_MAP

#if N_ABC_MOTORS > 0
#define M3_AVAILABLE
#define M3_STEP_PIN             (STEP_PINS_BASE + 3)
#define M3_DIRECTION_PIN        (X_DIRECTION_PIN + 3)
#define M3_LIMIT_PIN            29
#endif
#if N_ABC_MOTORS > 1
#define M4_AVAILABLE
#define M4_STEP_PIN             (STEP_PINS_BASE + 4)
#define M4_DIRECTION_PIN        (X_DIRECTION_PIN + 4)
#define M4_LIMIT_PIN            30
#endif
#if N_ABC_MOTORS > 2
#define M5_AVAILABLE
#define M5_STEP_PIN             (STEP_PINS_BASE + 5)
#define M5_DIRECTION_PIN        (X_DIRECTION_PIN + 5)
#define M5_LIMIT_PIN            31
#endif
#if N_ABC_MOTORS > 3
#define M6_AVAILABLE
#define M6_STEP_PIN             (STEP_PINS_BASE + 6)
#define M6_DIRECTION_PIN        (X_DIRECTION_PIN + 6)
#define M6_LIMIT_PIN            32
#endif
#if N_ABC_MOTORS > 4
#define M7_AVAILABLE
#define M7_STEP_PIN             (STEP_PINS_BASE + 7)
#define M7_DIRECTION_PIN        (X_DIRECTION_PIN + 7)
#define M7_LIMIT_PIN            33
#endif

// Auxiliary outputs.
#define AUXOUTPUT0_PORT         GPIO_OUTPUT // RS485 DE/RE
#define AUXOUTPUT0_PIN          25
#define AUXOUTPUT1_PORT         GPIO_OUTPUT // Spindle PWM
#define AUXOUTPUT1_PIN          41
#define AUXOUTPUT2_PORT         GPIO_OUTPUT // Spindle enable (VFD FWD)
#define AUXOUTPUT2_PIN          44
#define AUXOUTPUT3_PORT         GPIO_OUTPUT // Spindle direction (VFD REV)
#define AUXOUTPUT3_PIN          45

#if DRIVER_SPINDLE_ENABLE
#define SPINDLE_PORT            GPIO_OUTPUT
#endif
#if DRIVER_SPINDLE_ENABLE & SPINDLE_PWM
#define SPINDLE_PWM_PIN         AUXOUTPUT1_PIN
#endif
#if DRIVER_SPINDLE_ENABLE & SPINDLE_ENA
#define SPINDLE_ENABLE_PIN      AUXOUTPUT2_PIN
#endif
#if DRIVER_SPINDLE_ENABLE & SPINDLE_DIR
#define SPINDLE_DIRECTION_PIN   AUXOUTPUT3_PIN
#endif

// Auxiliary inputs.
#define AUXINPUT0_PIN           34 // E-stop
#define AUXINPUT1_PIN           35 // Feed hold
#define AUXINPUT2_PIN           36 // Cycle start
#define AUXINPUT3_PIN           37 // Probe
#define AUXINPUT4_PIN           38 // Arc OK
#define AUXINPUT5_PIN           39 // THC up
#define AUXINPUT6_PIN           40 // THC down

#if CONTROL_ENABLE & CONTROL_HALT
#define RESET_PIN               AUXINPUT0_PIN
#endif
#if CONTROL_ENABLE & CONTROL_FEED_HOLD
#define FEED_HOLD_PIN           AUXINPUT1_PIN
#endif
#if CONTROL_ENABLE & CONTROL_CYCLE_START
#define CYCLE_START_PIN         AUXINPUT2_PIN
#endif
#if PROBE_ENABLE
#define PROBE_PIN               AUXINPUT3_PIN
#endif

// SPI0: W5500 and SD card.
#if SDCARD_ENABLE || ETHERNET_ENABLE
#define SPI_PORT                0
#define SPI_SCK_PIN             22
#define SPI_MOSI_PIN            23
#define SPI_MISO_PIN            20
#if SDCARD_ENABLE
#define SD_CS_PIN               19
#endif
#if ETHERNET_ENABLE
#define SPI_CS_PIN              21
#define SPI_IRQ_PIN             24
#define WIZNET_CS_PIN           SPI_CS_PIN
#endif
#endif

// I2C1: MCP23017 (relays), optional FRAM.
#if I2C_ENABLE
#define I2C_PORT                1
#define I2C_SDA                 46
#define I2C_SCL                 47
#endif

// UART0: RS485 / Modbus VFD. UART1: handwheel MCU (MPG).
#define UART_TX_PIN             0
#define UART_RX_PIN             1
#define SERIAL1_PORT            1
#define UART_1_TX_PIN           42
#define UART_1_RX_PIN           43

#if MODBUS_ENABLE
#define MODBUS_RTU_STREAM       0
#undef MODBUS_ENABLE
#define MODBUS_ENABLE           (MODBUS_RTU_ENABLED|MODBUS_RTU_DIR_ENABLED)
#define MODBUS_DIR_AUX          0
#endif

// MPG_STREAM defaults to 1 (UART1) when Modbus has stream 0.
