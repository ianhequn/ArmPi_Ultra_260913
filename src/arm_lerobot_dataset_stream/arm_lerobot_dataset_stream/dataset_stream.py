# Copyright 2026 Rui
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

r"""
Stream measured arm joint states to a host over TCP as newline JSON.

This node polls the driver's ``get_state`` service for every mapped servo,
converts the raw pulses to radians, and broadcasts one JSON line per cycle
to all connected TCP clients.  It feeds a custom LeRobot robot class on the
host (Windows) without any ROS dependency on that side.

One frame per line, UTF-8, terminated by ``'\n'``::

    {"t":1789287268.123,"seq":42,
     "names":["joint1","joint2","joint3","joint4","joint5","r_joint"],
     "q":[0.21,-0.13,0.0,0.0,0.28,0.0],
     "pulse":[566,500,500,500,520,700]}

``q`` is in radians, ``pulse`` is the raw servo value (0..1000).

The same TCP connection carries an optional downlink (host -> VM) used by
``lerobot-replay`` / rollout.  It stays inert unless ``enable_downlink`` is
true::

    {"cmd":"joints","names":[...],"q":[...]}   -> publish /servo_controller
    {"cmd":"arm"} / {"cmd":"disarm"}           -> torque on / off
    {"cmd":"stop","release":true} / {"cmd":"ping"}

See ``My_note/dev/stream_docs/lerobot下行控制协议与VM设计.md``.
"""

import json
import math
import os
import select
import socket
import threading
import time

from ament_index_python.packages import get_package_share_directory
from arm_lerobot_dataset_stream.downlink import (
    extract_targets, parse_line, SafetyState)
from arm_vofaUDP_bridge.servo_map import load_joint_map, pulse_to_deg
import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import (
    BusServoState, GetBusServoCmd, SetBusServoState)
from ros_robot_controller_msgs.srv import GetBusServoState
from sensor_msgs.msg import JointState
from servo_controller_msgs.msg import ServoPosition, ServosPosition
from std_srvs.srv import Trigger


class DatasetStream(Node):
    """TCP JSON stream of measured joint states for LeRobot recording."""

    MAX_LINE = 8192
    SO_SNDBUF_BYTES = 2048

    def __init__(self):
        """Read parameters, open the TCP server and start the workers."""
        super().__init__('dataset_stream')
        self.declare_parameter('servo_config', self._default_servo_config())
        self.declare_parameter('poll_rate_hz', 30.0)
        self.declare_parameter('tcp_host', '0.0.0.0')
        self.declare_parameter('tcp_port', 1348)
        self.declare_parameter('release_torque', False)
        # downlink (host -> VM), disabled by default: recording is untouched
        self.declare_parameter('enable_downlink', False)
        self.declare_parameter('auto_engage', True)
        self.declare_parameter('watchdog_timeout', 1.0)
        self.declare_parameter('release_on_timeout', True)
        self.declare_parameter('release_on_disconnect', True)
        self.declare_parameter('downlink_token', '')
        self.declare_parameter('max_parse_errors', 50)

        self._joint_map = load_joint_map(
            self.get_parameter('servo_config').value)
        # logical order: joint1..joint5, r_joint (alphabetical by name)
        self._ids = sorted(self._joint_map,
                           key=lambda i: self._joint_map[i]['name'])
        self._names = [self._joint_map[i]['name'] for i in self._ids]
        self._name_set = set(self._names)
        self._rate = float(self.get_parameter('poll_rate_hz').value)
        host = self.get_parameter('tcp_host').value
        port = int(self.get_parameter('tcp_port').value)

        self._tcp_clients = []
        self._tcp_lock = threading.Lock()
        self._seq = 0

        # 上行："最新帧" 单槽位（覆盖式）。生产端只写不阻塞，
        # 每客户端一个发送线程按自己的节奏取走当前最新帧，
        # 中间被跳过的帧直接丢弃 —— 宿主机可任意改变读取频率。
        self._frame_cv = threading.Condition()
        self._latest_frame = None
        self._latest_seq = 0
        self._dropped = 0
        self._closing = False

        self._enable_downlink = bool(
            self.get_parameter('enable_downlink').value)
        self._auto_engage = bool(self.get_parameter('auto_engage').value)
        self._release_on_timeout = bool(
            self.get_parameter('release_on_timeout').value)
        self._release_on_disconnect = bool(
            self.get_parameter('release_on_disconnect').value)
        self._token = str(self.get_parameter('downlink_token').value)
        self._max_parse_errors = int(
            self.get_parameter('max_parse_errors').value)
        self._duration = max(0.02, 1.0 / self._rate) if self._rate else 0.02
        self._safety = SafetyState(
            self.get_parameter('watchdog_timeout').value)
        self._target_rad = {}
        self._measured_rad = {}
        self._parse_errors = 0
        self._command_count = 0
        self._last_summary = 0.0
        self._stalled_since = 0.0
        self._stall_warn = 0.0
        self._pending = None

        self._state_client = self.create_client(
            GetBusServoState, 'ros_robot_controller/bus_servo/get_state')
        self._init_client = self.create_client(
            Trigger, 'ros_robot_controller/init_finish')
        self._state_pub = self.create_publisher(
            SetBusServoState, 'ros_robot_controller/bus_servo/set_state', 10)
        self._servo_pub = self.create_publisher(
            ServosPosition, 'servo_controller', 1)
        self._joint_pub = self.create_publisher(
            JointState, '~/joint_states_measured', 10)

        if not self._ids:
            self.get_logger().error('empty joint map (check servo_config)')

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((host, port))
        except OSError as exc:
            self.get_logger().error(
                'cannot bind %s:%d (%s) -> another dataset_stream is probably '
                'still running. Check with:  ss -ltnp | grep %d  '
                'and kill it, or pick another tcp_port' % (host, port, exc, port))
            raise
        self._server.listen(5)
        self._server.settimeout(0.5)
        self.get_logger().info(
            'dataset_stream TCP %s:%d @ %.1f Hz, joints=%s'
            % (host, port, self._rate, self._names))
        if self._enable_downlink:
            self.get_logger().warn(
                'DOWNLINK ENABLED: host servo commands WILL be executed')
        else:
            self.get_logger().info('downlink disabled (recording only)')

        if self.get_parameter('release_torque').value:
            threading.Thread(
                target=self._release_torque_when_ready, daemon=True).start()

        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._poll_loop, daemon=True).start()
        threading.Thread(target=self._check_driver_ready, daemon=True).start()

    def _check_driver_ready(self):
        """Report clearly at startup whether the driver is reachable."""
        if self._state_client.wait_for_service(timeout_sec=10.0):
            self.get_logger().info('driver ready (get_state available)')
            return
        self.get_logger().error(
            'driver NOT ready: ros_robot_controller/bus_servo/get_state is '
            'missing -> serial port dead? (CH340 "[Errno 5] Input/output '
            'error" is fixed by unplug/replug the USB) or the driver node died')

    @staticmethod
    def _default_servo_config():
        """Return the installed servo_controller YAML path (or empty)."""
        try:
            share = get_package_share_directory('servo_controller')
        except Exception:
            return ''
        return os.path.join(share, 'config', 'servo_controller.yaml')

    # ----------------------------------------------------------- networking

    def _accept_loop(self):
        """Accept TCP clients and start one command reader per client."""
        while not self._closing:
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # 小发送缓冲：客户端读得慢时只能靠丢弃（而非无限堆内存）
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF,
                            self.SO_SNDBUF_BYTES)
            # 发送端保持阻塞（永不超时，避免 sendall 部分写入撕坏 JSON 行）；
            # 用 TCP_USER_TIMEOUT 兜住“对端已死”的连接。
            conn.setblocking(True)
            if hasattr(socket, 'TCP_USER_TIMEOUT'):
                try:
                    conn.setsockopt(socket.IPPROTO_TCP,
                                    socket.TCP_USER_TIMEOUT, 10000)
                except OSError:
                    pass
            with self._tcp_lock:
                self._tcp_clients.append(conn)
            self.get_logger().info('client connected: %s:%d' % addr)
            threading.Thread(
                target=self._client_reader, args=(conn, addr),
                daemon=True).start()
            threading.Thread(
                target=self._client_sender, args=(conn, addr),
                daemon=True).start()

    def _drop_client(self, conn):
        """Forget and close one client socket (idempotent)."""
        with self._tcp_lock:
            if conn in self._tcp_clients:
                self._tcp_clients.remove(conn)
        try:
            conn.close()
        except OSError:
            pass

    def _client_reader(self, conn, addr):
        """Read downlink command lines from one client until it goes away."""
        buffer = b''
        while not self._closing:
            # 用 select 做超时，而不是 conn.settimeout：后者会把同一 socket
            # 上的 sendall 也变成非阻塞超时模式。
            try:
                ready, _, _ = select.select([conn], [], [], 0.5)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = conn.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > self.MAX_LINE:
                buffer = buffer[-self.MAX_LINE:]
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                line = line.strip()
                if line:
                    self._handle_line(line)
        self._drop_client(conn)
        self.get_logger().info('client disconnected: %s:%d' % addr)
        if self._safety.armed:
            self._enter_safe('client disconnected',
                             self._release_on_disconnect)

    def _handle_line(self, line):
        """Parse and dispatch one downlink line, counting bad ones."""
        msg = parse_line(line)
        if msg is None:
            self._parse_errors += 1
            if self._parse_errors > self._max_parse_errors:
                self._parse_errors = 0
                self._enter_safe('too many malformed downlink lines',
                                 self._release_on_disconnect)
            return
        self._parse_errors = 0
        try:
            self._on_command(msg)
        except Exception as exc:                  # noqa: BLE001
            self.get_logger().error('downlink command failed: %s' % exc)

    def _publish_frame(self, line):
        """Store the newest frame and wake the senders (never blocks)."""
        with self._frame_cv:
            self._latest_frame = line
            self._latest_seq += 1
            self._frame_cv.notify_all()

    def _client_sender(self, conn, addr):
        """
        Push the newest frame to one client, skipping frames it missed.

        Runs in its own thread with a *blocking* send, so a slow client
        slows only itself: the sampling/control loop keeps running and
        every frame already superseded when the send returns is dropped.
        """
        sent_seq = 0
        while not self._closing:
            with self._frame_cv:
                self._frame_cv.wait_for(
                    lambda: self._latest_seq != sent_seq or self._closing,
                    timeout=1.0)
                if self._closing:
                    return
                seq = self._latest_seq
                line = self._latest_frame
            if line is None or seq == sent_seq:
                continue
            try:
                conn.sendall(line)
            except OSError:
                break
            if sent_seq and seq > sent_seq + 1:
                self._dropped += seq - sent_seq - 1
            sent_seq = seq          # 只有发成功才推进；否则下次取最新
        self._drop_client(conn)

    # -------------------------------------------------------------- downlink

    def _on_command(self, msg):
        """Execute one decoded command (lock L2 is applied here)."""
        if not self._enable_downlink:
            return
        if self._token and msg.get('token') != self._token:
            return

        command = msg['cmd']
        now = time.time()

        if command == 'ping':
            self._safety.touch(now)
        elif command == 'arm':
            self._engage()
            self._safety.arm(now)
            self.get_logger().info('downlink: armed (torque on)')
        elif command == 'disarm':
            self._set_torque(False)
            self._target_rad = {}
            self._safety.idle()
            self.get_logger().info('downlink: disarmed (torque off)')
        elif command == 'stop':
            self._target_rad = {}
            self._safety.touch(now)
            if msg.get('release'):
                self._set_torque(False)
                self._safety.idle()
            self.get_logger().info(
                'downlink: stop (release=%s)' % bool(msg.get('release')))
        elif command == 'joints':
            targets = extract_targets(msg, self._name_set)
            if not targets:
                return
            if not self._safety.armed and self._auto_engage:
                self._engage()
                self._safety.arm(now)
                self.get_logger().info(
                    'downlink: armed by first joints command')
            self._target_rad.update(targets)
            self._safety.touch(now)
            self._command_count += 1

    def _engage(self):
        """Hold the arm at its current pose (torque on)."""
        self._set_torque(True)
        self._set_torque(True)      # 连发两次，防单帧丢失导致全程无力

    def _enter_safe(self, reason, release):
        """Stop executing targets, optionally releasing torque."""
        self._safety.safe()
        self._target_rad = {}
        self.get_logger().warn('downlink SAFE: %s' % reason)
        if release:
            self._set_torque(False)

    def _control_tick(self):
        """Publish the latest host target (no-op when disabled)."""
        if not self._enable_downlink:
            return
        now = time.time()
        if self._safety.timed_out(now):
            self._enter_safe('watchdog timeout', self._release_on_timeout)
            return
        if not self._safety.armed or not self._target_rad:
            return

        # 不做任何限速：宿主机给的就是录制时的目标，duration 让舵机自己插值
        msg = ServosPosition()
        msg.duration = float(self._duration)
        msg.position_unit = 'rad'
        for servo_id in self._ids:
            target = self._target_rad.get(self._joint_map[servo_id]['name'])
            if target is None:
                continue
            servo = ServoPosition()
            servo.id = servo_id
            servo.position = target
            msg.position.append(servo)
        if msg.position:
            self._servo_pub.publish(msg)
            self._log_summary(now)

    def _log_summary(self, now):
        """Log the command rate every few seconds while armed."""
        if now - self._last_summary < 5.0:
            return
        period = now - self._last_summary if self._last_summary else 5.0
        self._last_summary = now
        self.get_logger().info(
            'downlink: %d cmds in %.1fs (%.1f Hz) state=%s'
            % (self._command_count, period,
               self._command_count / period, self._safety.state))
        self._command_count = 0

    def _set_torque(self, enable):
        """Enable or disable the torque of every mapped servo."""
        msg = SetBusServoState()
        for servo_id in self._ids:
            state = BusServoState()
            state.present_id = [1, servo_id]
            state.enable_torque = [1, 1 if enable else 0]
            msg.state.append(state)
        self._state_pub.publish(msg)
        self.get_logger().info(
            'torque %s on %d servos'
            % ('on' if enable else 'off', len(self._ids)))

    # --------------------------------------------------------------- polling

    def _poll_loop(self):
        """Poll the servos, broadcast frames and run the downlink tick."""
        period = 1.0 / self._rate if self._rate > 0 else 0.033
        while rclpy.ok():
            start = time.monotonic()
            with self._tcp_lock:
                has_tcp_clients = bool(self._tcp_clients)
            if has_tcp_clients:
                frame = self._read_frame()
                if frame is not None:
                    self._stalled_since = 0.0
                    self._publish_frame(frame)
                else:
                    self._warn_stalled()
            self._control_tick()
            elapsed = time.monotonic() - start
            if elapsed < period:
                time.sleep(period - elapsed)

    def _warn_stalled(self):
        """Warn when clients are connected but no frame can be produced."""
        now = time.monotonic()
        if not self._stalled_since:
            self._stalled_since = now
            return
        if now - self._stalled_since < 2.0 or now - self._stall_warn < 5.0:
            return
        self._stall_warn = now
        if not self._state_client.service_is_ready():
            reason = ('driver service NOT available -> serial port dead? '
                      'CH340 I/O error? is ros_robot_controller running?')
        else:
            reason = ('get_state not answering -> servo power off? serial '
                      'bus busy? multiple readers on the port?')
        self.get_logger().warn(
            'no measured frames for %.1fs while %d client(s) connected: %s'
            % (now - self._stalled_since, len(self._tcp_clients), reason))

    def _read_frame(self):
        """Read all servos once and return one JSON line (bytes) or None."""
        # 同时只允许一个 get_state 在飞：否则超时后继续发新请求会让
        # 响应队列错位（客户端按 FIFO 匹配），最终永久卡死。
        if self._pending is not None:
            if not self._pending.done():
                return None
            self._pending = None        # 上一帧超时的请求终于回来了，丢弃
        if not self._state_client.service_is_ready():
            if not self._state_client.wait_for_service(timeout_sec=0.2):
                return None

        request = GetBusServoState.Request()
        for servo_id in self._ids:
            cmd = GetBusServoCmd()
            cmd.id = servo_id
            cmd.get_position = 1
            request.cmd.append(cmd)

        future = self._state_client.call_async(request)
        self._pending = future
        done = threading.Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=0.5):
            return None
        try:
            response = future.result()
        except Exception as exc:                  # noqa: BLE001
            self.get_logger().warn('get_state call failed: %s' % exc)
            return None
        if response is None:
            return None

        pulses = {}
        for cmd, state in zip(request.cmd, response.state):
            if state.position:
                pulses[int(cmd.id)] = int(state.position[0])

        names = []
        q_rad = []
        q_pulse = []
        for servo_id in self._ids:
            if servo_id not in pulses:
                continue
            info = self._joint_map[servo_id]
            names.append(info['name'])
            q_pulse.append(pulses[servo_id])
            q_rad.append(math.radians(pulse_to_deg(
                pulses[servo_id], info['init'], info['flipped'])))

        self._measured_rad = dict(zip(names, q_rad))
        self._publish_joint_state(names, q_rad)
        self._seq += 1
        frame = {
            't': time.time(),
            'seq': self._seq,
            'names': names,
            'q': [round(value, 6) for value in q_rad],
            'pulse': q_pulse,
        }
        return (json.dumps(frame, separators=(',', ':')) + '\n').encode('ascii')

    def _publish_joint_state(self, names, positions):
        """Publish the measured state as a JointState for local debugging."""
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = names
        msg.position = positions
        self._joint_pub.publish(msg)

    # --------------------------------------------------------------- torque

    def _release_torque_when_ready(self):
        """Wait for the driver to be up, then disable torque on all servos."""
        if not self._init_client.wait_for_service(timeout_sec=15.0):
            self.get_logger().warn(
                'driver init_finish not available; torque not released')
            return
        # publish twice to survive any subscription-matching race
        for _ in range(2):
            self._set_torque(False)
            time.sleep(0.3)

    def destroy_node(self):
        """Release torque if armed, then close the TCP server/clients."""
        if self._safety.armed:
            self.get_logger().warn('shutting down while armed: releasing')
            self._set_torque(False)
            time.sleep(0.2)
        self._closing = True
        with self._frame_cv:
            self._frame_cv.notify_all()
        with self._tcp_lock:
            clients = list(self._tcp_clients)
            self._tcp_clients = []
        for conn in clients:
            try:
                conn.close()
            except OSError:
                pass
        try:
            self._server.close()
        except OSError:
            pass
        super().destroy_node()


def main(args=None):
    """Entry point for the ``dataset_stream`` node."""
    rclpy.init(args=args)
    node = None
    try:
        node = DatasetStream()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
