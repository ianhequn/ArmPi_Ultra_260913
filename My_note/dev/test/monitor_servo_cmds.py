#!/usr/bin/env python3
"""Log every bus-servo command with a wall-clock timestamp.

Watch this while using the arm; when it "resets" unexpectedly, check
whether a command appeared at that moment.

    source /opt/ros/jazzy/setup.bash
    source install/setup.bash
    python3 My_note/dev/test/monitor_servo_cmds.py
"""

import time

import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import ServosPosition, SetBusServoState

POSITION_TOPIC = '/ros_robot_controller/bus_servo/set_position'
STATE_TOPIC = '/ros_robot_controller/bus_servo/set_state'


class ServoCmdMonitor(Node):
    """Print every position/state command sent to the driver."""

    def __init__(self):
        super().__init__('servo_cmd_monitor')
        self.create_subscription(
            ServosPosition, POSITION_TOPIC, self._on_position, 10)
        self.create_subscription(
            SetBusServoState, STATE_TOPIC, self._on_state, 10)
        self.get_logger().info('monitoring %s and %s' % (
            POSITION_TOPIC, STATE_TOPIC))

    @staticmethod
    def _stamp():
        return time.strftime('%H:%M:%S')

    def _on_position(self, msg):
        """Log a ServosPosition command."""
        items = [(p.id, p.position) for p in msg.position]
        print('%s  SET_POSITION dur=%.3f  %s'
              % (self._stamp(), msg.duration, items), flush=True)

    def _on_state(self, msg):
        """Log a SetBusServoState command."""
        items = [(list(s.present_id), list(s.enable_torque),
                  list(s.stop)) for s in msg.state]
        print('%s  SET_STATE  [present_id, enable_torque, stop] = %s'
              % (self._stamp(), items), flush=True)


def main(args=None):
    """Run the monitor until interrupted."""
    rclpy.init(args=args)
    node = ServoCmdMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
