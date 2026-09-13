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
UDP bridge between the host VOFA+ (RawData ASCII) and the arm gateway.

This is the serial bridge with the transport replaced by UDP; the command
protocol is identical:

    host --UDP ASCII--> vofa_udp_bridge --/servo_controller(deg)-->
    servo_controller --> ros_robot_controller --> STM32

Replies go back to whoever sent the command.  Network addresses/ports are
read from a JSON file (see :mod:`arm_vofaUDP_bridge.config`).
"""

import os
import socket
import threading

from ament_index_python.packages import get_package_share_directory
from arm_serial_bridge.protocol import (
    format_state, NAME_ORDER, NAME_TO_CMD, parse_command, ProtocolError,
    split_commands)
from arm_vofaUDP_bridge.config import load_config
from arm_vofaUDP_bridge.servo_map import load_joint_map, pulse_to_deg
import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import (
    BusServoState, GetBusServoCmd, SetBusServoState)
from ros_robot_controller_msgs.srv import GetBusServoState
from sensor_msgs.msg import JointState
from servo_controller_msgs.msg import ServoPosition, ServosPosition


class VofaUdpBridge(Node):
    """Bridge between VOFA+ (UDP/ASCII) and ``/servo_controller``."""

    def __init__(self):
        """Load the config, open the UDP socket and start the receiver."""
        super().__init__('vofa_udp_bridge')

        self.declare_parameter('config_file', self._default_config_file())
        self.declare_parameter('default_duration', 0.5)
        self.declare_parameter('state_rate_hz', 0.0)
        self.declare_parameter('servo_config', self._default_servo_config())

        config = load_config(self.get_parameter('config_file').value)
        self.declare_parameter('local_ip', config['local_ip'])
        self.declare_parameter('local_port', config['local_port'])
        self.declare_parameter('remote_ip', config['remote_ip'])
        self.declare_parameter('remote_port', config['remote_port'])

        self._joint_map = load_joint_map(
            self.get_parameter('servo_config').value)

        local_ip = self.get_parameter('local_ip').value
        local_port = int(self.get_parameter('local_port').value)
        remote_ip = self.get_parameter('remote_ip').value
        remote_port = int(self.get_parameter('remote_port').value)
        self._default_duration = self.get_parameter('default_duration').value
        state_rate = self.get_parameter('state_rate_hz').value

        self._remote = (remote_ip, remote_port)
        self._peer = None
        self._joint_states = {}
        self._send_lock = threading.Lock()

        self._publisher = self.create_publisher(
            ServosPosition, 'servo_controller', 1)
        self._state_pub = self.create_publisher(
            SetBusServoState, 'ros_robot_controller/bus_servo/set_state', 10)
        self._state_client = self.create_client(
            GetBusServoState,
            'ros_robot_controller/bus_servo/get_state')
        self.create_subscription(
            JointState, 'controller_manager/joint_states',
            self._on_joint_state, 1)

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((local_ip, local_port))
        self._socket.settimeout(0.2)
        self.get_logger().info(
            'vofa_udp_bridge %s:%d -> %s:%d (RawData ASCII)'
            % (local_ip, local_port, remote_ip, remote_port))

        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True)
        self._recv_thread.start()

        if state_rate > 0.0:
            self.create_timer(1.0 / state_rate, self._push_state)

    @staticmethod
    def _default_config_file():
        """Return the installed default JSON config path (or empty)."""
        try:
            share = get_package_share_directory('arm_vofaUDP_bridge')
        except Exception:
            return ''
        return os.path.join(share, 'config', 'vofa_udp.json')

    @staticmethod
    def _default_servo_config():
        """Return the installed servo_controller YAML path (or empty)."""
        try:
            share = get_package_share_directory('servo_controller')
        except Exception:
            return ''
        return os.path.join(share, 'config', 'servo_controller.yaml')

    # ---------------------------------------------------------------- ROS

    def _on_joint_state(self, msg):
        """Cache the latest joint positions (rad) for the ``Q`` command."""
        for name, position in zip(msg.name, msg.position):
            self._joint_states[name] = position

    def _publish_targets(self, targets, duration):
        """Publish one ``ServosPosition`` (unit=deg) message."""
        msg = ServosPosition()
        msg.duration = float(duration)
        msg.position_unit = 'deg'
        for target in targets:
            servo = ServoPosition()
            servo.id = target['id']
            servo.position = float(target['deg'])
            msg.position.append(servo)
        self._publisher.publish(msg)

    # ---------------------------------------------------------------- UDP

    def _send(self, text, addr=None):
        """Send one ASCII line to a peer (or the configured remote)."""
        target = addr or self._peer or self._remote
        with self._send_lock:
            try:
                self._socket.sendto((text + '\n').encode('ascii'), target)
            except OSError as exc:
                self.get_logger().error('udp send failed: %s' % exc)

    def _recv_loop(self):
        """Receive datagrams and dispatch every command they contain."""
        while rclpy.ok():
            try:
                data, addr = self._socket.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError as exc:
                self.get_logger().error('udp recv failed: %s' % exc)
                return
            self._peer = addr
            # RawData has no separator: split glued commands here
            text = data.decode('ascii', errors='ignore')
            for command in split_commands(text):
                self._handle(command, addr)

    def _handle(self, line, addr):
        """Parse and execute one command line, replying to the sender."""
        self.get_logger().info('rx %r' % line)
        verb = line.split()[0].upper()
        if verb == 'R':
            self._read_measured(addr)
            return
        if verb in ('L', 'E'):
            self._set_torque(addr, enable=(verb == 'E'))
            return
        try:
            command = parse_command(line, self._default_duration)
        except ProtocolError as exc:
            self.get_logger().warn('bad command %r: %s' % (line, exc))
            self._send('ERR %s' % exc, addr)
            return

        op = command['op']
        if op == 'PING':
            self._send('PONG', addr)
            return
        if op == 'Q':
            self._send(format_state(self._joint_states), addr)
            return

        self._publish_targets(command['targets'], command['duration'])
        self.get_logger().info('exec %r' % line)
        self._send('OK %s' % line, addr)

    def _push_state(self):
        """Periodically push the arm state to the configured remote."""
        self._send(format_state(self._joint_states))

    def _read_measured(self, addr):
        """Read real servo positions and reply ``MEAS J1=.. ..`` (degrees)."""
        if not self._state_client.service_is_ready():
            if not self._state_client.wait_for_service(timeout_sec=0.5):
                self._send('ERR get_state_unavailable', addr)
                return

        request = GetBusServoState.Request()
        for servo_id in sorted(self._joint_map):
            cmd = GetBusServoCmd()
            cmd.id = servo_id
            cmd.get_position = 1
            request.cmd.append(cmd)

        future = self._state_client.call_async(request)
        done = threading.Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=1.0):
            self._send('ERR read_timeout', addr)
            return
        response = future.result()
        if response is None:
            self._send('ERR read_failed', addr)
            return

        readings = {}
        for cmd, state in zip(request.cmd, response.state):
            info = self._joint_map.get(int(cmd.id))
            if info is None or not state.position:
                continue
            readings[info['name']] = pulse_to_deg(
                int(state.position[0]), info['init'], info['flipped'])
        parts = ['%s=%.1f' % (NAME_TO_CMD[name], readings[name])
                 for name in NAME_ORDER if name in readings]
        if not parts:
            self._send('ERR no_reading', addr)
            return
        self._send('MEAS ' + ' '.join(parts), addr)

    def _set_torque(self, addr, enable):
        """Enable/disable torque (hold/loose) on every mapped servo."""
        msg = SetBusServoState()
        for servo_id in sorted(self._joint_map):
            state = BusServoState()
            state.present_id = [1, servo_id]
            state.enable_torque = [1, 1 if enable else 0]
            msg.state.append(state)
        self._state_pub.publish(msg)
        self.get_logger().info(
            'torque %s on %d servos'
            % ('on' if enable else 'off', len(self._joint_map)))
        self._send('OK %s' % ('E' if enable else 'L'), addr)

    def destroy_node(self):
        """Close the UDP socket before shutting the node down."""
        socket_ = getattr(self, '_socket', None)
        if socket_ is not None:
            try:
                socket_.close()
            except OSError:
                pass
        super().destroy_node()


def main(args=None):
    """Entry point for the ``vofa_udp_bridge`` node."""
    rclpy.init(args=args)
    node = None
    try:
        node = VofaUdpBridge()
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
