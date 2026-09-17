#!/usr/bin/env python3
"""Integration test for the dataset_stream downlink (fake driver, no arm).

Needs the workspace sourced first:

    source /opt/ros/jazzy/setup.bash
    source install/setup.bash
    python3 My_note/dev/test/test_downlink_integration.py
"""

import json
import socket
import threading
import time

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from ros_robot_controller_msgs.msg import (
    BusServoState, SetBusServoState)
from ros_robot_controller_msgs.srv import GetBusServoState
from servo_controller_msgs.msg import ServosPosition
from std_srvs.srv import Trigger

from arm_lerobot_dataset_stream.dataset_stream import DatasetStream

PORT = 1351
JOINTS = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'r_joint']
FAILURES = []


def check(name, ok, detail=''):
    """Record and print one assertion."""
    print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', name, detail))
    if not ok:
        FAILURES.append(name)


class FakeDriver(Node):
    """Minimal stand-in for ros_robot_controller."""

    def __init__(self):
        """Create the get_state/init_finish services and state sink."""
        super().__init__('fake_driver')
        self.pulse = {i: 500 for i in range(1, 7)}
        self.torque_events = []
        self.create_service(GetBusServoState,
                            '/ros_robot_controller/bus_servo/get_state',
                            self._get_state)
        self.create_service(Trigger, '/ros_robot_controller/init_finish',
                            self._init_done)
        self.create_subscription(
            SetBusServoState,
            '/ros_robot_controller/bus_servo/set_state', self._set_state, 10)

    def _init_done(self, request, response):
        response.success = True
        return response

    def _get_state(self, request, response):
        states = []
        for cmd in request.cmd:
            data = BusServoState()
            data.present_id = [int(cmd.id)]
            data.position = [self.pulse.get(int(cmd.id), 500)]
            states.append(data)
        response.state = states
        return response

    def _set_state(self, msg):
        for state in msg.state:
            if state.present_id and state.present_id[0]:
                servo_id = int(state.present_id[1])
                if state.enable_torque and state.enable_torque[0]:
                    self.torque_events.append(
                        (servo_id, int(state.enable_torque[1])))


class FakeGateway(Node):
    """Record everything published on /servo_controller."""

    def __init__(self):
        """Subscribe to the semantic gateway topic."""
        super().__init__('fake_gateway')
        self.commands = []
        self.create_subscription(
            ServosPosition, '/servo_controller', self._on_position, 10)

    def _on_position(self, msg):
        self.commands.append(
            {int(p.id): float(p.position) for p in msg.position})


class Sender:
    """Emit a joints command at 20 Hz so the watchdog stays fed."""

    def __init__(self, sock):
        """Remember the socket and start with all targets at zero."""
        self.sock = sock
        self.target = [0.0] * len(JOINTS)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        """Start emitting commands."""
        self._thread.start()

    def stop(self):
        """Stop emitting and wait for the thread."""
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _run(self):
        while not self._stop.is_set():
            try:
                send(self.sock, {'cmd': 'joints', 'names': JOINTS,
                                 'q': list(self.target)})
            except OSError:
                return
            time.sleep(0.05)


def open_client(port):
    """Connect a TCP client and drain the first frame."""
    sock = socket.create_connection(('127.0.0.1', port), timeout=2.0)
    sock.settimeout(2.0)
    sock.recv(4096)
    return sock


def send(sock, obj):
    """Send one newline terminated JSON command."""
    sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))


def run_case(enable_downlink, port):
    """Start the fake driver/gateway and the real node; return them."""
    rclpy.init(args=['--ros-args',
                     '-p', 'enable_downlink:=%s' % str(enable_downlink).lower(),
                     '-p', 'poll_rate_hz:=20.0',
                     '-p', 'tcp_port:=%d' % port,
                     '-p', 'watchdog_timeout:=0.4'])
    driver = FakeDriver()
    gateway = FakeGateway()
    stream = DatasetStream()
    executor = MultiThreadedExecutor()
    for node in (driver, gateway, stream):
        executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    time.sleep(0.8)                       # let the poll loop publish frames
    return driver, gateway, stream, executor


def teardown(stream, executor):
    """Stop everything and free the TCP port."""
    stream.destroy_node()
    executor.shutdown()
    rclpy.shutdown()
    time.sleep(0.8)


def case_recording():
    """enable_downlink=false: commands must be ignored completely."""
    print('== case 1: enable_downlink=false (recording) ==')
    driver, gateway, stream, executor = run_case(False, PORT)
    sock = open_client(PORT)
    try:
        send(sock, {'cmd': 'joints', 'names': JOINTS,
                    'q': [0.5, -0.5, 0.0, 0.0, 0.0, 0.0]})
        send(sock, {'cmd': 'arm'})
        time.sleep(0.6)
        check('no /servo_controller commands', not gateway.commands,
              'got %d' % len(gateway.commands))
        check('no torque commands', not driver.torque_events,
              'got %s' % driver.torque_events[:3])
    finally:
        sock.close()
        teardown(stream, executor)


def case_replay():
    """enable_downlink=true: ramp, watchdog and disconnect safety."""
    print('== case 2: enable_downlink=true (replay) ==')
    driver, gateway, stream, executor = run_case(True, PORT + 1)
    sock = open_client(PORT + 1)
    try:
        check('state starts IDLE', stream._safety.state == 'IDLE',
              stream._safety.state)

        sender = Sender(sock)
        sender.start()
        time.sleep(1.0)
        check('armed while commands flow', stream._safety.state == 'ARMED',
              stream._safety.state)
        check('torque enabled on all servos',
              sorted(set(driver.torque_events)) ==
              [(i, 1) for i in range(1, 7)],
              str(sorted(set(driver.torque_events))))

        # step the target and watch the ramp on joint1 (servo id 6)
        driver.torque_events.clear()
        gateway.commands.clear()
        sender.target[0] = 0.5
        time.sleep(0.6)
        joint1 = [c[6] for c in gateway.commands if 6 in c]
        check('ramp starts at the measured pose',
              bool(joint1) and joint1[0] <= 0.1 + 1e-6,
              'first=%.4f' % joint1[0] if joint1 else 'no command')
        check('ramp respects max step',
              all(b - a <= 0.15 + 1e-6
                  for a, b in zip(joint1, joint1[1:])),
              'n=%d' % len(joint1))
        check('ramp reaches the target',
              bool(joint1) and abs(joint1[-1] - 0.5) < 0.02,
              'last=%.4f' % joint1[-1] if joint1 else 'no command')

        # watchdog: stop sending, wait past watchdog_timeout (0.4 s)
        sender.stop()
        driver.torque_events.clear()
        time.sleep(1.0)
        check('watchdog -> SAFE', stream._safety.state == 'SAFE',
              stream._safety.state)
        check('watchdog releases torque',
              len(driver.torque_events) >= 6
              and all(e[1] == 0 for e in driver.torque_events),
              str(sorted(set(driver.torque_events))))

        # a new command stream must recover from SAFE
        sender2 = Sender(sock)
        sender2.start()
        time.sleep(0.5)
        check('recovers to ARMED', stream._safety.state == 'ARMED',
              stream._safety.state)

        # disconnect: must go SAFE and release torque
        driver.torque_events.clear()
        sock.close()
        time.sleep(1.2)
        check('disconnect -> SAFE', stream._safety.state == 'SAFE',
              stream._safety.state)
        check('disconnect releases torque',
              len(driver.torque_events) >= 6
              and all(e[1] == 0 for e in driver.torque_events),
              str(sorted(set(driver.torque_events))))
        sender2.stop()
    finally:
        try:
            sock.close()
        except OSError:
            pass
        teardown(stream, executor)


def case_slow_client():
    """A stalling client must not block the node and gets fresh data."""
    print('== case 3: async latest-only (slow client) ==')
    driver, gateway, stream, executor = run_case(False, PORT + 2)
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048)  # tiny window
    sock.settimeout(3.0)
    sock.connect(('127.0.0.1', PORT + 2))
    try:
        sock.recv(4096)                     # drain the first frame
        seq_before = stream._seq
        time.sleep(4.0)                     # stop reading -> buffers fill
        seq_after = stream._seq
        check('node keeps sampling while a client stalls',
              seq_after - seq_before >= 50,
              'seq %d -> %d' % (seq_before, seq_after))

        sock.setblocking(False)             # now drain the backlog, keep last
        blob = b''
        deadline = time.time() + 2.5
        while time.time() < deadline:
            try:
                chunk = sock.recv(65536)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            except OSError:
                break
            if not chunk:
                break
            blob += chunk
        lines = [ln for ln in blob.split(b'\n') if ln.strip()]
        last = json.loads(lines[-1])['seq']
        check('stale frames were dropped, not queued',
              bool(lines) and stream._seq - last <= 3,
              'node=%d last_read=%d read=%d'
              % (stream._seq, last, len(lines)))
        check('dropped frames are accounted for (bounded queue)',
              stream._dropped > 0,
              'dropped=%d' % stream._dropped)
    finally:
        sock.close()
        teardown(stream, executor)


def main():
    """Run the scenarios and report."""
    case_recording()
    case_replay()
    case_slow_client()
    case_recording()
    case_replay()
    print('\n== result ==')
    if FAILURES:
        print('FAILED: %s' % ', '.join(FAILURES))
        raise SystemExit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
