import sys, time
sys.path.insert(0, '/home/u24/MyTest/dev01/ros2/test_ws01/install/ros_robot_controller/lib/python3.12/site-packages')
import time as _t; _t.sleep(2)
from ros_robot_controller.ros_robot_controller_sdk import Board
b = Board('/dev/ttyUSB0', 1000000)
b.enable_reception(); time.sleep(1.0)
print('id : pos : vin(mV) : temp(C)', flush=True)
for sid in [1,2,3,4,5,6]:
    try:
        pos = b.bus_servo_read_position(sid)
        vin = b.bus_servo_read_vin(sid)
        tmp = b.bus_servo_read_temp(sid)
        print(f'{sid} : {pos} : {vin} : {tmp}', flush=True)
    except Exception as e:
        print(f'{sid} : ERR {e}', flush=True)
    time.sleep(0.05)
try: b.port.close()
except Exception: pass
