#!/usr/bin/env python3
"""MACH3-SIMPLE: a copy of the board in service, with the extras taken out.

This is deliberately the smaller, plainer sibling of MACH3_BOB_A0. It matches
the board currently running the machine - same connectors in the same places,
same functions, same 5 V single-ended outputs - so the existing wiring loom and
the existing Mach3 profile carry over unchanged.

Two decisions were taken on 2026-09-21 and they shape everything here:

* **The outputs are not isolated**, exactly as on the board in service. A
  74HC245 buffers each LPT pin and drives the axis terminal directly, sharing
  ground with the PC. This is the cheaper, smaller arrangement and it is what
  the machine already runs on.
* **5 V and 24 V both come from outside**, on their own terminals, again as on
  the board in service. There is no buck and no isolated module.

What that costs, stated plainly so nobody has to rediscover it: the pulse and
direction outputs are the ones that kept failing on the board in service, and a
buffer sharing ground with the PC is the arrangement they were failing in. The
fix for that - an optocoupler per channel behind the driver - lives in
MACH3_BOB_A0 and can be brought over later. Nothing here forecloses it.

What IS carried over from that design, because it costs almost nothing:

* an anti-parallel diode across every optocoupler LED. A PC847 LED is rated 6 V
  reverse and sees more than that from a sensor cable run beside a motor lead;
  this is the single most likely reason optocouplers keep dying.
* a bypass capacitor on every IC supply pin.
* the optocoupler collector and emitter resolved from the symbol geometry
  rather than from the order the pins are listed in, which is how twenty
  channels came out reversed on the sister project.
* a crystal and an ICSP header on the MCU (Y1, J60), so the firmware can be
  loaded and reloaded on the board and the UART keeps time.

Taken out, to be added back later: RS-422 line drivers, the charge pump, the
0-10 V spindle output, and on-board THC pulse generation. THC arrives here as
two plain inputs from an external THC box, as it does on the board in service.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schgen import Sheet, fmt, uid                           # noqa: E402

PROJECT = 'MACH3SIMPLE'
HW = 'hardware'
ROOT_UUID = '7b2c1a40-0001-4000-8000-000000000001'

SHEETS = {
    '01_power':   ('7b2c1a40-0002-4000-8000-000000000001',
                   'Power - 5 V and 24 V in'),
    '02_outputs': ('7b2c1a40-0002-4000-8000-000000000002',
                   'LPT port 1 - 6 axes, buffered 5 V out'),
    '03_inputs':  ('7b2c1a40-0002-4000-8000-000000000003',
                   'Inputs - home, E-stop, THC, handwheel'),
    '04_relays':  ('7b2c1a40-0002-4000-8000-000000000004',
                   'RS232, MCU and six relays'),
}

# 5.08 mm, measured off the drawing of the board in service: the pad ladders of
# T2, T3, T12, T13 and T15 all step 5.08 mm. An earlier version used 3.5 mm
# blocks to squeeze six terminals into a board believed to be 150 mm wide. The
# board turned out to be 168 mm and the narrow blocks were never reverted - they
# were solving a problem that did not exist, and they take thinner wire.
TERM = ('TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-%d'
        '_1x%02d_P5.00mm_Horizontal')
R0603 = 'Resistor_SMD:R_0603_1608Metric'
R1206 = 'Resistor_SMD:R_1206_3216Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
LED0603 = 'LED_SMD:LED_0603_1608Metric'
SOIC8 = 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
SOIC16 = 'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm'
SOIC20 = 'Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm'
SOD123 = 'Diode_SMD:D_SOD-123'
DSUB25 = ('Connector_Dsub:DSUB-25_Socket_Horizontal_P2.77x2.84mm'
          '_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm')

AXES = ['X', 'Y', 'Z', 'A', 'B', 'C']

# Straight from the table printed on the board in service, so the existing
# Mach3 profile still applies. Pins 1, 14 and 17 are inverted by the parallel
# port itself; on this board they carry DIR, which is a static level Mach3's
# per-pin Active Low setting handles cleanly.
P1_OUT = [('1', 'X_PUL'), ('2', 'X_DIR'), ('3', 'Y_PUL'), ('4', 'Y_DIR'),
          ('5', 'Z_PUL'), ('6', 'Z_DIR'), ('7', 'A_PUL'), ('8', 'A_DIR'),
          ('9', 'B_PUL'), ('14', 'B_DIR'), ('17', 'C_PUL'), ('16', 'C_DIR')]
P1_IN = [('10', 'X_HOME'), ('11', 'Y_HOME'), ('12', 'Z_HOME'),
         ('13', 'A_HOME'), ('15', 'C_HOME')]
P2_IN = [('15', 'ESTOP'), ('10', 'THC_UP'), ('11', 'THC_DOWN'),
         ('12', 'MPG_A'), ('13', 'MPG_B')]

# 24 V sensor channels, in the order they sit along the top edge.
SENSORS = [('ESTOP', 'E-stop'), ('C_HOME', 'C home'), ('A_HOME', 'A home'),
           ('Z_HOME', 'Z home'), ('Y_HOME', 'Y home'), ('X_HOME', 'X home')]
# No THC terminal. The handwheel feeds either the jog pins or the THC pins,
# and an analog switch picks which - the trick the board in service uses, so one
# encoder does both jobs and Mach3 sees THC up/down as ordinary inputs.
RELAYS = 'ABCDEF'


def sheet(key):
    u, title = SHEETS[key]
    return Sheet(key + '.kicad_sch', title, PROJECT, ROOT_UUID, u)


def opto_pins(u):
    """(anode, cathode, collector, emitter) from the symbol's geometry.

    Never from the order the pins are listed in. PC847 unit 1 lists its pins
    1, 2, 15, 16, so reading them positionally makes pin 15 the collector when
    pin 15 is the emitter - which reverse-biases every phototransistor on the
    board and was exactly what happened on the sister project.
    """
    led = sorted((q for q in u.pins if int(q['num']) <= 8), key=lambda q: -q['y'])
    tr = sorted((q for q in u.pins if int(q['num']) > 8), key=lambda q: -q['y'])
    if len(led) != 2 or len(tr) != 2:
        raise ValueError('%s: expected 2 LED and 2 transistor pins' % u.ref)
    return led[0]['num'], led[1]['num'], tr[0]['num'], tr[1]['num']


def db25(s, ref, x, y, label):
    j = s.place('Connector', 'DB25_Socket_MountingHoles', ref, label, x, y,
                footprint=DSUB25)
    for g in range(18, 26):
        s.net(j, str(g), 'GND')
    s.net(j, 'SH', 'CHASSIS')
    return j


# ----------------------------------------------------------- 01 power --

def build_power():
    """Two supplies in, one ground. That is the whole sheet.

    5 V and 24 V share GND because the outputs are not isolated, so there is
    nothing to keep apart. The optocouplers on the input side are still worth
    their place: they shift 24 V down to logic level and they keep sensor cable
    noise out of the parallel port, which is most of what they were doing
    before.
    """
    s = sheet('01_power')
    s.text('POWER. Two supplies from the cabinet, exactly as the board in service.', 12.7, 16.51, 2.0)
    s.text('One common ground: the outputs are not isolated, so there is nothing to', 12.7, 22.86)
    s.text('keep apart. See the header of build_project.py for what that costs.', 12.7, 27.94)

    s.box(12.7, 40.64, 190.5, 111.76, '5 V LOGIC SUPPLY')
    s.text('Feeds the buffers, the optocoupler LEDs on the PC side, the MCU and', 15.24, 48.26)
    s.text('the RS232 transceiver. F1 protects the board, not the supply.', 15.24, 53.34)
    j5 = s.place('Connector', 'Conn_01x02_Pin', 'J3', '5V IN', 25.4, 76.2,
                 footprint=TERM % (2, 2))
    f5 = s.place('Device', 'Fuse', 'F1', '1A slow 1206', 55.88, 76.2,
                 footprint='Fuse:Fuse_1206_3216Metric', rot=90)
    d5 = s.place('Device', 'D_Schottky', 'D1', 'SS34 reverse', 88.9, 76.2,
                 footprint='Diode_SMD:D_SMA', rot=180)
    c5 = s.place('Device', 'C_Polarized', 'C1', '100uF 16V', 127.0, 88.9,
                 footprint='Capacitor_SMD:CP_Elec_6.3x7.7')
    s.link(j5, 1, f5, 1, 'VIN5')
    s.link(f5, 2, d5, 2, 'VIN5F')
    s.link(d5, 1, c5, 1, '+5V', via_y=76.2)
    s.net(c5, 2, 'GND')
    s.net(j5, 2, 'GND')

    s.box(203.2, 40.64, 381.0, 111.76, '24 V SENSOR AND RELAY SUPPLY')
    s.text('Feeds the sensor loops and the relay coils. Nothing on this board', 205.74, 48.26)
    s.text('switches mains; the relay contacts drive 24 V coils only.', 205.74, 53.34)
    j24 = s.place('Connector', 'Conn_01x02_Pin', 'J4', '24V IN', 215.9, 76.2,
                  footprint=TERM % (2, 2))
    f24 = s.place('Device', 'Fuse', 'F2', '1A slow 1206', 246.38, 76.2,
                  footprint='Fuse:Fuse_1206_3216Metric', rot=90)
    d24 = s.place('Device', 'D_Schottky', 'D2', 'SS34 reverse', 279.4, 76.2,
                  footprint='Diode_SMD:D_SMA', rot=180)
    tvs = s.place('Device', 'D_TVS', 'D3', 'SMAJ26A', 309.88, 88.9,
                  footprint='Diode_SMD:D_SMA', rot=270)
    c24 = s.place('Device', 'C_Polarized', 'C2', '100uF 50V', 345.44, 88.9,
                  footprint='Capacitor_SMD:CP_Elec_6.3x7.7')
    s.link(j24, 1, f24, 1, 'VIN24')
    s.link(f24, 2, d24, 2, 'VIN24F')
    s.link(d24, 1, tvs, 1, 'V24', via_y=76.2)
    s.link(tvs, 1, c24, 1, 'V24')
    s.link(tvs, 2, c24, 2, 'GND')
    s.net(j24, 2, 'GND')

    s.box(12.7, 124.46, 190.5, 177.8, 'RAIL INDICATORS')
    s.text('See at a glance which supply is missing. 10k on 24 V, not 4k7:', 15.24, 132.08)
    s.text('4k7 would be (24-2)^2/4700 = 103 mW in a 100 mW 0603.', 15.24, 137.16)
    for i, (rail, val) in enumerate((('+5V', '1k'), ('V24', '10k'))):
        y = 152.4 + i * 15.24
        r = s.place('Device', 'R', 'R%d' % (1 + i), val, 55.88, y,
                    footprint=R0603, rot=90)
        led = s.place('Device', 'LED', 'D%d' % (10 + i), rail, 106.68, y,
                      footprint=LED0603, rot=180)
        s.net(r, 1, rail)
        s.link(r, 2, led, 2)
        s.net(led, 1, 'GND')

    s.box(203.2, 124.46, 381.0, 177.8, 'SHELL AND POWER FLAGS')
    s.text('The two D-sub shells share CHASSIS. C3 returns high-frequency screen', 205.74, 132.08)
    s.text('current without a DC loop; fit R3 only if measurement says otherwise.', 205.74, 137.16)
    csh = s.place('Device', 'C', 'C3', '1nF 2kV Y5P', 228.6, 156.21,
                  footprint='Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm')
    s.net(csh, 1, 'CHASSIS')
    s.net(csh, 2, 'GND')
    rsh = s.place('Device', 'R', 'R3', '0R link - DO NOT FIT', 279.4, 156.21,
                  footprint=R1206, rot=90)
    # Marked Do Not Populate, not just named so: the value is only read by a
    # person, and an assembly house works from the placement file, which
    # leaves DNP parts out.
    rsh.dnp = 'yes'
    s.net(rsh, 1, 'CHASSIS')
    s.net(rsh, 2, 'GND')
    for i, (net, x) in enumerate((('VIN5', 320.04), ('+5V', 341.63),
                                  ('VIN24', 363.22), ('V24', 384.81),
                                  ('GND', 406.4))):
        fl = s.place('power', 'PWR_FLAG', '#FLG%d' % (i + 1), 'PWR_FLAG',
                     x, 168.91)
        fx, fy = fl.at(1)
        s.wire(fx, fy, fx, fy + 6.35)
        s.label(net, fx, fy + 6.35, 270)
        fl.used.add('1')

    s.box(12.7, 190.5, 190.5, 228.6, 'MOUNTING')
    for i in range(4):
        s.place('Mechanical', 'MountingHole', 'H%d' % (i + 1), 'M3',
                30.48 + i * 38.1, 213.36,
                footprint='MountingHole:MountingHole_3.2mm_M3')
    return s


# --------------------------------------------------------- 02 outputs --

def build_outputs():
    """Twelve buffered outputs and the six axis terminals.

    A 74HC245 per eight channels, direction pinned to A->B and the enable tied
    low so the outputs are always on. The buffer exists to take the drive off
    the parallel port pin, which can source only a few milliamps, and to give
    the cable a low-impedance 5 V source instead of a PC chipset pin.
    """
    s = sheet('02_outputs')
    s.text('LPT PORT 1 - MOTION. Pin numbers are the ones printed on the board in', 12.7, 16.51, 2.0)
    s.text('service, so the existing Mach3 profile carries over unchanged.', 12.7, 22.86)
    s.text('NOT ISOLATED: the axis terminals share ground with the PC. That is the', 12.7, 30.48)
    s.text('arrangement on the board in service and the one chosen for this copy.', 12.7, 35.56)

    j = db25(s, 'J1', 40.64, 152.4, 'LPT PORT 1')

    s.box(114.3, 45.72, 330.2, 190.5, 'BUFFERS')
    bufs = {}
    for k in range(2):
        u = s.place('74xx', '74HC245', 'U%d' % (1 + k), '74HC245',
                    165.1 + k * 101.6, 76.2, footprint=SOIC20)
        s.net(u, '20', '+5V')
        s.net(u, '10', 'GND')
        s.net(u, '1', '+5V')        # A->B high: A side is the input
        s.net(u, '19', 'GND')       # CE low: outputs always enabled
        bufs[k] = u

    for i, (pin, net) in enumerate(P1_OUT):
        u = bufs[i // 8]
        ch = i % 8
        s.net(u, str(2 + ch), net + '_IN')      # A side, from the LPT
        s.net(u, str(18 - ch), net)             # B side, to the terminal
        s.net(j, pin, net + '_IN')

    # The twelve used inputs need holding down too, and for the reason the
    # spare-input comment below gives. It was written for inputs with nothing
    # connected; an input wired to the LPT is in exactly that state whenever
    # the PC is off or the cable is out, and a floating STEP line is a buffer
    # that can toggle on noise and step a motor with no computer attached.
    #
    # The board in service has a resistor network beside each buffer for this.
    # Its owner found them missing here; no check did. tools/check_coverage.py
    # now looks for any net that reaches a chip input with nothing to hold it.
    #
    # 10k to ground. A step is an edge, so either rail is safe against a
    # spurious step - what matters is that the line does not float - and 10k is
    # a negligible load on an LPT pin that is actually driving. Pin order read
    # off the R_Pack04 symbol: resistor n runs from pin n to pin 9 - n.
    ins = [net + '_IN' for _pin, net in P1_OUT]
    for k in range(3):
        rn = s.place('Device', 'R_Pack04', 'RN%d' % (1 + k), '4x10k pull-down',
                     152.4 + k * 50.8, 139.7,
                     footprint='Resistor_SMD:R_Array_Convex_4x0603')
        for m in range(4):
            s.net(rn, str(1 + m), ins[4 * k + m])
            s.net(rn, str(8 - m), 'GND')

    # Twelve outputs out of sixteen buffers. Tie the spare inputs down rather
    # than leaving them floating - a CMOS input with nothing on it drifts to the
    # threshold and the gate sits half-on, drawing current and making noise.
    # Their outputs are genuine outputs, so those are no-connects, not grounds.
    # A 74HC245's A pins are bidirectional, and grounding one outright means a
    # dead short if the direction pin is ever wrong or has not settled at
    # power-up. One 10k to ground holds them low without that risk, and it also
    # stops ERC objecting to a tri-state pin wired to a power pin.
    # A 100 nF on each buffer's supply pin, as on the board in service. Twelve
    # outputs switching together into cable is the biggest step in supply
    # current on this board; build_pcb.py puts each against pin 20.
    for k, ref in enumerate(('C40', 'C41')):
        c = s.place('Device', 'C', ref, '100nF', 190.5 + k * 50.8, 165.1,
                    footprint=C0603)
        s.net(c, 1, '+5V')
        s.net(c, 2, 'GND')

    rsp = s.place('Device', 'R', 'R5', '10k spare pull-down', 304.8, 165.1,
                  footprint=R0603, rot=90)
    s.net(rsp, 1, 'SPARE_IN')
    s.net(rsp, 2, 'GND')
    for k, u in bufs.items():
        for ch in range(8):
            if str(2 + ch) not in u.used:
                s.net(u, str(2 + ch), 'SPARE_IN')
                s.nc(u, str(18 - ch))

    for pin, net in P1_IN:
        s.net(j, pin, net + '_PC')
    s.nc_rest(j)

    s.box(12.7, 203.2, 330.2, 266.7, 'AXIS TERMINALS - PULSE / GND / DIR')
    s.text('5 V single-ended, as the board in service. To drive a differential', 15.24, 210.82)
    s.text('servo input, tie its /PULSE and /DIR to the G pin of the same terminal.', 15.24, 215.9)
    for i, a in enumerate(AXES):
        t = s.place('Connector', 'Conn_01x03_Pin', 'J%d' % (10 + i),
                    '%s axis' % a, 38.1 + i * 50.8, 243.84,
                    footprint=TERM % (3, 3))
        s.net(t, 1, '%s_PUL' % a)
        s.net(t, 2, 'GND')
        s.net(t, 3, '%s_DIR' % a)
    return s


# ---------------------------------------------------------- 03 inputs --

def build_inputs():
    """Six 24 V sensor channels, two THC channels, and the handwheel.

    The optocouplers stay even though both sides share a ground. They are not
    here for galvanic isolation on this board - they are here to turn a 24 V
    sensor loop into a logic level and to stop what the sensor cable picks up
    from arriving at the parallel port. That is most of what they were doing
    before, and it is worth the four packages.
    """
    s = sheet('03_inputs')
    s.text('INPUTS. 24 V sensors on optocouplers, handwheel straight through.', 12.7, 16.51, 2.0)
    s.text('EVERY optocoupler LED gets an anti-parallel diode. A PC847 LED is rated', 12.7, 24.13)
    s.text('6 V reverse and a sensor cable beside a motor lead delivers far more.', 12.7, 29.21)
    s.text('That is the most likely reason optocouplers keep dying, and the fix is', 12.7, 34.29)
    s.text('one diode each.', 12.7, 39.37)

    j2 = db25(s, 'J2', 40.64, 152.4, 'LPT PORT 2')

    s.box(114.3, 48.26, 396.24, 210.82, '24 V INPUT CHANNELS')
    s.text('4k7 in 1206: (24-1.2)^2/4700 = 0.11 W, which a 0603 cannot hold.', 116.84, 55.88)
    chans = SENSORS
    for i, (net, label) in enumerate(chans):
        pkg, unit = divmod(i, 4)
        y = 71.12 + i * 17.78
        u = s.place('Isolator', 'PC847', 'U%d' % (10 + pkg), 'PC847',
                    228.6, y, footprint=SOIC16, unit=unit + 1)
        a, k, c, e = opto_pins(u)

        r = s.place('Device', 'R', 'R%d' % (10 + i), '4k7 1206', 165.1, y,
                    footprint=R1206)
        s.net(r, 1, net + '_F')
        s.net(r, 2, net + '_LED')
        s.wire(*(r.at(2) + u.at(a)))
        u.used.add(a)
        s.net(u, k, 'GND')
        s.net(u, e, 'GND')
        s.net(u, c, net + '_PC')
        pu = s.place('Device', 'R', 'R%d' % (30 + i), '10k', 292.1, y,
                     footprint=R0603)
        s.net(pu, 1, net + '_PC')
        s.net(pu, 2, '+5V')
        cf = s.place('Device', 'C', 'C%d' % (10 + i), '10nF filter', 342.9, y,
                     footprint=C0603)
        s.net(cf, 1, net + '_PC')
        s.net(cf, 2, 'GND')

    # Six channels fill one quad and half of the second. The spare half is
    # placed and no-connected rather than left off the sheet, so nobody has to
    # wonder later whether it was forgotten.
    for unit in (3, 4):
        sp = s.place('Isolator', 'PC847', 'U11', 'PC847', 381.0,
                     71.12 + unit * 22.86, footprint=SOIC16, unit=unit)
        for n in [q['num'] for q in sp.pins]:
            s.nc(sp, n)

    s.box(114.3, 223.52, 396.24, 281.94, 'HANDWHEEL - 5 V, STRAIGHT THROUGH')
    s.text('The MPG runs at 5 V and shares ground with the port, so it needs no', 116.84, 231.14)
    s.text('optocoupler - only a series resistor and a pull-up, because most', 116.84, 236.22)
    s.text('handwheels drive their outputs open-collector.', 116.84, 241.3)
    jm = s.place('Connector', 'Conn_01x04_Pin', 'J30', 'MPG handwheel',
                 149.86, 262.89, footprint=TERM % (4, 4))
    s.net(jm, 1, '+5V')
    s.net(jm, 2, 'GND')
    for i, ch in enumerate(('A', 'B')):
        s.net(jm, 3 + i, 'MPG_%s_RAW' % ch)
        r = s.place('Device', 'R', 'R%d' % (40 + i), '330R',
                    228.6 + i * 76.2, 262.89, footprint=R0603)
        s.net(r, 1, 'MPG_%s_RAW' % ch)
        s.net(r, 2, 'MPG_%s_PC' % ch)
        pu = s.place('Device', 'R', 'R%d' % (42 + i), '4k7',
                     266.7 + i * 76.2, 262.89, footprint=R0603)
        s.net(pu, 1, 'MPG_%s_PC' % ch)
        s.net(pu, 2, '+5V')

    s.box(114.3, 294.64, 396.24, 375.92,
          'HANDWHEEL ROUTING - JOG OR THC, CHOSEN BY SendSerial')
    s.text('One encoder, two jobs. U3 sends MPG A and B either to port 2 pins 12', 116.84, 302.26)
    s.text('and 13, where Mach3 reads them as the handwheel, or to pins 10 and 11,', 116.84, 307.34)
    s.text('where it reads them as THC up and down. The MCU picks, on SendSerial', 116.84, 312.42)
    s.text("'T' for THC and 't' for jog, so it is one more macro alongside the relays.", 116.84, 317.5)
    s.text('The four LPT pins are pulled up, so whichever pair is not selected sits', 116.84, 325.12)
    s.text('high and inactive rather than floating.', 116.84, 330.2)

    sw = s.place('4xxx', '4053', 'U3', '74HC4053', 228.6, 358.14,
                 footprint=SOIC16)
    s.net(sw, '16', '+5V')
    s.net(sw, '8', 'GND')
    s.net(sw, '7', 'GND')            # VEE: single supply, so 0 V
    s.net(sw, '6', 'GND')            # Inhibit low = switches live
    s.net(sw, '11', 'MPG_SEL')       # A and B selects tied together
    s.net(sw, '10', 'MPG_SEL')
    s.net(sw, '9', 'GND')            # C unused, its switch parked
    s.net(sw, '14', 'MPG_A_PC')      # X common: the conditioned A signal
    s.net(sw, '12', 'MPG_A_JOG')     # X0 -> port 2 pin 12
    s.net(sw, '13', 'MPG_A_THC')     # X1 -> port 2 pin 10
    s.net(sw, '15', 'MPG_B_PC')      # Y common
    s.net(sw, '2', 'MPG_B_JOG')      # Y0 -> port 2 pin 13
    s.net(sw, '1', 'MPG_B_THC')      # Y1 -> port 2 pin 11
    s.net(sw, '4', 'GND')            # Z switch unused
    s.nc(sw, '3')
    s.nc(sw, '5')

    for i, (net, x) in enumerate((('MPG_A_THC', 279.4), ('MPG_B_THC', 317.5),
                                  ('MPG_A_JOG', 355.6), ('MPG_B_JOG', 393.7))):
        pu = s.place('Device', 'R', 'R%d' % (44 + i), '10k', x, 358.14,
                     footprint=R0603)
        s.net(pu, 1, net)
        s.net(pu, 2, '+5V')

    # The select line is driven by an MCU pin, and an MCU pin is an input -
    # floating - all through reset, at every power-up, and for good on a chip
    # that has not been programmed. Left like that the switch would hand the
    # handwheel to the jog pins or the THC pins at random and could flick
    # between them on noise, which Mach3 would read as THC up and down. Held
    # low, it comes up on jog - the same state SendSerial 't' selects.
    sel = s.place('Device', 'R', 'R52', '10k MPG_SEL pull-down', 190.5, 358.14,
                  footprint=R0603)
    s.net(sel, 1, 'MPG_SEL')
    s.net(sel, 2, 'GND')

    # Port 2's five inputs: E-stop from its optocoupler, the other four from
    # the switch.
    s.net(j2, '15', 'ESTOP_PC')
    s.net(j2, '10', 'MPG_A_THC')
    s.net(j2, '11', 'MPG_B_THC')
    s.net(j2, '12', 'MPG_A_JOG')
    s.net(j2, '13', 'MPG_B_JOG')
    s.nc_rest(j2)

    s.box(12.7, 294.64, 396.24, 332.74, 'EMG & HOME  -  ONE POSITION PER SIGNAL')
    s.text('One six-way block, labelled EMG C A Z Y X as on the board in service.', 15.24, 302.26)
    s.text('The sensors take their +24 and 0 V from the 24 V terminal, not from a', 15.24, 307.34)
    s.text('pin each. PNP (sourcing) sensors: an NPN will not drive these as drawn.', 15.24, 312.42)
    t = s.place('Connector', 'Conn_01x06_Pin', 'J20', 'EMG C A Z Y X',
                76.2, 320.04, footprint=TERM % (6, 6))
    for i, (net, _label) in enumerate(SENSORS):
        s.net(t, 1 + i, net + '_F')
    return s


# ---------------------------------------------------------- 04 relays --

def build_relays():
    """RS232, the MCU and six relays - the part that stays exactly as it was.

    SendSerial("A").."F" turns a relay on and "a".."f" turns it off, the same
    protocol the board in service uses, so existing Mach3 macros keep working.
    RS232 comes in on a 3-pin terminal as it does there, not a DE9.
    """
    s = sheet('04_relays')
    s.text('RS232 RELAY BANK. SendSerial("A").."F" on, "a".."f" off - the same', 12.7, 16.51, 2.0)
    s.text('protocol as the board in service, so existing macros keep working.', 12.7, 22.86)

    s.box(12.7, 35.56, 215.9, 152.4, 'RS232 AND MCU')
    s.text('The ATmega arrives blank: program it through J60 with a USBasp', 15.24, 43.18)
    s.text('(firmware/build.sh flash), which also sets the fuses for the 16 MHz', 15.24, 48.26)
    s.text('crystal Y1: low FF, high D9, extended FD. The factory fuses select the', 15.24, 53.34)
    s.text('internal RC, which is trimmed only to 10 percent. Serial is 9600 8N1.', 15.24, 58.42)

    jr = s.place('Connector', 'Conn_01x03_Pin', 'J50', 'RS232 RX TX GND',
                 35.56, 88.9, footprint=TERM % (3, 3))
    s.net(jr, 1, 'RS232_RX')
    s.net(jr, 2, 'RS232_TX')
    s.net(jr, 3, 'GND')

    m = s.place('Interface_UART', 'MAX3232', 'U20', 'MAX3232', 104.14, 88.9,
                footprint=SOIC16)
    s.net(m, '16', '+5V')
    s.net(m, '15', 'GND')
    s.net(m, '13', 'RS232_RX')
    s.net(m, '12', 'MCU_RX')
    s.net(m, '11', 'MCU_TX')
    s.net(m, '14', 'RS232_TX')
    s.net(m, '10', 'GND')
    s.net(m, '8', 'GND')
    s.nc(m, '9')
    s.nc(m, '7')
    for pin, net in (('1', 'C1P'), ('3', 'C1N'), ('4', 'C2P'), ('5', 'C2N'),
                     ('2', 'VSP'), ('6', 'VSN')):
        s.net(m, pin, net)
    s.nc_rest(m)
    for ref, a, b, x in (('C20', 'C1P', 'C1N', 139.7), ('C21', 'C2P', 'C2N', 177.8),
                         ('C22', 'VSP', '+5V', 139.7), ('C23', 'VSN', 'GND', 177.8)):
        y = 114.3 if ref in ('C20', 'C21') else 139.7
        c = s.place('Device', 'C', ref, '100nF', x, y, footprint=C0603)
        s.net(c, 1, a)
        s.net(c, 2, b)

    mcu = s.place('MCU_Microchip_ATmega', 'ATmega328P-A', 'U21', 'ATmega328P-AU',
                  76.2, 190.5, footprint='Package_QFP:TQFP-32_7x7mm_P0.8mm')
    by = {p['name']: p['num'] for p in mcu.pins}
    s.net(mcu, by['VCC'], '+5V')
    s.net(mcu, by['GND'], 'GND')
    if 'AVCC' in by:
        s.net(mcu, by['AVCC'], '+5V')
    for nm in ('ADC6', 'ADC7'):
        if nm in by:
            s.net(mcu, by[nm], 'GND')
    # AREF is left open. It had been tied to ground when its 100 nF capacitor
    # was taken off, and that is not the same as removing a part: selecting
    # AVCC or the 1.1 V bandgap as the ADC reference closes an internal switch
    # onto this pin, and with the pin on ground that switch shorts the
    # reference. Arduino's analogRead selects AVCC by default. The datasheet
    # says an externally driven AREF rules out the internal references; open,
    # it rules out nothing.
    if 'AREF' in by:
        s.nc(mcu, by['AREF'])

    # One 100 nF per supply pin - pins 4 and 6 (VCC) and 18 (AVCC). These were
    # offered once as extras and declined, and put back when the drawing of the
    # board in service turned out to have four capacitors round its MCU. With
    # one ground and six relay coils switching on it, they are what keeps this
    # chip's supply clean. The schematic cannot say which capacitor serves which
    # pin - they are all +5V to GND - so build_pcb.py places each against its
    # own pin; see PIN_CAPS there.
    for k, ref in enumerate(('C30', 'C31', 'C32')):
        c = s.place('Device', 'C', ref, '100nF', 25.4 + k * 12.7, 241.3,
                    footprint=C0603)
        s.net(c, 1, '+5V')
        s.net(c, 2, 'GND')

    # And the MAX3232's supply pin, 16. Its four capacitors are all the charge
    # pump's - C22 sits on +5V, but as V+'s reservoir, not as a bypass - so a
    # chip whose pump switches continuously had nothing at its own supply pin.
    # The board in service has one there, and names it for the pin: Cvcc16.
    c = s.place('Device', 'C', 'C42', '100nF', 63.5, 241.3, footprint=C0603)
    s.net(c, 1, '+5V')
    s.net(c, 2, 'GND')
    s.net(mcu, by['~{RESET}/PC6'] if '~{RESET}/PC6' in by else by.get('PC6', '29'),
          'MCU_RESET')
    rr = s.place('Device', 'R', 'R50', '10k', 25.4, 165.1, footprint=R0603)
    s.net(rr, 1, 'MCU_RESET')
    s.net(rr, 2, '+5V')
    s.net(mcu, by['PD0'], 'MCU_RX')
    s.net(mcu, by['PD1'], 'MCU_TX')

    # A 16 MHz crystal. It was left off at first, by request, and put back
    # before the first order: the internal RC is trimmed only to within 10
    # percent at the factory, and an 8N1 link has about 2 percent to share
    # between both ends. Most chips would have worked; the crystal makes it
    # every chip. The load capacitors suit a crystal specified for CL = 18 to
    # 20 pF: C = 2 x (CL - about 5 pF of stray). The fuses have to be set for
    # it - firmware/build.sh does that when it programs the chip.
    # Pad 1 of the crystal takes XTAL2 and pad 3 XTAL1: on the board pad 1 is
    # the corner nearest pin 8. The crystal does not care which way round it is.
    xt = s.place('Device', 'Crystal_GND24', 'Y1', '16MHz',
                 101.6, 254.0,
                 footprint='Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm')
    s.net(mcu, by['XTAL1/PB6'], 'XTAL1')
    s.net(mcu, by['XTAL2/PB7'], 'XTAL2')
    s.net(xt, '3', 'XTAL1')
    s.net(xt, '1', 'XTAL2')
    s.net(xt, '2', 'GND')
    s.net(xt, '4', 'GND')
    for ref, net, x in (('C33', 'XTAL1', 88.9), ('C34', 'XTAL2', 114.3)):
        c = s.place('Device', 'C', ref, '22pF', x, 266.7, footprint=C0603)
        s.net(c, 1, net)
        s.net(c, 2, 'GND')

    # Every MCU pin that does anything, named. These used to be "the first
    # eight free PD/PB pins in pin order", which produced this same map but
    # would have moved it without a word the day a pin was reserved for
    # something else - and the firmware is written against this map. It is
    # read back out of the netlist by firmware/test, which fails if the two
    # disagree.
    MCU_PINS = (
        ('PD3', 'REL_A'), ('PD4', 'REL_B'), ('PD5', 'REL_C'),
        ('PD6', 'REL_D'), ('PD7', 'REL_E'), ('PB0', 'REL_F'),
        ('PB1', 'MPG_SEL'),                   # SendSerial 'T' / 't'
        ('PB2', 'MCU_LED'),
        ('PB3', 'ICSP_MOSI'), ('PB4', 'ICSP_MISO'), ('PB5', 'ICSP_SCK'),
    )
    for nm, net in MCU_PINS:
        s.net(mcu, by[nm], net)

    # The programming header, back by request: without it the MCU cannot be
    # programmed at all - it is a TQFP, and its clock fuses can only be set
    # through this. The standard 10-pin AVR layout, which is what the board in
    # service has as P1 and what a USBasp plugs into. Shrouded, so the cable
    # goes in one way only: turned round, a plain header puts the programmer's
    # VCC on MISO.
    isp = s.place('Connector', 'AVR-ISP-10', 'J60', 'ICSP', 152.4, 215.9,
                  footprint='Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical')
    s.net(isp, '1', 'ICSP_MOSI')
    s.net(isp, '2', '+5V')
    s.nc(isp, '3')
    s.net(isp, '5', 'MCU_RESET')
    s.net(isp, '7', 'ICSP_SCK')
    s.net(isp, '9', 'ICSP_MISO')
    for g in ('4', '6', '8', '10'):
        s.net(isp, g, 'GND')

    rl = s.place('Device', 'R', 'R51', '1k', 190.5, 165.1, footprint=R0603)
    dl = s.place('Device', 'LED', 'D30', 'SERIAL', 228.6, 165.1,
                 footprint=LED0603, rot=180)
    s.net(rl, 1, 'MCU_LED')
    s.link(rl, 2, dl, 2)
    s.net(dl, 1, 'GND')
    s.nc_rest(mcu)

    s.box(215.9, 35.56, 457.2, 302.26, 'SIX RELAYS - 24 V COILS ONLY')
    s.text('The contacts switch 24 V Finder coils. Nothing on this board touches', 218.44, 43.18)
    s.text('mains. A Finder coil is 20-60 mA, so a 10 A contact is heavily derated.', 218.44, 48.26)
    for i, ch in enumerate(RELAYS):
        y = 76.2 + i * 38.1
        q = s.place('Transistor_FET', 'Q_NMOS_GSD', 'Q%d' % (1 + i), '2N7002',
                    279.4, y, footprint='Package_TO_SOT_SMD:SOT-23')
        rg = s.place('Device', 'R', 'R%d' % (60 + i), '1k', 241.3, y,
                     footprint=R0603)
        rp = s.place('Device', 'R', 'R%d' % (70 + i), '10k', 241.3, y + 15.24,
                     footprint=R0603)
        s.net(rg, 1, 'REL_%s' % ch)
        s.wire(*(rg.at(2) + q.at(1)))
        rg.used.add('2')
        q.used.add('1')
        s.net(rp, 1, 'REL_%s' % ch)
        s.net(rp, 2, 'GND')
        s.net(q, 3, 'GND')
        s.net(q, 2, 'RELC_%s' % ch)

        k = s.place('Relay', 'JQC-3FF-024-1Z', 'K%d' % (1 + i),
                    'JQC-3FF-024-1Z', 330.2, y,
                    footprint='Relay_THT:Relay_SPDT_Hongfa_JQC-3FF_0XX-1Z')
        s.net(k, 'A1', 'V24')
        s.net(k, 'A2', 'RELC_%s' % ch)
        # Beside the relay, not above it: above is where the previous relay
        # in the column already sits.
        fw = s.place('Device', 'D', 'D%d' % (40 + i), '1N4148 flyback',
                     373.38, y, footprint=SOD123)
        s.net(fw, 1, 'V24')          # cathode to the positive rail
        s.net(fw, 2, 'RELC_%s' % ch)
        s.net(k, '11', 'K%s_COM' % ch)
        s.net(k, '14', 'K%s_NO' % ch)
        s.net(k, '12', 'K%s_NC' % ch)
        s.nc_rest(k)

        t = s.place('Connector', 'Conn_01x03_Pin', 'J%d' % (40 + i),
                    'Relay %s' % ch, 419.1, y, footprint=TERM % (3, 3))
        s.net(t, 1, 'K%s_NO' % ch)
        s.net(t, 2, 'K%s_COM' % ch)
        s.net(t, 3, 'K%s_NC' % ch)

        rli = s.place('Device', 'R', 'R%d' % (80 + i), '4k7', 279.4, y + 22.86,
                      footprint=R0603)
        dli = s.place('Device', 'LED', 'D%d' % (50 + i), 'K%s' % ch,
                      330.2, y + 22.86, footprint=LED0603, rot=180)
        s.net(rli, 1, 'V24')
        s.link(rli, 2, dli, 2)
        s.net(dli, 1, 'RELC_%s' % ch)
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
            ' (paper "A4") (title_block (title "MACH3-SIMPLE: copy of the board in service")'
            ' (rev "A0 ENGINEERING ONLY"))(lib_symbols)' % ROOT_UUID)
    notes = (
        '(text "MACH3-SIMPLE  -  6 axes, two LPT ports, buffered 5 V outputs" (at 12.7 12.7 0)'
        ' (effects (font (size 2.54 2.54)) (justify left)) (uuid "%s"))'
        '(text "A copy of the board in service, extras removed. NOT ISOLATED on the'
        ' output side." (at 12.7 20.32 0) (effects (font (size 1.524 1.524))'
        ' (justify left)) (uuid "%s"))'
        '(text "A0: NOT BUILT, NOT TESTED." (at 12.7 27.94 0)'
        ' (effects (font (size 1.524 1.524)) (justify left)) (uuid "%s"))'
        % (uid(), uid(), uid()))
    return head + notes + ''.join(body) + '(sheet_instances (path "/" (page "1")))) '


def main():
    os.makedirs(HW, exist_ok=True)
    built, clashes = {}, []
    DECOUPLE_AT = {'01_power': 900, '02_outputs': 910,
                   '03_inputs': 930, '04_relays': 950}
    for fn in (build_power, build_outputs, build_inputs, build_relays):
        s = fn()
        key = s.filename[:-len('.kicad_sch')]
        s.write(HW)
        built[key] = s
        print('wrote %-22s %3d symbols%s'
              % (s.filename, len(s.symbols),
                 '' if not s._clashes
                 else '  UNRESOLVED STUB CLASH: ' + ', '.join(s._clashes)))
        clashes.extend('%s: %s' % (s.filename, c) for c in s._clashes)

    with open(os.path.join(HW, PROJECT + '.kicad_sch'), 'w',
              encoding='utf-8', newline='') as f:
        f.write(build_root(built))
    print('wrote', PROJECT + '.kicad_sch')

    if clashes:
        print()
        print('FATAL: %d stub(s) could not be placed without touching another net.'
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
        print('wrote', PROJECT + '.kicad_pro')
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
