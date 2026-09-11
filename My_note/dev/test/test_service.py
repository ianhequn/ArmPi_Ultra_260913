import os, subprocess, signal, time, sys
env = dict(os.environ)
env['PYTHONUNBUFFERED'] = '1'
log = open('/tmp/rrc.log', 'w')
proc = subprocess.Popen(['ros2', 'run', 'ros_robot_controller', 'ros_robot_controller'],
                        stdout=log, stderr=subprocess.STDOUT, env=env,
                        start_new_session=True)
rc = 1
try:
    time.sleep(6)
    import rclpy
    from rclpy.node import Node
    from ros_robot_controller_msgs.srv import GetBusServoState
    from ros_robot_controller_msgs.msg import GetBusServoCmd
    rclpy.init()
    n = Node('verify_client')
    cli = n.create_client(GetBusServoState, '/ros_robot_controller/bus_servo/get_state')
    ok = cli.wait_for_service(timeout_sec=4.0)
    print('service available:', ok, flush=True)
    if ok:
        req = GetBusServoState.Request()
        cmd = GetBusServoCmd(); cmd.id = 1; cmd.get_id = 1; req.cmd = [cmd]
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(n, fut, timeout_sec=3.0)
        res = fut.result()
        val = res.state[0].present_id[0] if (res and res.state and res.state[0].present_id) else None
        print('servo 1 present_id ->', val, flush=True)
        rc = 0
    n.destroy_node(); rclpy.shutdown()
finally:
    log.flush()
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT); time.sleep(1)
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    log.close()
    out = open('/tmp/rrc.log').read()
    print('--- node log (tail) ---', flush=True)
    print(out[-800:], flush=True)
sys.exit(rc)
