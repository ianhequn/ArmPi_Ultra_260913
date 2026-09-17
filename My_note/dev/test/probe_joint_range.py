#!/usr/bin/env python3
"""
Hand-probe the mechanical pulse range of every arm servo.

Usage
-----
1. STOP any running launch (the driver owns /dev/ttyUSB0).
2. Run this script.
3. It prints each servo's internal angle limit (register 0x32), then
   RELEASES TORQUE so the arm is free to move by hand.
4. Push each joint slowly to BOTH mechanical stops (a few times).
5. Press Ctrl+C: it prints the min/max pulse reached per joint.

Interpretation
--------------
* The servo's internal limit (hard limit, lives in the servo) protects the
  hardware even if ROS sends something silly.
* ``servo_controller.yaml`` min/max is the ROS-side soft limit.
* Hand-moving is done with torque OFF: the internal limit does NOT stop you,
  so the range you reach is the *pure mechanical* range.
* If a joint reaches pulses outside its yaml range, the yaml is too narrow
  and replay of that joint would be clipped.
"""

import sys
import time

sys.path.insert(
    0,
    '/home/u24/MyTest/dev01/ros2/test_ws01/install/ros_robot_controller'
    '/lib/python3.12/site-packages')
from ros_robot_controller.ros_robot_controller_sdk import Board  # noqa: E402

DEVICE = '/dev/ttyUSB0'
BAUDRATE = 1000000

# servo_id, joint name, yaml min, yaml max (from servo_controller.yaml)
SERVOS = [
    (1, 'r_joint', 0, 1000),
    (2, 'joint5', 0, 1000),
    (3, 'joint4', 0, 1000),
    (4, 'joint3', 1000, 500),   # flipped: min > max
    (5, 'joint2', 0, 1000),
    (6, 'joint1', 0, 1000),
]


def read_position(board, servo_id):
    """Return the pulse of one servo (or None on a failed read)."""
    value = board.bus_servo_read_position(servo_id)
    return None if not value else int(value[0])


def main():
    """Print hard limits, release torque, then track the hand-moved range."""
    board = Board(DEVICE, BAUDRATE)
    low = {servo_id: 10000 for servo_id, *_ in SERVOS}
    high = {servo_id: -1 for servo_id, *_ in SERVOS}
    try:
        board.enable_reception()
        time.sleep(1.0)

        print('== servo internal angle limit (register 0x32) ==', flush=True)
        for servo_id, name, *_ in SERVOS:
            limit = board.bus_servo_read_angle_limit(servo_id)
            print('  id=%d %-8s %s' % (servo_id, name, limit), flush=True)

        print('== releasing torque (arm becomes movable by hand) ==', flush=True)
        for servo_id, *_ in SERVOS:
            board.bus_servo_enable_torque(servo_id, False)
        time.sleep(0.5)

        print('Move every joint to BOTH mechanical stops. Ctrl+C to finish.',
              flush=True)
        count = 0
        while True:
            line = []
            for servo_id, name, *_ in SERVOS:
                value = read_position(board, servo_id)
                if value is None:
                    continue
                low[servo_id] = min(low[servo_id], value)
                high[servo_id] = max(high[servo_id], value)
                line.append('%s=%d[%d..%d]'
                            % (name, value, low[servo_id], high[servo_id]))
            count += 1
            if count % 5 == 0:
                print('  ' + '  '.join(line), flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    except Exception as exc:                      # noqa: BLE001
        print('error: %s' % exc, flush=True)
    finally:
        print('\n== reached range (min..max pulse) ==', flush=True)
        for servo_id, name, ymin, ymax in SERVOS:
            if high[servo_id] < 0:
                print('  %-8s (no reading)' % name, flush=True)
                continue
            span = high[servo_id] - low[servo_id]
            note = ' (not moved)' if span < 50 else ''
            print('  %-8s %4d..%4d   span=%4d   yaml=[%d,%d]%s'
                  % (name, low[servo_id], high[servo_id], span, ymin, ymax,
                     note), flush=True)
        try:
            board.port.close()
        except Exception:                          # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
