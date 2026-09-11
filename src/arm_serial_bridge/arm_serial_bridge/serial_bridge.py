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

"""
ROS 2 node bridging a serial ASCII link to the arm semantic gateway.

Data flow (VM side):

    host --serial--> serial_bridge --/servo_controller(ServosPosition,deg)-->
    servo_controller --> ros_robot_controller --> STM32

The host sends one command per line (see :mod:`arm_serial_bridge.protocol`).
The node never talks to the arm directly; it only republishes on the
existing ``/servo_controller`` topic, keeping control logic in one place.
"""

import threading

from arm_serial_bridge.protocol import (
    format_state, parse_command, ProtocolError)
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
import serial
from servo_controller_msgs.msg import ServoPosition, ServosPosition


class SerialBridge(Node):
    """Bridge between the host serial link and ``/servo_controller``."""

    def __init__(self):
        """Declare parameters, open the port and start the reader thread."""
        super().__init__('serial_bridge')
        self.declare_parameter('device', '/dev/ttyS0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('default_duration', 0.5)
        self.declare_parameter('read_timeout', 0.2)

        device = self.get_parameter('device').value
        baudrate = self.get_parameter('baudrate').value
        self._default_duration = self.get_parameter('default_duration').value
        read_timeout = self.get_parameter('read_timeout').value

        self._joint_states = {}
        self._write_lock = threading.Lock()

        self._publisher = self.create_publisher(
            ServosPosition, 'servo_controller', 1)
        self.create_subscription(
            JointState, 'controller_manager/joint_states',
            self._on_joint_state, 1)

        self._serial = serial.Serial(device, baudrate, timeout=read_timeout)
        self.get_logger().info(
            'serial_bridge on %s @ %d, publishing /servo_controller'
            % (device, baudrate))

        self._read_thread = threading.Thread(
            target=self._read_loop, daemon=True)
        self._read_thread.start()

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

    # ------------------------------------------------------------- serial

    def _send(self, text):
        """Write one reply line to the host (thread-safe)."""
        with self._write_lock:
            self._serial.write((text + '\n').encode('ascii'))

    def _read_loop(self):
        """Read command lines from the host until the node shuts down."""
        while rclpy.ok():
            try:
                raw = self._serial.readline()
            except serial.SerialException as exc:
                self.get_logger().error('serial read failed: %s' % exc)
                return
            if not raw:
                continue
            line = raw.decode('ascii', errors='ignore').strip()
            if line:
                self._handle(line)

    def _handle(self, line):
        """Parse and execute one command line, replying to the host."""
        try:
            command = parse_command(line, self._default_duration)
        except ProtocolError as exc:
            self.get_logger().warn('bad command %r: %s' % (line, exc))
            self._send('ERR %s' % exc)
            return

        op = command['op']
        if op == 'PING':
            self._send('PONG')
            return
        if op == 'Q':
            self._send(format_state(self._joint_states))
            return

        self._publish_targets(command['targets'], command['duration'])
        self.get_logger().info('exec %r' % line)
        self._send('OK %s' % line)


def main(args=None):
    """Entry point for the ``serial_bridge`` node."""
    rclpy.init(args=args)
    node = None
    try:
        node = SerialBridge()
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
