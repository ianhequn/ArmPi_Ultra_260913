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
    format_state, parse_command, ProtocolError)
from arm_vofaUDP_bridge.config import load_config
import rclpy
from rclpy.node import Node
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

        config = load_config(self.get_parameter('config_file').value)
        self.declare_parameter('local_ip', config['local_ip'])
        self.declare_parameter('local_port', config['local_port'])
        self.declare_parameter('remote_ip', config['remote_ip'])
        self.declare_parameter('remote_port', config['remote_port'])

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
        """Receive datagrams and dispatch complete lines until shutdown."""
        buffer = b''
        while rclpy.ok():
            try:
                data, addr = self._socket.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError as exc:
                self.get_logger().error('udp recv failed: %s' % exc)
                return
            self._peer = addr
            buffer += data
            # accept both '\n' and '\r' (and '\r\n') as line endings
            while b'\n' in buffer or b'\r' in buffer:
                ends = [i for i in (buffer.find(b'\n'), buffer.find(b'\r'))
                        if i != -1]
                index = min(ends)
                raw, buffer = buffer[:index], buffer[index + 1:]
                line = raw.decode('ascii', errors='ignore').strip()
                if line:
                    self._handle(line, addr)

    def _handle(self, line, addr):
        """Parse and execute one command line, replying to the sender."""
        self.get_logger().info('rx %r' % line)
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
