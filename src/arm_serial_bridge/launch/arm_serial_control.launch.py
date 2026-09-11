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

"""Launch the full arm control chain: driver + gateway + serial bridge."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription, LaunchService
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Return the launch description for the arm serial control chain."""
    arm_device = LaunchConfiguration('arm_device')
    arm_device_arg = DeclareLaunchArgument(
        'arm_device',
        default_value='/dev/ttyUSB0',
        description='Serial device of the STM32 board '
                    '(e.g. /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0)')

    host_device = LaunchConfiguration('host_device')
    host_device_arg = DeclareLaunchArgument(
        'host_device',
        default_value='/dev/ttyS0',
        description='Serial device connected to the host machine')

    driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_robot_controller'),
            'launch', 'ros_robot_controller.launch.py')),
        launch_arguments={'device': arm_device}.items())

    gateway = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('servo_controller'),
            'launch', 'servo_controller.launch.py')))

    bridge = Node(
        package='arm_serial_bridge',
        executable='serial_bridge',
        output='screen',
        parameters=[{'device': host_device}])

    return LaunchDescription([
        arm_device_arg,
        host_device_arg,
        driver,
        gateway,
        bridge,
    ])


if __name__ == '__main__':
    ld = generate_launch_description()

    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()
