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
"""

import json
import math
import os
import socket
import threading
import time

from ament_index_python.packages import get_package_share_directory
from arm_vofaUDP_bridge.servo_map import load_joint_map, pulse_to_deg
import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import (
    BusServoState, GetBusServoCmd, SetBusServoState)
from ros_robot_controller_msgs.srv import GetBusServoState
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger


class DatasetStream(Node):
    """TCP JSON stream of measured joint states for LeRobot recording."""

    def __init__(self):
        """Read parameters, open the TCP server and start the workers."""
        super().__init__('dataset_stream')
        self.declare_parameter('servo_config', self._default_servo_config())
        self.declare_parameter('poll_rate_hz', 30.0)
        self.declare_parameter('tcp_host', '0.0.0.0')
        self.declare_parameter('tcp_port', 1348)
        self.declare_parameter('release_torque', False)

        self._joint_map = load_joint_map(
            self.get_parameter('servo_config').value)
        # logical order: joint1..joint5, r_joint (alphabetical by name)
        self._ids = sorted(self._joint_map,
                           key=lambda i: self._joint_map[i]['name'])
        self._names = [self._joint_map[i]['name'] for i in self._ids]
        self._rate = float(self.get_parameter('poll_rate_hz').value)
        host = self.get_parameter('tcp_host').value
        port = int(self.get_parameter('tcp_port').value)

        self._tcp_clients = []
        self._tcp_lock = threading.Lock()
        self._seq = 0

        self._state_client = self.create_client(
            GetBusServoState, 'ros_robot_controller/bus_servo/get_state')
        self._init_client = self.create_client(
            Trigger, 'ros_robot_controller/init_finish')
        self._state_pub = self.create_publisher(
            SetBusServoState, 'ros_robot_controller/bus_servo/set_state', 10)
        self._joint_pub = self.create_publisher(
            JointState, '~/joint_states_measured', 10)

        if not self._ids:
            self.get_logger().error('empty joint map (check servo_config)')

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen(5)
        self._server.settimeout(0.5)
        self.get_logger().info(
            'dataset_stream TCP %s:%d @ %.1f Hz, joints=%s'
            % (host, port, self._rate, self._names))

        if self.get_parameter('release_torque').value:
            threading.Thread(
                target=self._release_torque_when_ready, daemon=True).start()

        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._poll_loop, daemon=True).start()

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
        """Accept TCP clients and remember their sockets."""
        while rclpy.ok():
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._tcp_lock:
                self._tcp_clients.append(conn)
            self.get_logger().info('client connected: %s:%d' % addr)

    def _broadcast(self, line):
        """Send one frame to every client, dropping broken ones."""
        with self._tcp_lock:
            clients = list(self._tcp_clients)
        dead = []
        for conn in clients:
            try:
                conn.sendall(line)
            except OSError:
                dead.append(conn)
        if dead:
            with self._tcp_lock:
                for conn in dead:
                    if conn in self._tcp_clients:
                        self._tcp_clients.remove(conn)
                    try:
                        conn.close()
                    except OSError:
                        pass
            self.get_logger().info('dropped %d client(s)' % len(dead))

    # --------------------------------------------------------------- polling

    def _poll_loop(self):
        """Poll the servos and broadcast frames (only if a client is there)."""
        period = 1.0 / self._rate if self._rate > 0 else 0.033
        while rclpy.ok():
            start = time.monotonic()
            with self._tcp_lock:
                has_tcp_clients = bool(self._tcp_clients)
            if has_tcp_clients:
                frame = self._read_frame()
                if frame is not None:
                    self._broadcast(frame)
            elapsed = time.monotonic() - start
            if elapsed < period:
                time.sleep(period - elapsed)

    def _read_frame(self):
        """Read all servos once and return one JSON line (bytes) or None."""
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
        done = threading.Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=0.5):
            return None
        response = future.result()
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
            self._release_torque()
            time.sleep(0.3)

    def _release_torque(self):
        """Disable torque on every mapped servo (for hand-guided recording)."""
        msg = SetBusServoState()
        for servo_id in self._ids:
            state = BusServoState()
            state.present_id = [1, servo_id]
            state.enable_torque = [1, 0]
            msg.state.append(state)
        self._state_pub.publish(msg)
        self.get_logger().info('torque released on %d servos' % len(self._ids))

    def destroy_node(self):
        """Close the TCP server and every client socket."""
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
