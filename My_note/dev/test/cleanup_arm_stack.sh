#!/bin/bash
# 清理机械臂 ROS2 栈的所有残留进程（Ctrl+C 没退干净 / 端口被占时用）。
#
#   ./cleanup_arm_stack.sh
#
# 注意：不要在命令行里直接写 "pkill -f dataset_stream" —— 那个 shell 自己的
# 命令行也含这个字符串，会把自己一起杀掉。本脚本用 ps+awk 规避了这点。
PIDS=$(ps -eo pid,cmd \
  | grep -E "ros2 launch|dataset_stream|servo_controller/lib|ros_robot_controller/lib" \
  | grep -v cleanup_arm_stack \
  | awk '{print $1}')

if [ -z "$PIDS" ]; then
  echo "没有残留进程"
else
  echo "清理: $PIDS"
  kill -9 $PIDS 2>/dev/null
fi

sleep 2
echo "--- 端口 1348 ---"
if command -v ss >/dev/null; then
  ss -ltnp 2>/dev/null | grep 1348 || echo "  空闲"
fi
echo "--- 剩余进程 ---"
ps -eo pid,cmd | grep -E "[r]os2 launch|[d]ataset_stream|[s]ervo_controller/lib|[r]os_robot_controller/lib" \
  || echo "  无"
