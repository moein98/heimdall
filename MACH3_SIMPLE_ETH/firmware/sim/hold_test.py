"""Feed hold / resume at many moments: does any axis lose a step?"""
import os, signal, subprocess, sys, time
import client

SIM = sys.argv[1]
WORK = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[2]) if len(sys.argv) > 2 else 12


def start():
    try:
        os.remove(os.path.join(WORK, 'EEPROM.DAT'))
    except OSError:
        pass
    for _ in range(30):
        p = subprocess.Popen([SIM, '-n', '-t', '0', '-p', '5000', '-s', 'hs.out', '-b', 'hb.out'],
                             cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.4)
        if p.poll() is None:
            break
    client.PORT = 5000
    g = client.Grbl()
    time.sleep(0.2)
    return p, g


def mpos(st):
    return [float(x) for x in st.split('MPos:')[1].split('|')[0].split(',')]


bad = 0
for trial in range(N):
    p, g = start()
    try:
        g.cmd('$X')
        g.cmd('G21 G90 G1 X200 B100 F300')
        time.sleep(0.02 + 0.03 * trial)
        g.s.sendall(b'!')
        time.sleep(0.3)
        held = g.status()
        g.s.sendall(b'~')
        st = g.wait_idle(120)
        m = mpos(st)
        err = [m[0] - 200, m[4] - 100]
        lost = any(abs(e) > 1e-6 for e in err)
        bad += lost
        print('trial %2d  hold at X=%8.3f B=%8.3f  end X=%.3f B=%.3f  %s'
              % (trial, mpos(held)[0], mpos(held)[4], m[0], m[4], 'STEP LOST' if lost else 'ok'))
    finally:
        p.send_signal(signal.SIGKILL)
        p.wait()
print('%d / %d trials lost a step' % (bad, N))
