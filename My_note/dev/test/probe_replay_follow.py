#!/usr/bin/env python3
"""硬件实测：宿主机式下发目标 -> 看实测角是否跟随。

小幅度（joint1 +0.1 rad = 5.7°），安全。
"""
import json
import socket
import sys
import threading
import time

PORT = 1348
NAMES = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'r_joint']


def main():
    sock = socket.create_connection(('127.0.0.1', PORT), timeout=5.0)
    sock.settimeout(3.0)

    # 1) 读当前实测
    buf = b''
    while b'\n' not in buf:
        buf += sock.recv(65536)
    frame = json.loads(buf.split(b'\n')[0])
    print('起点实测 q:', [round(v, 3) for v in frame['q']])
    print('起点实测 pulse:', frame['pulse'])

    base = list(frame['q'])
    target = list(base)
    target[0] = base[0] + 0.10          # joint1 +5.7°

    state = {'q': target, 'run': True}

    def sender():
        while state['run']:
            try:
                sock.sendall((json.dumps({
                    'cmd': 'joints', 'names': NAMES,
                    'q': state['q']}) + '\n').encode())
            except OSError:
                return
            time.sleep(1.0 / 22.6)

    threading.Thread(target=sender, daemon=True).start()
    print('\n下发 joint1 -> %.3f rad（%.1f°），持续 3s ...'
          % (target[0], target[0] * 57.3))

    seen = {}
    t0 = time.time()
    buf = b''
    while time.time() - t0 < 3.0:
        try:
            buf += sock.recv(65536)
        except socket.timeout:
            continue
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            if not line.strip():
                continue
            f = json.loads(line)
            for n, q in zip(f['names'], f['q']):
                seen.setdefault(n, []).append(q)

    for n in NAMES:
        vals = seen.get(n, [])
        if vals:
            print('  %-8s 实测 q: 起 %.3f -> 末 %.3f  (变化 %+.3f rad = %+.1f°)'
                  % (n, vals[0], vals[-1], vals[-1] - vals[0],
                     (vals[-1] - vals[0]) * 57.3))

    state['run'] = False
    time.sleep(0.3)
    sock.sendall(b'{"cmd":"stop","release":true}\n')
    time.sleep(0.5)
    sock.close()


if __name__ == '__main__':
    sys.exit(main())
