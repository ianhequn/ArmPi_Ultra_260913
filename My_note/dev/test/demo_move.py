import os, subprocess, signal, time, sys
env = dict(os.environ); env['PYTHONUNBUFFERED'] = '1'
log = open('/tmp/rrc.log', 'w')
proc = subprocess.Popen(['ros2', 'run', 'ros_robot_controller', 'ros_robot_controller'],
                        stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
TARGET_ID, DELTA = 5, 30
try:
    time.sleep(6)
    import rclpy
    from rclpy.node import Node
    from ros_robot_controller_msgs.msg import ServosPosition, ServoPosition
    from ros_robot_controller_msgs.srv import GetBusServoState
    from ros_robot_controller_msgs.msg import GetBusServoCmd
    rclpy.init()
    n = Node('demo_move_client')
    pub = n.create_publisher(ServosPosition, '/ros_robot_controller/bus_servo/set_position', 1)
    cli = n.create_client(GetBusServoState, '/ros_robot_controller/bus_servo/get_state')
    if not cli.wait_for_service(timeout_sec=5.0):
        print('service not available, abort', flush=True); raise SystemExit(2)

    def read_pos(sid):
        req = GetBusServoState.Request()
        c = GetBusServoCmd(); c.id = sid; c.get_position = 1; req.cmd = [c]
        f = cli.call_async(req); rclpy.spin_until_future_complete(n, f, timeout_sec=3.0)
        r = f.result()
        return (r.state[0].position[0] if (r and r.state and r.state[0].position) else None)

    def move(sid, pos, dur=0.5):
        m = ServosPosition(); m.duration = float(dur)
        p = ServoPosition(); p.id = sid; p.position = int(pos)
        m.position = [p]
        pub.publish(m)
        rclpy.spin_once(n, timeout_sec=0.1)

    cur = read_pos(TARGET_ID)
    print(f'servo {TARGET_ID} current = {cur}', flush=True)
    if cur is None:
        print('read failed, abort', flush=True); raise SystemExit(3)
    target = cur - DELTA if cur - DELTA >= 150 else cur + DELTA
    print(f'moving {TARGET_ID}: {cur} -> {target} (delta={target-cur:+d}, ~{(target-cur)*0.24:+.1f} deg)', flush=True)
    move(TARGET_ID, target); time.sleep(1.5)
    print(f'  after move pos = {read_pos(TARGET_ID)}', flush=True)
    print(f'return {TARGET_ID} -> {cur}', flush=True)
    move(TARGET_ID, cur); time.sleep(1.5)
    print(f'  after return pos = {read_pos(TARGET_ID)}', flush=True)
    n.destroy_node(); rclpy.shutdown()
finally:
    log.flush()
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT); time.sleep(1)
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception: pass
    log.close()
    print('--- node log (tail) ---'); print(open('/tmp/rrc.log').read()[-600:], flush=True)
