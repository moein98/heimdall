#!/usr/bin/env python3
"""MACH3-SIMPLE-ETH: MACH3-SIMPLE A1 with Ethernet in place of the LPT ports.

An RP2350B runs grblHAL on the board. It plans the motion and makes the step
pulses itself; the PC, a tablet or nothing at all (SD card) only sends G-code.
Eight independent coordinated axes, W5500 Ethernet, RS485 for Modbus VFDs.

Every GPIO is assigned in docs/SPEC.md and in the grblHAL board map
firmware/grblHAL/boards/my_machine_map.h. The table GPIO below is the one
place the schematic takes them from, and tools/check_pinmap.py reads the
netlist back and compares it with the board map - a pin moved in one and not
the other fails that check, not the first power-up.

What comes from where:

* **A1, unchanged:** the 24 V input, fuse, reverse diode and TVS; the
  LM2596S-5.0 buck; the opto input channel (4k7 1206, anti-parallel diode
  across the LED, PC847 on SMD DIP-16, collector and emitter read from the
  symbol geometry); the six relay channels; the whole isolated VFD block.
* **Raspberry Pi / WIZnet W5500-EVB-Pico2 (RP2350 + W5500 on one board):**
  the RP2350 core - internal switching regulator with a 3.3 uH inductor,
  VREG_AVDD through 10R with 2.2 uF, 12 MHz crystal with 1k in XOUT and
  15 pF loads, 27R in the USB lines, 1k from QSPI_SS to the BOOTSEL button -
  and the W5500 - 25 MHz crystal with 1M across it and 18 pF loads, 12.4k 1 %
  on EXRES1, 49.9R terminations, 3.3R series in each pair, 6.8 nF in the
  receive pair, 10R and 22 nF on the transmit centre tap, 4.7 uF on TOCAP,
  0.1 uF on 1V2O, a ferrite-fed analog supply, 1 nF 2 kV shield to ground.
* **Phil Barrett's RP23CNC (read, not copied):** 3.3 V logic into
  AHCT/ACT buffers running at 5 V for the step/dir outputs; a pull-up on the
  W5500 interrupt even though the chip has one.

New here, and why:

* **74ACT245, not A1's 74AC245.** The RP2350 drives 3.3 V. A 74AC245 on 5 V
  wants 3.5 V for a high; an ACT part has TTL thresholds (2.0 V) and the same
  24 mA drive. Same for the 74HCT14 in the spindle channel.
* **Opto pull-ups to +3V3, 4k7.** The RP2350's inputs are 3.3 V, and 4k7 is
  well inside what overrides the chip's own pull-down (erratum RP2350-E9).
* **Relays on an MCP23017**, AO3400A gates: 3.3 V is too little gate for a
  2N7002 at relay current.
* **Handwheel on a small ATmega328P at 3.3 V / 8 MHz** that sends jog
  commands to grblHAL on UART1. grblHAL's RP2350 driver has no quadrature
  input of its own for a handwheel. At 3.3 V because GP42/43 are ADC pins
  and not 5 V tolerant.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schgen import Sheet, fmt, uid                           # noqa: E402

PROJECT = 'MACH3SIMPLEETH'
HW = 'hardware'
REV = 'ETH-0 ENGINEERING ONLY'
ROOT_UUID = '8c3d2b51-0001-4000-8000-000000000001'

SHEETS = {
    '01_power':    ('8c3d2b51-0002-4000-8000-000000000001',
                    'Power - 24 V in, 5 V and 3.3 V made on board'),
    '02_mcu':      ('8c3d2b51-0002-4000-8000-000000000002',
                    'RP2350B, flash, USB, SD card'),
    '03_ethernet': ('8c3d2b51-0002-4000-8000-000000000003',
                    'Ethernet - W5500 and magjack'),
    '04_outputs':  ('8c3d2b51-0002-4000-8000-000000000004',
                    'Outputs - 8 axes step/dir, enable, buffered 5 V'),
    '05_inputs':   ('8c3d2b51-0002-4000-8000-000000000005',
                    'Inputs - 15 opto-isolated 24 V channels'),
    '06_relays':   ('8c3d2b51-0002-4000-8000-000000000006',
                    'MCP23017 and six relays'),
    '07_spindle':  ('8c3d2b51-0002-4000-8000-000000000007',
                    'Spindle - isolated 0-10 V and FWD-REV-AUX'),
    '08_comms':    ('8c3d2b51-0002-4000-8000-000000000008',
                    'RS485 VFD port and handwheel MCU'),
}

TERM = ('TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-%d'
        '_1x%02d_P5.00mm_Horizontal')
R0603 = 'Resistor_SMD:R_0603_1608Metric'
R1206 = 'Resistor_SMD:R_1206_3216Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
C1206 = 'Capacitor_SMD:C_1206_3216Metric'
LED0603 = 'LED_SMD:LED_0603_1608Metric'
SOIC8 = 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
SOIC14 = 'Package_SO:SOIC-14_3.9x8.7mm_P1.27mm'
SOIC20 = 'Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm'
SMDIP16 = 'Package_DIP:SMDIP-16_W9.53mm'
SOD123 = 'Diode_SMD:D_SOD-123'
SOT23 = 'Package_TO_SOT_SMD:SOT-23'
XTAL = 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm'
BUTTON = 'Button_Switch_SMD:SW_SPST_PTS810'

AXES = ['X', 'Y', 'Z', 'A', 'B', 'C', 'U', 'V']

# ---------------------------------------------------------------------------
# The RP2350B pin map. Keep in step with docs/SPEC.md and my_machine_map.h;
# tools/check_pinmap.py compares all three.
GPIO = {0: 'RS485_DI', 1: 'RS485_RO'}
for _i, _a in enumerate(AXES):
    GPIO[2 + _i] = '%s_STEP3' % _a           # PIO, consecutive
    GPIO[10 + _i] = '%s_DIR3' % _a           # consecutive
    GPIO[26 + _i] = '%s_LIM' % _a
GPIO.update({
    18: 'EN3',
    19: 'SD_CS',
    20: 'SPI_MISO', 21: 'ETH_CS', 22: 'SPI_SCK', 23: 'SPI_MOSI',
    24: 'ETH_INT',
    25: 'RS485_DE',
    34: 'ESTOP', 35: 'FEED_HOLD', 36: 'CYCLE_START', 37: 'PROBE',
    38: 'ARC_OK', 39: 'THC_UP', 40: 'THC_DOWN',
    41: 'SP_PWM_IN',
    42: 'UART1_TX', 43: 'UART1_RX',
    44: 'SP_FWD_IN', 45: 'SP_REV_IN',
    46: 'I2C_SDA', 47: 'I2C_SCL',
})
assert sorted(GPIO) == list(range(48)), 'every RP2350B GPIO must be assigned'

# 24 V opto channels: (net, terminal legend). Limits, then control, then THC.
LIMITS = [('%s_LIM' % a, a) for a in AXES]
CONTROL = [('ESTOP', 'EST'), ('FEED_HOLD', 'HLD'), ('CYCLE_START', 'RUN'),
           ('PROBE', 'PRB')]
THC = [('ARC_OK', 'AOK'), ('THC_UP', 'UP'), ('THC_DOWN', 'DN')]
INPUTS = LIMITS + CONTROL + THC
RELAYS = 'ABCDEF'


def TOP_PIN(position, ways):
    """Pin number of the `position`-th screw from the left, 0-based.

    Top-edge terminals are turned 180 degrees so the wire enters from the
    edge, which puts pin 1 at the right. A0 of MACH3-SIMPLE wired pin 1 to the
    first word of each legend and printed every legend backwards; this is the
    fix it got, kept.
    """
    return ways - position


def sheet(key):
    u, title = SHEETS[key]
    return Sheet(key + '.kicad_sch', title, PROJECT, ROOT_UUID, u, rev=REV)


def opto_pins(u):
    """(anode, cathode, collector, emitter) from the symbol's geometry.

    Never from the order the pins are listed in: PC847 unit 1 lists 1, 2, 15,
    16, and reading that positionally makes the emitter the collector.
    """
    led = sorted((q for q in u.pins if int(q['num']) <= 8), key=lambda q: -q['y'])
    tr = sorted((q for q in u.pins if int(q['num']) > 8), key=lambda q: -q['y'])
    if len(led) != 2 or len(tr) != 2:
        raise ValueError('%s: expected 2 LED and 2 transistor pins' % u.ref)
    return led[0]['num'], led[1]['num'], tr[0]['num'], tr[1]['num']


def cap(s, ref, value, x, y, a, b, fp=C0603, rot=0):
    c = s.place('Device', 'C', ref, value, x, y, footprint=fp, rot=rot)
    s.net(c, 1, a)
    s.net(c, 2, b)
    return c


def res(s, ref, value, x, y, a, b, fp=R0603, rot=0):
    r = s.place('Device', 'R', ref, value, x, y, footprint=fp, rot=rot)
    s.net(r, 1, a)
    s.net(r, 2, b)
    return r


def by_name(u):
    """Pin name -> [pin numbers]. Power pins repeat, so a list."""
    out = {}
    for p in u.pins:
        out.setdefault(p['name'], []).append(p['num'])
    return out


def pwr_flag(s, ref, net, x, y):
    """PWR_FLAG on a rail no symbol pin drives: one fed through a passive
    part (inductor, resistor, ferrite), which ERC cannot see through."""
    # Through Sheet.net, which checks the stub against every wire and label
    # already on the sheet. A bare wire here, as A1's flags were drawn, landed
    # on neighbouring labels and joined +1V1 to +3V3 and +3V3A to GND - ERC
    # reported both only as "multiple net names" warnings.
    fl = s.place('power', 'PWR_FLAG', ref, 'PWR_FLAG', x, y)
    s.net(fl, '1', net)


def add_test_points(s, points, x0, y0):
    for i, (ref, net, label) in enumerate(points):
        tp = s.place('Connector', 'TestPoint', ref, label, x0 + i * 25.4, y0,
                     footprint='TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm')
        tp.in_bom = 'no'
        s.net(tp, 1, net)


# ----------------------------------------------------------- 01 power --

def build_power():
    """24 V in; 5 V from the A1 buck; 3.3 V from an LDO off 5 V.

    3.3 V is linear, not a second buck: about 0.4 A worst case (W5500 130 mA,
    RP2350, SD card, MCP23017, the handwheel MCU) is 0.7 W across an
    AP7361C in SOT-223 - warm, not hot - and a linear rail is the quiet one the
    W5500's analog side and the RP2350's regulator want to start from.

    USB can power the logic for flashing and setup with no 24 V: VBUS reaches
    +5V through a Schottky, which is reverse biased whenever the buck is
    running (5.0 V on the cathode, at most 5.25 - 0.3 on the anode).
    """
    s = sheet('01_power')
    s.text('POWER. 24 V from the cabinet; 5 V and 3.3 V made on the board.', 12.7, 16.51, 2.0)
    s.text('One ground, as on A1. Only the VFD port (sheet 7) is isolated.', 12.7, 22.86)

    s.box(12.7, 40.64, 190.5, 111.76, '5 V - LM2596S-5.0 BUCK, AS A1')
    reg = s.place('Regulator_Switching', 'LM2596S-5', 'U101', 'LM2596S-5', 88.9, 81.28,
                  footprint='Package_TO_SOT_SMD:TO-263-5_TabPin3')
    cin = s.place('Device', 'C_Polarized', 'C101', '47uF 50V', 30.48, 88.9,
                  footprint='Capacitor_SMD:CP_Elec_6.3x7.7')
    dc = s.place('Device', 'D_Schottky', 'D101', 'SS34 catch', 116.84, 93.98,
                 footprint='Diode_SMD:D_SMA', rot=90)
    ind = s.place('Device', 'L', 'L101', '47uH 1.5A shielded', 137.16, 78.74,
                  footprint='Inductor_SMD:L_12x12mm_H8mm', rot=90)
    cout = s.place('Device', 'C_Polarized', 'C103', '220uF 16V low ESR', 160.02, 88.9,
                   footprint='Capacitor_SMD:CP_Elec_6.3x7.7')
    s.net(reg, 1, 'V24')
    s.net(reg, 5, 'GND')
    s.net(reg, 3, 'GND')
    s.net(reg, 2, 'BUCK_SW')
    s.net(reg, 4, '+5V')
    s.net(cin, 1, 'V24')
    s.net(cin, 2, 'GND')
    cap(s, 'C102', '1uF 50V X7R', 50.8, 88.9, 'V24', 'GND', fp=C1206)
    s.net(dc, 1, 'BUCK_SW')
    s.net(dc, 2, 'GND')
    s.net(ind, 1, 'BUCK_SW')
    s.net(ind, 2, '+5V')
    s.net(cout, 1, '+5V')
    s.net(cout, 2, 'GND')

    s.box(203.2, 40.64, 381.0, 111.76, '24 V IN, SENSOR SUPPLY - AS A1')
    j24 = s.place('Connector', 'Conn_01x04_Pin', 'J101', 'SENSORS / 24V IN',
                  215.9, 76.2, footprint=TERM % (4, 4))
    f24 = s.place('Device', 'Fuse', 'F101', '1A slow 1206', 246.38, 76.2,
                  footprint='Fuse:Fuse_1206_3216Metric', rot=90)
    d24 = s.place('Device', 'D_Schottky', 'D102', 'SS34 reverse', 279.4, 76.2,
                  footprint='Diode_SMD:D_SMA', rot=180)
    tvs = s.place('Device', 'D_TVS', 'D103', 'SMAJ26A', 309.88, 88.9,
                  footprint='Diode_SMD:D_SMA', rot=270)
    c24 = s.place('Device', 'C_Polarized', 'C104', '47uF 50V', 345.44, 88.9,
                  footprint='Capacitor_SMD:CP_Elec_6.3x7.7')
    s.net(j24, TOP_PIN(2, 4), 'VIN24')
    s.net(f24, 1, 'VIN24')
    s.link(f24, 2, d24, 2, 'VIN24F')
    s.link(d24, 1, tvs, 1, 'V24', via_y=76.2)
    s.link(tvs, 1, c24, 1, 'V24')
    s.link(tvs, 2, c24, 2, 'GND')
    s.net(j24, TOP_PIN(3, 4), 'GND')
    s.net(j24, TOP_PIN(0, 4), 'V24')
    s.net(j24, TOP_PIN(1, 4), 'GND')

    s.box(12.7, 124.46, 190.5, 185.42, '3.3 V - AP7361C LDO OFF 5 V')
    s.text('RP2350, W5500, SD card, MCP23017, handwheel MCU. ~0.4 A worst case.', 15.24, 132.08)
    ldo = s.place('Regulator_Linear', 'AP7361C-33E', 'U102', 'AP7361C-33E', 88.9, 160.02,
                  footprint='Package_TO_SOT_SMD:SOT-223-3_TabPin2')
    s.net(ldo, 1, '+5V')
    s.net(ldo, 2, 'GND')
    s.net(ldo, 3, '+3V3')
    cap(s, 'C105', '10uF 16V X7R', 40.64, 165.1, '+5V', 'GND', fp=C0805)
    cap(s, 'C106', '10uF 16V X7R', 139.7, 165.1, '+3V3', 'GND', fp=C0805)
    cap(s, 'C107', '100nF', 165.1, 165.1, '+3V3', 'GND')

    s.box(203.2, 124.46, 381.0, 185.42, 'USB POWER - LOGIC ONLY, FOR FLASHING AND SETUP')
    s.text('VBUS feeds +5V through D104. With 24 V on, the buck holds +5V at 5.0 V', 205.74, 132.08)
    s.text('and D104 is reverse biased. Relays and sensors need 24 V regardless.', 205.74, 137.16)
    dv = s.place('Device', 'D_Schottky', 'D104', 'B5819W', 266.7, 160.02,
                 footprint=SOD123, rot=180)
    s.net(dv, 2, 'VBUS')
    s.net(dv, 1, '+5V')

    s.box(12.7, 198.12, 190.5, 256.54, 'RAIL INDICATORS')
    for i, (rail, val) in enumerate((('+5V', '1k'), ('V24', '10k'), ('+3V3', '1k'))):
        y = 215.9 + i * 15.24
        r = s.place('Device', 'R', 'R%d' % (101 + i), val, 55.88, y,
                    footprint=R0603, rot=90)
        led = s.place('Device', 'LED', 'D%d' % (105 + i), rail, 106.68, y,
                      footprint=LED0603, rot=180)
        s.net(r, 1, rail)
        s.link(r, 2, led, 2)
        s.net(led, 1, 'GND')

    s.box(203.2, 198.12, 381.0, 256.54, 'CHASSIS AND POWER FLAGS')
    s.text('Magjack shield, USB shield and mounting holes are CHASSIS.', 205.74, 205.74)
    s.text('1 nF 2 kV to GND, as W5500-EVB-Pico2; R104 only if EMC says so.', 205.74, 210.82)
    cap(s, 'C108', '1nF 2kV X7R 1206', 228.6, 228.6, 'CHASSIS', 'GND', fp=C1206)
    rsh = s.place('Device', 'R', 'R104', '0R link - DO NOT FIT', 266.7, 228.6,
                  footprint=R1206, rot=90)
    rsh.dnp = 'yes'
    s.net(rsh, 1, 'CHASSIS')
    s.net(rsh, 2, 'GND')
    # +3V3 needs none: the LDO's output pin drives it.
    for i, net in enumerate(('+5V', 'VIN24', 'V24', 'GND', 'VBUS', 'CHASSIS')):
        pwr_flag(s, '#FLG%d' % (101 + i), net, 304.8 + i * 12.7, 246.38)

    s.box(12.7, 269.24, 381.0, 304.8, 'TEST POINTS AND MOUNTING')
    add_test_points(s, (('TP101', 'GND', 'GND'), ('TP102', '+5V', '5V'),
                        ('TP103', '+3V3', '3V3'), ('TP104', 'V24', '24V'),
                        ('TP105', '+1V1', '1V1')), 228.6, 292.1)
    for i in range(4):
        h = s.place('Mechanical', 'MountingHole_Pad', 'H%d' % (101 + i), 'M3',
                    30.48 + i * 38.1, 292.1,
                    footprint='MountingHole:MountingHole_3.2mm_M3_Pad_Via')
        s.net(h, 1, 'CHASSIS')
    return s


# ------------------------------------------------------------- 02 mcu --

def build_mcu():
    """RP2350B, its regulator, crystal, flash, USB, SD card, SWD, buttons.

    The core follows Raspberry Pi's minimal design as WIZnet's
    W5500-EVB-Pico2 applies it. The internal switching regulator makes
    +1V1 for DVDD: VREG_LX through L201 to the +1V1 node, which VREG_FB
    senses. The inductor must be a shielded 3.3 uH in 2016; the layout goes
    in the RP2350 hardware design guide's pattern, tight to pins 62-65.
    """
    s = sheet('02_mcu')
    s.text('RP2350B - grblHAL. 48 GPIO, all assigned: see docs/SPEC.md and', 12.7, 16.51, 2.0)
    s.text('firmware/grblHAL/boards/my_machine_map.h. tools/check_pinmap.py compares them.', 12.7, 22.86)

    mcu = s.place('MCU_RaspberryPi', 'RP2350B', 'U201', 'RP2350B', 203.2, 165.1,
                  footprint='Package_DFN_QFN:QFN-80-1EP_10x10mm_P0.4mm_EP3.4x3.4mm')
    pins = by_name(mcu)
    for name, nums in pins.items():
        if name.startswith('GPIO'):
            n = int(name.split('/')[0][4:])
            s.net(mcu, nums[0], GPIO[n])
    for n in pins['IOVDD']:
        s.net(mcu, n, '+3V3')
    for n in pins['DVDD']:
        s.net(mcu, n, '+1V1')
    s.net(mcu, pins['GND'][0], 'GND')
    s.net(mcu, pins['QSPI_IOVDD'][0], '+3V3')
    s.net(mcu, pins['USB_OTP_VDD'][0], '+3V3')
    s.net(mcu, pins['ADC_AVDD'][0], '+3V3')
    s.net(mcu, pins['VREG_VIN'][0], '+3V3')
    s.net(mcu, pins['VREG_PGND'][0], 'GND')
    s.net(mcu, pins['VREG_LX'][0], 'VREG_LX')
    s.net(mcu, pins['VREG_FB'][0], '+1V1')
    s.net(mcu, pins['VREG_AVDD'][0], 'VREG_AVDD')
    s.net(mcu, pins['XIN'][0], 'XIN')
    s.net(mcu, pins['XOUT'][0], 'XOUT')
    s.net(mcu, pins['RUN'][0], 'NRST')
    s.net(mcu, pins['SWCLK'][0], 'SWCLK')
    s.net(mcu, pins['SWDIO'][0], 'SWDIO')
    s.net(mcu, pins['USB_DP'][0], 'USB_DP_MCU')
    s.net(mcu, pins['USB_DM'][0], 'USB_DM_MCU')
    for nm in ('QSPI_SD0', 'QSPI_SD1', 'QSPI_SD2', 'QSPI_SD3', 'QSPI_SCLK'):
        s.net(mcu, pins[nm][0], nm)
    s.net(mcu, pins['~{QSPI_SS}'][0], 'QSPI_SS')
    s.nc_rest(mcu)

    s.box(12.7, 35.56, 127.0, 157.48, 'CORE SUPPLY - INTERNAL SWITCHER')
    s.text('VREG_LX -> L201 -> +1V1 (DVDD). Tight loop to pins 62-65.', 15.24, 43.18)
    l = s.place('Device', 'L', 'L201', '3.3uH 2016 shielded', 50.8, 63.5,
                footprint='Inductor_SMD:L_Murata_DFE201610P', rot=90)
    s.net(l, 1, 'VREG_LX')
    s.net(l, 2, '+1V1')
    cap(s, 'C201', '10uF 0805 X5R', 25.4, 88.9, '+3V3', 'GND', fp=C0805)   # VREG_VIN
    cap(s, 'C202', '10uF 0805 X5R', 50.8, 88.9, '+1V1', 'GND', fp=C0805)   # VREG out
    res(s, 'R201', '10R', 76.2, 63.5, '+3V3', 'VREG_AVDD')
    cap(s, 'C203', '2.2uF', 101.6, 88.9, 'VREG_AVDD', 'GND')
    for i in range(3):                       # one per DVDD pin
        cap(s, 'C%d' % (204 + i), '100nF', 25.4 + i * 25.4, 114.3, '+1V1', 'GND')
    cap(s, 'C207', '1uF', 101.6, 114.3, '+1V1', 'GND')
    pwr_flag(s, '#FLG201', '+1V1', 139.7, 50.8)
    pwr_flag(s, '#FLG202', 'VREG_AVDD', 139.7, 81.28)
    s.text('One 100 nF per IOVDD pin (8), ADC_AVDD, QSPI_IOVDD, USB_OTP_VDD:', 15.24, 132.08)
    for i in range(11):
        cap(s, 'C%d' % (210 + i), '100nF', 25.4 + (i % 4) * 25.4,
            144.78 + (i // 4) * 20.32, '+3V3', 'GND')
    cap(s, 'C221', '4.7uF', 25.4 + 3 * 25.4, 144.78 + 2 * 20.32, '+3V3', 'GND')

    s.box(12.7, 223.52, 127.0, 289.56, '12 MHz CRYSTAL')
    xt = s.place('Device', 'Crystal_GND24', 'Y201', '12MHz ABM8-272-T3', 63.5, 256.54,
                 footprint=XTAL)
    s.net(xt, 1, 'XIN')
    s.net(xt, 3, 'XOUT_X')
    s.net(xt, 2, 'GND')
    s.net(xt, 4, 'GND')
    res(s, 'R202', '1k', 101.6, 241.3, 'XOUT', 'XOUT_X')
    cap(s, 'C222', '15pF', 30.48, 276.86, 'XIN', 'GND')
    cap(s, 'C223', '15pF', 96.52, 276.86, 'XOUT_X', 'GND')

    s.box(304.8, 35.56, 482.6, 116.84, 'QSPI FLASH - 16 MB, AS THE PGA2350 THE FIRMWARE IS BUILT FOR')
    fl = s.place('Memory_Flash', 'W25Q128JVS', 'U202', 'W25Q128JVS', 355.6, 76.2,
                 footprint='Package_SO:SOIC-8_5.3x5.3mm_P1.27mm')
    s.net(fl, 1, 'QSPI_SS')
    s.net(fl, 2, 'QSPI_SD1')
    s.net(fl, 3, 'QSPI_SD2')
    s.net(fl, 4, 'GND')
    s.net(fl, 5, 'QSPI_SD0')
    s.net(fl, 6, 'QSPI_SCLK')
    s.net(fl, 7, 'QSPI_SD3')
    s.net(fl, 8, '+3V3')
    cap(s, 'C224', '100nF', 431.8, 76.2, '+3V3', 'GND')
    s.text('BOOTSEL: hold, tap RESET, release - the chip comes up as a USB drive.', 307.34, 101.6)

    s.box(304.8, 129.54, 482.6, 187.96, 'RESET AND BOOTSEL')
    s.text('NRST also resets the W5500. 10k/1uF: ~10 ms, past its 500 us minimum.', 307.34, 137.16)
    res(s, 'R203', '10k', 330.2, 160.02, '+3V3', 'NRST')
    cap(s, 'C225', '1uF', 355.6, 172.72, 'NRST', 'GND')
    sw1 = s.place('Switch', 'SW_Push', 'SW201', 'RESET', 393.7, 160.02, footprint=BUTTON)
    s.net(sw1, 1, 'NRST')
    s.net(sw1, 2, 'GND')
    res(s, 'R204', '1k', 431.8, 160.02, 'QSPI_SS', 'BOOTSEL_SW')
    sw2 = s.place('Switch', 'SW_Push', 'SW202', 'BOOTSEL', 462.28, 160.02, footprint=BUTTON)
    s.net(sw2, 1, 'BOOTSEL_SW')
    s.net(sw2, 2, 'GND')

    s.box(304.8, 200.66, 482.6, 289.56, 'USB-C - SETUP, FLASHING, SERIAL')
    usb = s.place('Connector', 'USB_C_Receptacle_USB2.0_16P', 'J201', 'USB-C', 340.36, 246.38,
                  footprint='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12')
    un = by_name(usb)
    for n in un['VBUS']:
        s.net(usb, n, 'VBUS')
    for n in un['GND']:
        s.net(usb, n, 'GND')
    s.net(usb, un['SHIELD'][0], 'CHASSIS')
    for n in un['D+']:
        s.net(usb, n, 'USB_DP')
    for n in un['D-']:
        s.net(usb, n, 'USB_DM')
    s.net(usb, un['CC1'][0], 'USB_CC1')
    s.net(usb, un['CC2'][0], 'USB_CC2')
    s.nc(usb, un['SBU1'][0])
    s.nc(usb, un['SBU2'][0])
    res(s, 'R205', '5.1k', 386.08, 269.24, 'USB_CC1', 'GND')
    res(s, 'R206', '5.1k', 411.48, 269.24, 'USB_CC2', 'GND')
    res(s, 'R207', '27R', 434.34, 220.98, 'USB_DP', 'USB_DP_MCU')
    res(s, 'R208', '27R', 434.34, 241.3, 'USB_DM', 'USB_DM_MCU')
    esd = s.place('Power_Protection', 'USBLC6-2SC6', 'U203', 'USBLC6-2SC6', 459.74, 269.24,
                  footprint='Package_TO_SOT_SMD:SOT-23-6')
    s.net(esd, 1, 'USB_DP')
    s.net(esd, 6, 'USB_DP')
    s.net(esd, 3, 'USB_DM')
    s.net(esd, 4, 'USB_DM')
    s.net(esd, 2, 'GND')
    s.net(esd, 5, 'VBUS')

    s.box(304.8, 302.26, 482.6, 360.68, 'SWD DEBUG')
    swd = s.place('Connector_Generic', 'Conn_01x04', 'J202', 'SWD', 340.36, 330.2,
                  footprint='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical')
    for pin, net in ((1, '+3V3'), (2, 'SWCLK'), (3, 'SWDIO'), (4, 'GND')):
        s.net(swd, pin, net)

    s.box(12.7, 302.26, 289.56, 373.38, 'SD CARD - SHARES SPI0 WITH THE W5500')
    sd = s.place('Connector', 'Micro_SD_Card_Det_Hirose_DM3AT', 'J203', 'microSD',
                 76.2, 337.82, footprint='Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5')
    sn = by_name(sd)
    s.net(sd, sn['DAT3/CD'][0], 'SD_CS')
    s.net(sd, sn['CMD'][0], 'SPI_MOSI')
    s.net(sd, sn['CLK'][0], 'SPI_SCK')
    s.net(sd, sn['DAT0'][0], 'SPI_MISO')
    s.net(sd, sn['VDD'][0], '+3V3')
    s.net(sd, sn['VSS'][0], 'GND')
    s.net(sd, sn['DAT1'][0], 'SD_DAT1')
    s.net(sd, sn['DAT2'][0], 'SD_DAT2')
    s.net(sd, sn['SHIELD'][0], 'GND')
    s.nc(sd, sn['DET_A'][0])
    s.nc(sd, sn['DET_B'][0])
    # SPI-mode SD: CS and the unused data lines held high so the card stays
    # in SPI mode and off the bus while the W5500 talks; MISO pulled up so it
    # is not floating when neither device drives it.
    for i, net in enumerate(('SD_CS', 'SD_DAT1', 'SD_DAT2', 'SPI_MISO', 'ETH_CS')):
        res(s, 'R%d' % (209 + i), '10k', 139.7 + i * 25.4, 320.04, '+3V3', net)
    cap(s, 'C226', '10uF 0805', 139.7, 350.52, '+3V3', 'GND', fp=C0805)
    cap(s, 'C227', '100nF', 165.1, 350.52, '+3V3', 'GND')
    return s


# -------------------------------------------------------- 03 ethernet --

def build_ethernet():
    """W5500 and a HanRun HR911105A magjack, after WIZnet's W5500-EVB-Pico2.

    Pair polarity: TXP to TD+, TXN to TD-, RXP to RD+, RXN to RD-. The W5500
    also corrects receive polarity and does Auto-MDIX, but there is no
    reason to lean on either.
    """
    s = sheet('03_ethernet')
    s.text('ETHERNET. W5500 on SPI0 (with the SD card). 10/100, Auto-MDIX.', 12.7, 16.51, 2.0)
    s.text('Layout: 100 ohm differential pairs, short, no vias, nothing under the magjack.', 12.7, 22.86)

    w = s.place('Interface_Ethernet', 'W5500', 'U301', 'W5500', 190.5, 139.7,
                footprint='Package_QFP:LQFP-48_7x7mm_P0.5mm')
    wn = by_name(w)
    for n in wn['AGND']:
        s.net(w, n, 'GND')
    for n in wn['AVDD']:
        s.net(w, n, '+3V3A')
    s.net(w, wn['VDD'][0], '+3V3')
    s.net(w, wn['GND'][0], 'GND')
    s.net(w, wn['TXP'][0], 'ETH_TXP')
    s.net(w, wn['TXN'][0], 'ETH_TXN')
    s.net(w, wn['RXP'][0], 'ETH_RXP')
    s.net(w, wn['RXN'][0], 'ETH_RXN')
    s.net(w, wn['EXRES1'][0], 'ETH_EXRES')
    s.net(w, wn['TOCAP'][0], 'ETH_TOCAP')
    s.net(w, wn['1V2O'][0], 'ETH_1V2')
    s.nc(w, wn['VBG'][0])                   # band gap: datasheet says leave open
    # RSVD 23, 38-42: tied to GND. KiCad types them as inputs and the
    # datasheet's pin table asks for GND; W5500-EVB-Pico2 leaves them open,
    # which says the chip holds them itself. Either is safe for an input.
    for n in wn['RSVD']:
        s.net(w, n, 'GND')
    for nm in ('PMODE0', 'PMODE1', 'PMODE2'):
        s.net(w, wn[nm][0], '+3V3')         # 111: all capable, auto-negotiation
    s.net(w, wn['XI/CLKIN'][0], 'ETH_XI')
    s.net(w, wn['XO'][0], 'ETH_XO')
    s.net(w, wn['~{SCS}'][0], 'ETH_CS')
    s.net(w, wn['SCLK'][0], 'SPI_SCK')
    s.net(w, wn['MISO'][0], 'SPI_MISO')
    s.net(w, wn['MOSI'][0], 'SPI_MOSI')
    s.net(w, wn['~{INT}'][0], 'ETH_INT')
    s.net(w, wn['~{RST}'][0], 'NRST')
    s.net(w, wn['LINKLED'][0], 'ETH_LINKLED')
    s.net(w, wn['ACTLED'][0], 'ETH_ACTLED')
    s.nc(w, wn['SPDLED'][0])
    s.nc(w, wn['DUPLED'][0])
    s.nc_rest(w)                            # NC and DNC pins

    s.box(12.7, 35.56, 127.0, 127.0, 'ANALOG SUPPLY +3V3A')
    fb = s.place('Device', 'FerriteBead_Small', 'FB301', '120R@100MHz 0603', 50.8, 63.5,
                 footprint='Inductor_SMD:L_0603_1608Metric', rot=90)
    s.net(fb, 1, '+3V3')
    s.net(fb, 2, '+3V3A')
    cap(s, 'C301', '10uF 0805', 25.4, 88.9, '+3V3A', 'GND', fp=C0805)
    for i in range(6):                       # one per AVDD pin
        cap(s, 'C%d' % (302 + i), '100nF', 50.8 + (i % 3) * 25.4,
            88.9 + (i // 3) * 20.32, '+3V3A', 'GND')
    cap(s, 'C308', '100nF', 25.4, 109.22, '+3V3', 'GND')      # VDD pin 28
    pwr_flag(s, '#FLG301', '+3V3A', 139.7, 50.8)
    cap(s, 'C309', '4.7uF', 101.6, 50.8, 'ETH_TOCAP', 'GND')
    cap(s, 'C310', '100nF', 76.2, 50.8, 'ETH_1V2', 'GND')
    res(s, 'R301', '12.4k 1%', 25.4, 50.8, 'ETH_EXRES', 'GND')

    s.box(12.7, 139.7, 127.0, 226.06, '25 MHz CRYSTAL, PULL-UPS')
    xt = s.place('Device', 'Crystal_GND24', 'Y301', '25MHz 18pF', 63.5, 172.72,
                 footprint=XTAL)
    s.net(xt, 1, 'ETH_XI')
    s.net(xt, 3, 'ETH_XO')
    s.net(xt, 2, 'GND')
    s.net(xt, 4, 'GND')
    res(s, 'R302', '1M', 101.6, 160.02, 'ETH_XI', 'ETH_XO')
    cap(s, 'C311', '18pF', 30.48, 195.58, 'ETH_XI', 'GND')
    cap(s, 'C312', '18pF', 96.52, 195.58, 'ETH_XO', 'GND')
    # INT has an internal pull-up; RP23CNC found it unreliable without an
    # external one. CS is pulled up on sheet 2.
    res(s, 'R303', '4.7k', 30.48, 215.9, '+3V3', 'ETH_INT')

    s.box(304.8, 35.56, 571.5, 226.06, 'LINE SIDE - TERMINATION AND MAGJACK')
    # Transmit: 3.3R series, 49.9R to +3V3A (W5500's current-mode driver).
    for i, (pin, line, term) in enumerate((('P', 'TXP', 'TDP'), ('N', 'TXN', 'TDN'))):
        res(s, 'R%d' % (304 + i), '3.3R', 330.2, 63.5 + i * 20.32, 'ETH_%s' % line,
            'ETH_%s' % term)
        res(s, 'R%d' % (306 + i), '49.9R 1%', 368.3, 50.8 + i * 20.32, '+3V3A',
            'ETH_%s' % term)
    # Receive: 3.3R series, 49.9R each to a common node decoupled to GND and
    # tied to the receive centre tap; 6.8 nF in each line.
    for i, (line, mid, jack) in enumerate((('RXP', 'RP', 'RDP'), ('RXN', 'RN', 'RDN'))):
        res(s, 'R%d' % (308 + i), '3.3R', 330.2, 119.38 + i * 20.32, 'ETH_%s' % line,
            'ETH_%s' % mid)
        res(s, 'R%d' % (310 + i), '49.9R 1%', 368.3, 106.68 + i * 20.32,
            'ETH_%s' % mid, 'ETH_RCT')
        cap(s, 'C%d' % (313 + i), '6.8nF', 406.4, 119.38 + i * 20.32,
            'ETH_%s' % mid, 'ETH_%s' % jack)
    cap(s, 'C315', '100nF', 368.3, 162.56, 'ETH_RCT', 'GND')
    res(s, 'R312', '10R 1%', 406.4, 50.8, '+3V3A', 'ETH_TCT')
    cap(s, 'C316', '22nF', 431.8, 63.5, 'ETH_TCT', 'GND')

    rj = s.place('Connector', 'RJ45_Hanrun_HR911105A_Horizontal', 'J301', 'HR911105A',
                 495.3, 119.38, footprint='Connector_RJ:RJ45_Hanrun_HR911105A_Horizontal')
    for pin, net in (('1', 'ETH_TDP'), ('2', 'ETH_TDN'), ('4', 'ETH_TCT'),
                     ('3', 'ETH_RDP'), ('6', 'ETH_RDN'), ('5', 'ETH_RCT'),
                     ('8', 'CHASSIS'), ('SH', 'CHASSIS')):
        s.net(rj, pin, net)
    s.nc(rj, '7')
    # LEDs, read off the symbol: yellow anode 12 cathode 11, green anode 9
    # cathode 10. The W5500 LED pins sink.
    s.net(rj, '12', 'ETH_LEDY_A')
    s.net(rj, '11', 'ETH_ACTLED')
    s.net(rj, '9', 'ETH_LEDG_A')
    s.net(rj, '10', 'ETH_LINKLED')
    res(s, 'R313', '330R', 431.8, 190.5, '+3V3', 'ETH_LEDY_A')
    res(s, 'R314', '330R', 482.6, 190.5, '+3V3', 'ETH_LEDG_A')
    return s


# --------------------------------------------------------- 04 outputs --

def build_outputs():
    """Seventeen buffered outputs: 8 x STEP, 8 x DIR, ENABLE.

    74ACT245 on 5 V: TTL input thresholds take the RP2350's 3.3 V, and
    24 mA outputs drive opto-input stepper drivers directly.
    """
    s = sheet('04_outputs')
    s.text('OUTPUTS. 3.3 V from the RP2350 -> 74ACT245 on 5 V -> terminals.', 12.7, 16.51, 2.0)
    s.text('NOT ISOLATED, as A1: the axis terminals share ground with the board.', 12.7, 22.86)

    lines = []
    for a in AXES:
        lines += [('%s_STEP' % a), ('%s_DIR' % a)]
    lines.append('EN')
    s.box(12.7, 35.56, 482.6, 190.5, 'BUFFERS - 74ACT245, A->B, ALWAYS ENABLED')
    bufs = []
    for k in range(3):
        u = s.place('74xx', '74HC245', 'U%d' % (401 + k), '74ACT245',
                    101.6 + k * 152.4, 88.9, footprint=SOIC20)
        s.net(u, '20', '+5V')
        s.net(u, '10', 'GND')
        s.net(u, '1', '+5V')
        s.net(u, '19', 'GND')
        bufs.append(u)
        cap(s, 'C%d' % (401 + k), '100nF', 152.4 + k * 152.4, 63.5, '+5V', 'GND')
    for i, net in enumerate(lines):
        u = bufs[i // 8]
        ch = i % 8
        s.net(u, str(2 + ch), net + '3')          # A side, 3.3 V from the MCU
        s.net(u, str(18 - ch), net)               # B side, 5 V to the terminal
    # Held low while the RP2350 is in reset or unprogrammed: its pins float
    # then, and a floating STEP input is a motor that can step on noise.
    ins = [n + '3' for n in lines]
    for k in range(4):
        rn = s.place('Device', 'R_Pack04', 'RN%d' % (401 + k), '4x10k pull-down',
                     76.2 + k * 50.8, 152.4,
                     footprint='Resistor_SMD:R_Array_Convex_4x0603')
        for m in range(4):
            s.net(rn, str(1 + m), ins[4 * k + m])
            s.net(rn, str(8 - m), 'GND')
    res(s, 'R401', '10k pull-down', 304.8, 152.4, ins[16], 'GND')
    res(s, 'R402', '10k spare pull-down', 355.6, 152.4, 'SPARE_IN', 'GND')
    for u in bufs:
        for ch in range(8):
            if str(2 + ch) not in u.used:
                s.net(u, str(2 + ch), 'SPARE_IN')
                s.nc(u, str(18 - ch))

    s.box(12.7, 203.2, 482.6, 266.7, 'AXIS TERMINALS - PULSE / GND / DIR, AND ENABLE')
    for i, a in enumerate(AXES):
        t = s.place('Connector', 'Conn_01x03_Pin', 'J%d' % (401 + i),
                    '%s axis' % a, 38.1 + i * 50.8, 243.84, footprint=TERM % (3, 3))
        s.net(t, 1, '%s_STEP' % a)
        s.net(t, 2, 'GND')
        s.net(t, 3, '%s_DIR' % a)
    t = s.place('Connector', 'Conn_01x02_Pin', 'J409', 'ENABLE', 38.1 + 8 * 50.8, 243.84,
                footprint=TERM % (2, 2))
    s.net(t, 1, 'EN')
    s.net(t, 2, 'GND')
    return s


# ---------------------------------------------------------- 05 inputs --

def build_inputs():
    """Fifteen 24 V sensor inputs on PC847s - the A1 channel, pulled to 3.3 V.

    Active low at the RP2350: a sensor that is on lights the LED, the
    transistor pulls the pin down. grblHAL's invert masks ($5, $14, $6) set
    the sense per input.
    """
    s = sheet('05_inputs')
    s.text('INPUTS. 24 V PNP sensors -> PC847 -> RP2350, active low.', 12.7, 16.51, 2.0)
    s.text('An anti-parallel diode across EVERY LED, as A1: the LED is rated 6 V reverse.', 12.7, 22.86)
    s.text('4k7 pull-ups to +3V3: strong enough for RP2350 erratum E9.', 12.7, 27.94)

    s.box(12.7, 35.56, 482.6, 327.66, '24 V INPUT CHANNELS')
    for i, (net, _lbl) in enumerate(INPUTS):
        pkg, unit = i // 4, i % 4
        y = 55.88 + i * 17.78
        u = s.place('Isolator', 'PC847', 'U%d' % (501 + pkg), 'PC847',
                    228.6, y, footprint=SMDIP16, unit=unit + 1)
        a, k, c, e = opto_pins(u)
        r = s.place('Device', 'R', 'R%d' % (501 + i), '4k7 1206', 165.1, y,
                    footprint=R1206)
        s.net(r, 1, net + '_24')
        s.net(r, 2, net + '_LED')
        s.wire(*(r.at(2) + u.at(a)))
        u.used.add(a)
        s.net(u, k, 'GND')
        s.net(u, e, 'GND')
        s.net(u, c, net)
        dr = s.place('Device', 'D', 'D%d' % (501 + i), '1N4148W', 190.5, y + 10.16,
                     footprint=SOD123)
        s.net(dr, 1, net + '_LED')
        s.net(dr, 2, 'GND')
        res(s, 'R%d' % (521 + i), '4k7', 292.1, y, net, '+3V3')
        cap(s, 'C%d' % (501 + i), '10nF', 342.9, y, net, 'GND')
    # Fifteen channels, sixteen in four packages: the last one is spare.
    sp = s.place('Isolator', 'PC847', 'U504', 'PC847', 381.0, 327.66 - 17.78,
                 footprint=SMDIP16, unit=4)
    for n in [q['num'] for q in sp.pins]:
        s.nc(sp, n)

    s.box(12.7, 340.36, 482.6, 391.16, 'TERMINALS - SENSOR +24/0V FROM J101')
    blocks = (('J501', 'LIMITS X Y Z A B C U V', LIMITS),
              ('J502', 'EST HLD RUN PRB', CONTROL),
              ('J503', 'THC AOK UP DN', THC))
    x = 38.1
    for ref, val, chans in blocks:
        n = len(chans)
        t = s.place('Connector', 'Conn_01x%02d_Pin' % n, ref, val, x, 370.84,
                    footprint=TERM % (n, n))
        for pos, (net, _l) in enumerate(chans):
            s.net(t, TOP_PIN(pos, n), net + '_24')
        x += 50.8 + n * 12.7
    return s


# ---------------------------------------------------------- 06 relays --

def build_relays():
    """MCP23017 at I2C 0x20 (grblHAL's default), six relays as A1.

    Port A outputs: GPA0-5 relays A-F, GPA6 the VFD AUX contact, GPA7 a
    status LED. Port B inputs: eight spare 3.3 V inputs on a header. grblHAL
    numbers these after the RP2350's own aux ports; `$pins` lists them.
    """
    s = sheet('06_relays')
    s.text('RELAYS. MCP23017 (I2C 0x20) -> AO3400A -> 24 V relay coils.', 12.7, 16.51, 2.0)
    s.text('G-code M62/M63 P<n> switch them, synchronised with motion; M64/M65 at once.', 12.7, 22.86)

    s.box(12.7, 35.56, 203.2, 238.76, 'MCP23017 AND EXPANSION HEADER')
    m = s.place('Interface_Expansion', 'MCP23017x-x-SO', 'U601', 'MCP23017-E/SO',
                101.6, 119.38, footprint='Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm')
    mn = by_name(m)
    s.net(m, mn['V_{DD}'][0], '+3V3')
    s.net(m, mn['V_{SS}'][0], 'GND')
    s.net(m, mn['SDA'][0], 'I2C_SDA')
    s.net(m, mn['SCK'][0], 'I2C_SCL')
    for a in ('A0', 'A1', 'A2'):
        s.net(m, mn[a][0], 'GND')            # address 0x20
    s.net(m, mn['~{RESET}'][0], 'NRST')
    s.nc(m, mn['INTA'][0])
    s.nc(m, mn['INTB'][0])
    for i, ch in enumerate(RELAYS):
        s.net(m, mn['GPA%d' % i][0], 'REL_%s' % ch)
    s.net(m, mn['GPA6'][0], 'SP_AUX_IN')
    s.net(m, mn['GPA7'][0], 'STATUS_LED')
    for i in range(8):
        s.net(m, mn['GPB%d' % i][0], 'EXP_IN%d' % i)
    s.nc_rest(m)
    cap(s, 'C601', '100nF', 30.48, 71.12, '+3V3', 'GND')
    res(s, 'R601', '4.7k', 30.48, 91.44, '+3V3', 'I2C_SDA')
    res(s, 'R602', '4.7k', 30.48, 111.76, '+3V3', 'I2C_SCL')
    res(s, 'R603', '1k', 160.02, 45.72, 'STATUS_LED', 'STATUS_LED_A')
    led = s.place('Device', 'LED', 'D601', 'STATUS', 185.42, 45.72,
                  footprint=LED0603, rot=180)
    s.net(led, 2, 'STATUS_LED_A')
    s.net(led, 1, 'GND')
    hdr = s.place('Connector_Generic', 'Conn_02x05_Odd_Even', 'J601', 'EXPANSION',
                  101.6, 213.36, footprint='Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical')
    for i in range(8):
        s.net(hdr, i + 1, 'EXP_IN%d' % i)
        res(s, 'R%d' % (604 + i), '10k', 30.48 + (i % 4) * 43.18,
            157.48 + (i // 4) * 17.78, 'EXP_IN%d' % i, '+3V3')
    s.net(hdr, 9, '+3V3')
    s.net(hdr, 10, 'GND')

    s.box(215.9, 35.56, 457.2, 302.26, 'SIX RELAYS - 24 V COILS ONLY, AS A1')
    for i, ch in enumerate(RELAYS):
        y = 76.2 + i * 38.1
        q = s.place('Transistor_FET', 'Q_NMOS_GSD', 'Q%d' % (601 + i), 'AO3400A',
                    279.4, y, footprint=SOT23)
        rg = s.place('Device', 'R', 'R%d' % (621 + i), '1k', 241.3, y, footprint=R0603)
        s.net(rg, 1, 'REL_%s' % ch)
        s.wire(*(rg.at(2) + q.at(1)))
        rg.used.add('2')
        q.used.add('1')
        # Holds the gate off while the MCP23017 is in reset: its pins come
        # up as inputs, so without this every relay could chatter at power-up.
        res(s, 'R%d' % (631 + i), '10k', 241.3, y + 15.24, 'REL_%s' % ch, 'GND')
        s.net(q, 2, 'GND')                   # Q_NMOS_GSD: 2 source, 3 drain
        s.net(q, 3, 'RELC_%s' % ch)
        k = s.place('Relay', 'JQC-3FF-024-1Z', 'K%d' % (601 + i), 'JQC-3FF-024-1Z',
                    330.2, y, footprint='Relay_THT:Relay_SPDT_Hongfa_JQC-3FF_0XX-1Z')
        s.net(k, 'A1', 'V24')
        s.net(k, 'A2', 'RELC_%s' % ch)
        fw = s.place('Device', 'D', 'D%d' % (611 + i), '1N4148W flyback', 373.38, y,
                     footprint=SOD123)
        s.net(fw, 1, 'V24')
        s.net(fw, 2, 'RELC_%s' % ch)
        s.net(k, '11', 'K%s_COM' % ch)
        s.net(k, '14', 'K%s_NO' % ch)
        s.net(k, '12', 'K%s_NC' % ch)
        s.nc_rest(k)
        t = s.place('Connector', 'Conn_01x03_Pin', 'J%d' % (611 + i), 'Relay %s' % ch,
                    419.1, y, footprint=TERM % (3, 3))
        s.net(t, 1, 'K%s_NO' % ch)
        s.net(t, 2, 'K%s_COM' % ch)
        s.net(t, 3, 'K%s_NC' % ch)
        rli = s.place('Device', 'R', 'R%d' % (641 + i), '10k', 279.4, y + 22.86,
                      footprint=R0603)
        dli = s.place('Device', 'LED', 'D%d' % (621 + i), 'K%s' % ch, 330.2, y + 22.86,
                      footprint=LED0603, rot=180)
        s.net(rli, 1, 'V24')
        s.link(rli, 2, dli, 2)
        s.net(dli, 1, 'RELC_%s' % ch)
    return s


# -------------------------------------------------------- 07 spindle --

def build_spindle():
    """The A1 isolated VFD block, fed from 3.3 V GPIO through a 74HCT14.

    Unchanged from A1 past the Schmitt buffer: PC847 across the barrier,
    B2412S isolated 12 V, 78L05 reference, chopper, two-pole filter, LM358
    x2 trimmed by RV701 to 10.0 V at 100 % PWM. PWM from GP41, FWD from
    GP44, REV from GP45 (grblHAL spindle PWM, enable, direction), AUX from
    the MCP23017's GPA6.
    """
    s = sheet('07_spindle')
    s.text('SPINDLE. 0-10 V and FWD / REV / AUX for the VFD, isolated from this board.', 12.7, 16.51, 2.0)
    s.text('grblHAL: $33 PWM frequency 100 Hz (as A1). Trim RV701 for 10.0 V at full speed.', 12.7, 24.13)

    s.box(12.7, 40.64, 190.5, 185.42, 'BOARD SIDE - GPIO TO THE LEDS')
    s.text('Pulled down, so with the RP2350 in reset every LED is dark.', 15.24, 48.26)
    s.text('74HCT14: TTL thresholds take 3.3 V; it sinks the LED current.', 15.24, 53.34)
    inv = s.place_all_units('74xx', '74HC14', 'U701', '74HCT14',
                            {1: (88.9, 76.2), 2: (88.9, 101.6), 3: (88.9, 127.0),
                             4: (88.9, 152.4), 5: (116.84, 152.4),
                             6: (144.78, 152.4), 7: (160.02, 76.2)},
                            footprint=SOIC14)
    s.net(inv[7], '14', '+5V')
    s.net(inv[7], '7', 'GND')
    for unit, (gin, gout) in ((5, ('11', '10')), (6, ('13', '12'))):
        s.net(inv[unit], gin, 'GND')
        s.nc(inv[unit], gout)
    chans = (('PWM', 1, ('1', '2')), ('FWD', 2, ('3', '4')),
             ('REV', 3, ('5', '6')), ('AUX', 4, ('9', '8')))
    for i, (name, unit, (gin, gout)) in enumerate(chans):
        y = 76.2 + i * 25.4
        res(s, 'R%d' % (701 + i), '10k pull-down', 50.8, y, 'SP_%s_IN' % name, 'GND')
        s.net(inv[unit], gin, 'SP_%s_IN' % name)
        s.net(inv[unit], gout, 'SP_%s_K' % name)
        res(s, 'R%d' % (705 + i), '330R', 132.08, y + 7.62, '+5V', 'SP_%s_A' % name)
    cap(s, 'C701', '100nF', 175.26, 88.9, '+5V', 'GND')

    s.box(203.2, 40.64, 279.4, 185.42, 'BARRIER')
    s.text('Nothing crosses this box but light', 205.74, 48.26)
    s.text('and the DC-DC module.', 205.74, 53.34)
    opto = {}
    for i, (name, _u, _p) in enumerate(chans):
        u = s.place('Isolator', 'PC847', 'U702', 'PC847', 241.3, 76.2 + i * 25.4,
                    footprint=SMDIP16, unit=i + 1)
        a, k, c, e = opto_pins(u)
        s.net(u, a, 'SP_%s_A' % name)
        s.net(u, k, 'SP_%s_K' % name)
        opto[name] = (u, c, e)
    iso = s.place('Converter_DCDC_Isolated', 'CRE1S2412SC', 'U703', 'B2412S-1WR3',
                  241.3, 172.72,
                  footprint='Converter_DCDC:Converter_DCDC_Murata_CRE1xxxxxxSC_THT')
    s.net(iso, 2, 'V24')
    s.net(iso, 1, 'GND')
    s.net(iso, 4, 'SP_12V')
    s.net(iso, 3, 'SP_ACM')
    cap(s, 'C702', '1uF 50V X7R', 175.26, 165.1, 'V24', 'GND', fp=C1206)

    s.box(292.1, 40.64, 571.5, 185.42, 'VFD SIDE - ISOLATED, ITS GROUND IS THE VFD ACM')
    reg = s.place('Regulator_Linear', 'L78L05_SOT89', 'U704', '78L05', 317.5, 165.1,
                  footprint='Package_TO_SOT_SMD:SOT-89-3')
    s.net(reg, 3, 'SP_12V')
    s.net(reg, 2, 'SP_ACM')
    s.net(reg, 1, 'SP_5V')
    cap(s, 'C703', '10uF 25V X7R', 355.6, 165.1, 'SP_12V', 'SP_ACM', fp=C1206)
    cap(s, 'C704', '1uF', 381.0, 165.1, 'SP_5V', 'SP_ACM')
    u, c, e = opto['PWM']
    s.net(u, c, 'SP_5V')
    s.net(u, e, 'SP_CHOP')
    res(s, 'R709', '2k2', 330.2, 76.2, 'SP_CHOP', 'SP_ACM')
    res(s, 'R710', '100k', 355.6, 76.2, 'SP_CHOP', 'SP_F1')
    cap(s, 'C705', '470nF', 381.0, 88.9, 'SP_F1', 'SP_ACM')
    res(s, 'R711', '100k', 406.4, 76.2, 'SP_F1', 'SP_F2')
    cap(s, 'C706', '470nF', 431.8, 88.9, 'SP_F2', 'SP_ACM')
    amp = s.place_all_units('Amplifier_Operational', 'LM358', 'U705', 'LM358',
                            {1: (477.52, 81.28), 2: (477.52, 127.0),
                             3: (447.04, 160.02)}, footprint=SOIC8)
    s.net(amp[1], '3', 'SP_F2')
    s.net(amp[1], '2', 'SP_FB')
    s.net(amp[1], '1', 'SP_OUT')
    s.net(amp[2], '5', 'SP_ACM')
    s.net(amp[2], '6', 'SP_UNUSED')
    s.net(amp[2], '7', 'SP_UNUSED')
    s.net(amp[3], '8', 'SP_12V')
    s.net(amp[3], '4', 'SP_ACM')
    res(s, 'R712', '10k', 452.12, 104.14, 'SP_FB', 'SP_ACM')
    res(s, 'R713', '8k2', 513.08, 104.14, 'SP_OUT', 'SP_RF')
    res(s, 'R714', '100R', 538.48, 76.2, 'SP_OUT', 'SP_AVI')
    rv = s.place('Device', 'R_Potentiometer_Trim', 'RV701', '5k 10.0V trim', 513.08, 127.0,
                 footprint='Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical')
    s.net(rv, 1, 'SP_RF')
    s.net(rv, 2, 'SP_FB')
    s.net(rv, 3, 'SP_FB')
    cap(s, 'C707', '100nF', 406.4, 165.1, 'SP_12V', 'SP_ACM')
    cap(s, 'C708', '10nF', 548.64, 101.6, 'SP_AVI', 'SP_ACM')
    for name in ('FWD', 'REV', 'AUX'):
        u, c, e = opto[name]
        s.net(u, c, 'SP_%s' % name)
        s.net(u, e, 'SP_DCM')

    s.box(304.8, 198.12, 571.5, 243.84, 'VFD-SIDE TEST POINTS - measure against ACM')
    add_test_points(s, (('TP701', 'SP_ACM', 'ACM'), ('TP702', 'SP_12V', '12V'),
                        ('TP703', 'SP_AVI', 'AVI')), 330.2, 228.6)
    s.box(12.7, 198.12, 292.1, 243.84, 'VFD TERMINAL - AVI ACM FWD REV AUX DCM, AS A1')
    j = s.place('Connector', 'Conn_01x06_Pin', 'J701', 'VFD', 76.2, 228.6,
                footprint=TERM % (6, 6))
    for pos, net in enumerate(('SP_AVI', 'SP_ACM', 'SP_FWD', 'SP_REV', 'SP_AUX', 'SP_DCM')):
        s.net(j, TOP_PIN(pos, 6), net)
    return s


# ---------------------------------------------------------- 08 comms --

def build_comms():
    """RS485 for Modbus VFDs, and the handwheel MCU.

    RS485: MAX3485 on 3.3 V, UART0, DE and /RE together on GP25 (grblHAL
    MODBUS_DIR_AUX). 120R termination on a solder jumper - fit it only at the
    end of the line. NUP2105L clamps A and B.

    Handwheel: an ATmega328P at 3.3 V, 8 MHz reads a standard MPG pendant -
    quadrature A/B, eight axis-select lines, x1/x10/x100 - and sends $J= jog
    commands to grblHAL over UART1 in MPG mode. The pendant's encoder runs on
    5 V (fused), so A and B come in through 4.7k with the MCU's clamp diodes
    taking the difference; the switch lines are contacts to GND.
    """
    s = sheet('08_comms')
    s.text('RS485 VFD PORT AND HANDWHEEL', 12.7, 16.51, 2.0)

    s.box(12.7, 35.56, 254.0, 152.4, 'RS485 - MODBUS RTU TO THE VFD (UART0)')
    x = s.place('Interface_UART', 'MAX3485', 'U801', 'MAX3485ESA', 88.9, 91.44,
                footprint=SOIC8)
    s.net(x, 1, 'RS485_RO')
    s.net(x, 2, 'RS485_DE')
    s.net(x, 3, 'RS485_DE')
    s.net(x, 4, 'RS485_DI')
    s.net(x, 5, 'GND')
    s.net(x, 6, 'RS485_A')
    s.net(x, 7, 'RS485_B')
    s.net(x, 8, '+3V3')
    cap(s, 'C801', '100nF', 30.48, 71.12, '+3V3', 'GND')
    # Receiver held idle with the RP2350 in reset; driver off (DE low).
    res(s, 'R801', '10k', 30.48, 91.44, '+3V3', 'RS485_RO')
    res(s, 'R802', '10k', 30.48, 111.76, 'RS485_DE', 'GND')
    jp = s.place('Jumper', 'SolderJumper_2_Open', 'JP801', 'TERM 120R', 157.48, 71.12,
                 footprint='Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm')
    s.net(jp, 1, 'RS485_A')
    s.net(jp, 2, 'RS485_T')
    res(s, 'R803', '120R', 195.58, 71.12, 'RS485_T', 'RS485_B')
    tv = s.place('Power_Protection', 'NUP2105L', 'D801', 'NUP2105L', 157.48, 119.38,
                 footprint=SOT23)
    s.net(tv, 1, 'RS485_A')
    s.net(tv, 2, 'RS485_B')
    s.net(tv, 3, 'GND')
    t = s.place('Connector', 'Conn_01x03_Pin', 'J801', 'RS485 A B GND', 223.52, 101.6,
                footprint=TERM % (3, 3))
    s.net(t, TOP_PIN(0, 3), 'RS485_A')
    s.net(t, TOP_PIN(1, 3), 'RS485_B')
    s.net(t, TOP_PIN(2, 3), 'GND')

    s.box(12.7, 165.1, 482.6, 381.0, 'HANDWHEEL MCU - ATmega328P, 3.3 V, 8 MHz, UART1 TO THE RP2350')
    m = s.place('MCU_Microchip_ATmega', 'ATmega328P-A', 'U802', 'ATmega328P-AU',
                101.6, 269.24, footprint='Package_QFP:TQFP-32_7x7mm_P0.8mm')
    by = {p['name']: p['num'] for p in m.pins}
    s.net(m, by['VCC'], '+3V3')
    s.net(m, by['GND'], 'GND')
    s.net(m, by['AVCC'], '+3V3')
    s.nc(m, by['AREF'])
    s.net(m, by['~{RESET}/PC6'], 'HW_RESET')
    s.net(m, by['XTAL1/PB6'], 'HW_XTAL1')
    s.net(m, by['XTAL2/PB7'], 'HW_XTAL2')
    # RP2350 UART1 TX (GP42) -> ATmega RXD; ATmega TXD -> GP43.
    s.net(m, by['PD0'], 'UART1_TX')
    s.net(m, by['PD1'], 'UART1_RX')
    HW_PINS = (('PD2', 'MPG_A'), ('PD3', 'MPG_B'),          # INT0 / INT1
               ('PC0', 'MPG_SEL_X'), ('PC1', 'MPG_SEL_Y'), ('PC2', 'MPG_SEL_Z'),
               ('PC3', 'MPG_SEL_A'), ('PC4', 'MPG_SEL_B'), ('PC5', 'MPG_SEL_C'),
               ('PD4', 'MPG_SEL_U'), ('PD5', 'MPG_SEL_V'),
               ('PD6', 'MPG_X1'), ('PD7', 'MPG_X10'), ('PB0', 'MPG_X100'),
               ('PB1', 'HW_LED'),
               ('PB3', 'HW_MOSI'), ('PB4', 'HW_MISO'), ('PB5', 'HW_SCK'))
    for nm, net in HW_PINS:
        s.net(m, by[nm], net)
    s.nc_rest(m)
    for i in range(3):
        cap(s, 'C%d' % (802 + i), '100nF', 30.48 + i * 22.86, 355.6, '+3V3', 'GND')
    res(s, 'R804', '10k', 30.48, 195.58, '+3V3', 'HW_RESET')
    cap(s, 'C805', '10nF', 55.88, 195.58, 'HW_RESET', 'GND')
    xt = s.place('Device', 'Crystal_GND24', 'Y801', '8MHz', 172.72, 355.6, footprint=XTAL)
    s.net(xt, 3, 'HW_XTAL1')
    s.net(xt, 1, 'HW_XTAL2')
    s.net(xt, 2, 'GND')
    s.net(xt, 4, 'GND')
    cap(s, 'C806', '22pF', 139.7, 368.3, 'HW_XTAL1', 'GND')
    cap(s, 'C807', '22pF', 205.74, 368.3, 'HW_XTAL2', 'GND')
    isp = s.place('Connector', 'AVR-ISP-6', 'J802', 'HW ICSP', 205.74, 195.58,
                  footprint='Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical')
    for pin, net in (('1', 'HW_MISO'), ('2', '+3V3'), ('3', 'HW_SCK'), ('4', 'HW_MOSI'),
                     ('5', 'HW_RESET'), ('6', 'GND')):
        s.net(isp, pin, net)
    res(s, 'R805', '1k', 256.54, 220.98, 'HW_LED', 'HW_LED_A')
    led = s.place('Device', 'LED', 'D802', 'MPG', 284.48, 220.98, footprint=LED0603, rot=180)
    s.net(led, 2, 'HW_LED_A')
    s.net(led, 1, 'GND')

    # Pendant connector: 2x8 IDC. 1 +5V, 2 GND, 3 A, 4 B, then the switches.
    pend = s.place('Connector_Generic', 'Conn_02x08_Odd_Even', 'J803', 'MPG PENDANT',
                   419.1, 294.64, footprint='Connector_IDC:IDC-Header_2x08_P2.54mm_Vertical')
    pf = s.place('Device', 'Polyfuse', 'F801', '200mA hold PTC 1206', 360.68, 195.58,
                 footprint='Fuse:Fuse_1206_3216Metric')
    s.net(pf, 1, '+5V')
    s.net(pf, 2, 'MPG_5V')
    s.net(pend, 1, 'MPG_5V')
    s.net(pend, 2, 'GND')
    s.net(pend, 3, 'MPG_A_RAW')
    s.net(pend, 4, 'MPG_B_RAW')
    sw = ['MPG_SEL_%s' % a for a in AXES] + ['MPG_X1', 'MPG_X10', 'MPG_X100']
    for i, net in enumerate(sw):
        s.net(pend, 5 + i, net)
    s.net(pend, 16, 'GND')
    for i, ch in enumerate(('A', 'B')):
        res(s, 'R%d' % (806 + i), '4.7k', 309.88, 238.76 + i * 17.78,
            'MPG_%s_RAW' % ch, 'MPG_%s' % ch)
        cap(s, 'C%d' % (808 + i), '1nF', 340.36, 238.76 + i * 17.78, 'MPG_%s' % ch, 'GND')
    # Encoders are usually open collector: pull-up on the pendant side to 5 V.
    for i, ch in enumerate(('A', 'B')):
        res(s, 'R%d' % (808 + i), '4.7k', 276.86, 271.78 + i * 17.78,
            'MPG_%s_RAW' % ch, 'MPG_5V')
    # Switch lines use the ATmega's internal pull-ups; 1 nF each against the
    # cable picking up the motors.
    for i, net in enumerate(sw):
        cap(s, 'C%d' % (811 + i), '1nF', 256.54 + (i % 6) * 20.32,
            320.04 + (i // 6) * 20.32, net, 'GND')
    return s


def build_root(children):
    body = []
    for i, (key, (suid, title)) in enumerate(SHEETS.items()):
        if key not in children:
            continue
        x = 25.4 + (i % 2) * 152.4
        y = 50.8 + (i // 2) * 25.4
        body.append(
            '(sheet (at %s %s) (size 127 15) (stroke (width 0.1524) (type default))'
            ' (fill (color 0 0 0 0)) (uuid "%s")'
            '(property "Sheetname" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) (justify left)))'
            '(property "Sheetfile" "%s.kicad_sch" (at %s %s 0) (effects (font (size 1.016 1.016)) (justify left)))'
            '(instances (project "%s" (path "/%s" (page "%d")))))'
            % (fmt(x), fmt(y), suid, title, fmt(x), fmt(y - 1.27),
               key, fmt(x), fmt(y + 16.51), PROJECT, ROOT_UUID, i + 2))
    head = ('(kicad_sch (version 20231120) (generator "eeschema") (uuid "%s")'
            ' (paper "A4") (title_block (title "MACH3-SIMPLE-ETH")'
            ' (rev "%s"))(lib_symbols)' % (ROOT_UUID, REV))
    notes = (
        '(text "MACH3-SIMPLE-ETH  -  RP2350B + grblHAL, 8 axes, W5500 Ethernet" (at 12.7 12.7 0)'
        ' (effects (font (size 2.54 2.54)) (justify left)) (uuid "%s"))'
        '(text "A1 with the LPT ports replaced: relays, inputs and isolated VFD port kept." (at 12.7 20.32 0)'
        ' (effects (font (size 1.524 1.524)) (justify left)) (uuid "%s"))'
        '(text "ETH-0: NOT BUILT, NOT TESTED." (at 12.7 27.94 0)'
        ' (effects (font (size 1.524 1.524)) (justify left)) (uuid "%s"))'
        % (uid(), uid(), uid()))
    return head + notes + ''.join(body) + '(sheet_instances (path "/" (page "1")))) '


def main():
    os.makedirs(HW, exist_ok=True)
    built, clashes = {}, []
    for fn in (build_power, build_mcu, build_ethernet, build_outputs, build_inputs,
               build_relays, build_spindle, build_comms):
        s = fn()
        key = s.filename[:-len('.kicad_sch')]
        s.write(HW)
        built[key] = s
        print('wrote %-22s %3d symbols%s'
              % (s.filename, len(s.symbols),
                 '' if not s._clashes else '  UNRESOLVED STUB CLASH: ' + ', '.join(s._clashes)))
        clashes.extend('%s: %s' % (s.filename, c) for c in s._clashes)
    with open(os.path.join(HW, PROJECT + '.kicad_sch'), 'w', encoding='utf-8',
              newline='') as f:
        f.write(build_root(built))
    print('wrote', PROJECT + '.kicad_sch')
    if clashes:
        print('\nFATAL: %d stub(s) could not be placed without touching another net.'
              % len(clashes))
        for c in clashes:
            print('   ' + c)
        return 1
    pro = os.path.join(HW, PROJECT + '.kicad_pro')
    if not os.path.exists(pro):
        with open(pro, 'w', encoding='utf-8', newline='') as f:
            f.write('{\n  "board": {"design_settings": {}},\n'
                    '  "meta": {"filename": "%s.kicad_pro", "version": 3},\n'
                    '  "schematic": {},\n  "sheets": [],\n  "text_variables": {}\n}\n'
                    % PROJECT)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
