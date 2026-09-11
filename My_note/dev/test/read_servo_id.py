import sys, time
sys.path.insert(0, '/home/u24/MyTest/dev01/ros2/test_ws01/install/ros_robot_controller/lib/python3.12/site-packages')
from ros_robot_controller.ros_robot_controller_sdk import Board
print('opening /dev/ttyUSB0 @ 1000000 ...', flush=True)
b = Board('/dev/ttyUSB0', 1000000)
print('opened; enable reception', flush=True)
b.enable_reception()
time.sleep(1.0)
for sid in [1, 2, 3, 4, 5, 6]:
    try:
        r = b.bus_servo_read_id(sid)
        print(f'servo {sid}: read_id -> {r}', flush=True)
    except Exception as e:
        print(f'servo {sid}: ERR {e}', flush=True)
    time.sleep(0.1)
try:
    b.port.close()
except Exception:
    pass
print('done', flush=True)
