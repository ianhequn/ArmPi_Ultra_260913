#!/usr/bin/env bash
# 本机查看 /scan（VM 侧）：设同样的发现环境后持续 echo
source /opt/ros/jazzy/setup.bash
source /home/u24/MyTest/dev01/ros2/test_ws01/scripts/ros_discovery_env.sh 10.144.144.3
source /home/u24/MyTest/dev01/ros2/test_ws01/install/setup.bash

ros2 topic echo /scan sensor_msgs/msg/LaserScan
