"""Talk to grblHAL (simulator or board) over raw TCP, as a sender/UI would."""
import socket, sys, time, re

HOST, PORT = '127.0.0.1', 5000


def PORT_():
    return PORT


class Grbl:
    def __init__(self):
        for _ in range(50):
            try:
                self.s = socket.create_connection((HOST, PORT_()), timeout=5)
                break
            except OSError:
                time.sleep(0.2)
        self.buf = b''

    def _lines(self, until, timeout=10):
        out, end = [], time.time() + timeout
        while time.time() < end:
            while b'\n' in self.buf:
                line, self.buf = self.buf.split(b'\n', 1)
                line = line.decode(errors='replace').strip()
                if line:
                    out.append(line)
                    if until(line):
                        return out
            try:
                self.s.settimeout(0.2)
                d = self.s.recv(4096)
                if d:
                    self.buf += d
            except socket.timeout:
                pass
        return out

    def cmd(self, line, timeout=10):
        self.s.sendall(line.encode() + b'\n')
        return self._lines(lambda l: l == 'ok' or l.startswith('error'), timeout)

    def status(self):
        self.s.sendall(b'?')
        r = self._lines(lambda l: l.startswith('<'), 3)
        return [l for l in r if l.startswith('<')][-1] if r else None

    def wait_idle(self, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            st = self.status()
            if st and st.startswith('<Idle'):
                return st
            time.sleep(0.1)
        return self.status()


if __name__ == '__main__':
    PORT = int(sys.argv[1])
    g = Grbl()
    time.sleep(0.5)
    for c in sys.argv[2:]:
        print('>>', c)
        for l in g.cmd(c, 30):
            print('  ', l)
