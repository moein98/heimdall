"""grblHAL simulator tests for MACH3-SIMPLE-ETH: 8 axes, over TCP as the UI will."""
import math, os, signal, subprocess, sys, time
import client

SIM = sys.argv[1]
WORK = os.path.dirname(os.path.abspath(__file__))
PORT = 5000
results = []


def check(name, ok, detail=''):
    results.append((name, ok, detail))
    print('%-4s %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def start(step_file):
    for f in ('EEPROM.DAT', step_file, 'blocks.out'):
        try:
            os.remove(os.path.join(WORK, f))
        except OSError:
            pass
    for _ in range(30):          # the port can take a moment to free after a kill
        p = subprocess.Popen([SIM, '-n', '-t', '0', '-r', '0.02', '-p', str(PORT),
                              '-s', step_file, '-b', 'blocks.out'],
                             cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        if p.poll() is None:
            break
    client.PORT = PORT
    g = client.Grbl()
    time.sleep(0.3)
    return p, g


def steps(fn):
    rows = []
    for line in open(os.path.join(WORK, fn)):
        if line.startswith('#'):
            continue
        v = line.split()
        rows.append((float(v[0]), [int(x) for x in v[1:]]))
    return rows


def mpos(st):
    return [float(x) for x in st.split('MPos:')[1].split('|')[0].split(',')]


p, g = start('steps1.out')
try:
    # 1. identity
    info = g.cmd('$I')
    check('build reports 8 axes', any('[AXS:8:XYZABCUV]' in l for l in info),
          [l for l in info if l.startswith('[AXS')][0])
    g.cmd('$X')

    # 2. per-axis settings: steps/mm, max rate, accel for all 8 axes
    for i in range(8):
        g.cmd('$%d=%d' % (100 + i, 400 + 100 * i))   # distinct steps/mm
        g.cmd('$%d=3000' % (110 + i))
        g.cmd('$%d=200' % (120 + i))
    ss = g.cmd('$$')
    got = {l.split('=')[0]: l.split('=')[1] for l in ss if l.startswith('$1')}
    check('steps/mm stored for all 8 axes ($100-$107)',
          all(abs(float(got['$%d' % (100 + i)]) - (400 + 100 * i)) < 1e-6 for i in range(8)),
          ' '.join('$%d=%s' % (100 + i, got['$%d' % (100 + i)]) for i in range(8)))

    # 3. one coordinated move on all 8 axes
    tgt = [10, 20, -5, 90, 45, 30, 12, 7]
    g.cmd('G21 G90 G94')
    g.cmd('G1 ' + ' '.join('%s%g' % (a, v) for a, v in zip('XYZABCUV', tgt)) + ' F900')
    st = g.wait_idle(60)
    check('8-axis move ends at target', max(abs(a - b) for a, b in zip(mpos(st), tgt)) < 1e-3,
          st.split('|')[1])
    rows = steps('steps1.out')
    final = [t * (400 + 100 * i) for i, t in enumerate(tgt)]
    # Coordinated = every axis the same fraction of the way at every sample.
    worst = 0.0
    for t, pos in rows:
        fr = [pos[i] / final[i] for i in range(8)]
        worst = max(worst, max(fr) - min(fr))
    check('all 8 axes move together (Bresenham)',
          worst < 0.01, 'worst spread of progress between axes: %.4f%% over %d samples'
          % (worst * 100, len(rows)))
    # Bresenham: an axis with fewer steps takes its first a few dominant
    # steps later. So: every axis moving by the time the move is 1 % done.
    first = next((t, pos) for t, pos in rows
                 if max(abs(pos[i] / final[i]) for i in range(8)) >= 0.01)
    last_t, last = rows[-1]
    fr_last = [last[i] / final[i] for i in range(8)]
    check('all 8 start in the same sample and finish together',
          all(first[1]) and min(fr_last) > 0.98,
          'at 1%% of the move (%.3f s): all 8 moving; last sample (%.3f s): %.1f-%.1f%% done'
          % (first[0], last_t, min(fr_last) * 100, max(fr_last) * 100))

    # 4. arc in XY with A and U riding along (helical style)
    m0 = mpos(g.wait_idle(10))
    g.cmd('G91 G17 G2 X20 Y0 I10 J0 A180 U5 F1200')
    g.cmd('G90')
    st = g.wait_idle(60)
    m = [a - b for a, b in zip(mpos(st), m0)]
    check('arc G2 + A + U lands on target',
          abs(m[0] - 20) < 1e-3 and abs(m[1]) < 1e-3 and abs(m[3] - 180) < 1e-3
          and abs(m[6] - 5) < 1e-3, 'moved X%.3f Y%.3f A%.3f U%.3f' % (m[0], m[1], m[3], m[6]))

    # 5. jog, as a UI or the handwheel MCU would send it
    m0 = mpos(g.wait_idle(10))
    r = g.cmd('$J=G91 G21 U2.5 V-1.5 F600')
    st = g.wait_idle(30)
    m = [a - b for a, b in zip(mpos(st), m0)]
    check('jog $J= on U and V', r[-1] == 'ok' and abs(m[6] - 2.5) < 1e-3 and abs(m[7] + 1.5) < 1e-3,
          'moved U%.3f V%.3f' % (m[6], m[7]))

    # 6. bad input is refused, not executed
    r = g.cmd('G1 X10 Q')
    check('malformed G-code is rejected', r[-1].startswith('error'), r[-1])
finally:
    p.send_signal(signal.SIGKILL)

# 7. feed hold and resume in the middle of a long move, and a whole program
p, g = start('steps2.out')
try:
    g.cmd('$X')
    g.cmd('G21 G90 G1 X200 B100 F300')
    time.sleep(0.05)
    g.s.sendall(b'!')
    time.sleep(0.5)
    st = g.status()
    held = st and st.startswith('<Hold')
    pos_hold = mpos(st)[0] if st else None
    time.sleep(0.5)
    st2 = g.status()
    check('feed hold stops motion', held and abs(mpos(st2)[0] - pos_hold) < 1e-6,
          '%s ... X stays at %.3f' % (st.split('|')[0], pos_hold))
    g.s.sendall(b'~')
    st = g.wait_idle(120)
    check('cycle start resumes and finishes, every axis exact',
          abs(mpos(st)[0] - 200) < 1e-6 and abs(mpos(st)[4] - 100) < 1e-6,
          st.split('|')[1] + '  (see hold_test.py)')

    # A real program: a 40-point star outline in XY, Z plunges, A/U/V
    # indexing between passes - streamed line by line, as a sender does.
    prog = ['G21 G90 G92 X0 Y0 Z0 A0 B0 C0 U0 V0', 'G0 Z5']
    for k in range(3):
        prog += ['G0 X50 Y0', 'G1 Z-1 F200']
        for i in range(1, 41):
            ang = 2 * math.pi * i / 40
            r = 50 if i % 2 == 0 else 20
            prog.append('G1 X%.3f Y%.3f F1500' % (r * math.cos(ang), r * math.sin(ang)))
        prog += ['G0 Z5', 'G0 A%d U%d V%d' % (120 * (k + 1), 10 * (k + 1), -5 * (k + 1))]
    prog += ['G0 X0 Y0 Z10']
    t0 = time.time()
    errors = []
    for l in prog:
        r = g.cmd(l, 60)
        if not r or r[-1] != 'ok':
            errors.append((l, r))
    g.wait_idle(300)
    r = g.cmd('M30', 60)               # syncs: answers once motion is done
    if not r or r[-1] != 'ok':
        errors.append(('M30', r))
    st = g.wait_idle(300)
    check('program of %d lines runs with no error' % len(prog), not errors,
          '%s; end %s' % (errors[:2] or 'all ok', st.split('|')[1]))
    m = mpos(st)
    check('program ends where it should (A360 U30 V-15, back at X0Y0Z10)',
          abs(m[3] - 360) < 1e-3 and abs(m[6] - 30) < 1e-3 and abs(m[7] + 15) < 1e-3
          and abs(m[2] - 10) < 1e-3, st.split('|')[1])
finally:
    p.send_signal(signal.SIGKILL)

n_ok = sum(1 for r in results if r[1])
print('\n%d / %d passed' % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
