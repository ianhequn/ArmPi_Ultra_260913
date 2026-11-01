#!/usr/bin/env bash
# SCL 驱动一键启动（VM 侧）：设发现环境 + 起驱动，发布 /scan
source /opt/ros/jazzy/setup.bash
source /home/u24/MyTest/dev01/ros2/test_ws01/scripts/ros_discovery_env.sh 10.144.144.3
source /home/u24/MyTest/dev01/ros2/test_ws01/install/setup.bash

ros2 launch ydlidar_ros2_driver ydlidar_launch.py \
  params_file:=/home/u24/MyTest/dev01/ros2/test_ws01/src/ydlidar_ros2_driver/params/SCL.yaml
