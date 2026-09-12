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

"""
Launch the whole "serial command controls the arm" chain.

Nodes started (in order of data flow):

    serial_bridge      : host serial ASCII  -> /servo_controller (deg)
    servo_controller   : deg/rad/pulse      -> pulse + joint limits
    ros_robot_controller: pulse             -> STM32 over CH340

Default serial devices assume the adapters are plugged in this order:
    arm  (STM32) plugged first  -> /dev/ttyUSB0  (1000000 baud)
    host link     plugged second -> /dev/ttyUSB1  (115200 baud)

Override on the command line, e.g.:

    ros2 launch arm_serial_bridge arm_serial_control.launch.py \\
      arm_device:=/dev/serial/by-path/pci-0000:02:00.0-usb-0:2.1:1.0-port0 \\
      host_device:=/dev/serial/by-path/pci-0000:02:00.0-usb-0:2.2:1.0-port0
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription, LaunchService
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Return the launch description for the arm serial control chain."""
    arm_device = LaunchConfiguration('arm_device')
    arm_device_arg = DeclareLaunchArgument(
        'arm_device',
        default_value='/dev/ttyUSB0',
        description='Arm (STM32) serial device, e.g. plug arm first -> ttyUSB0')

    arm_baudrate = LaunchConfiguration('arm_baudrate')
    arm_baudrate_arg = DeclareLaunchArgument(
        'arm_baudrate',
        default_value='1000000',
        description='Arm serial baudrate')

    host_device = LaunchConfiguration('host_device')
    host_device_arg = DeclareLaunchArgument(
        'host_device',
        default_value='/dev/ttyUSB1',
        description='Host-link serial device, e.g. plugged second -> ttyUSB1')

    host_baudrate = LaunchConfiguration('host_baudrate')
    host_baudrate_arg = DeclareLaunchArgument(
        'host_baudrate',
        default_value='115200',
        description='Host-link baudrate')

    driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_robot_controller'),
            'launch', 'ros_robot_controller.launch.py')),
        launch_arguments={
            'device': arm_device,
            'baudrate': arm_baudrate,
        }.items())

    gateway = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('servo_controller'),
            'launch', 'servo_controller.launch.py')))

    bridge = Node(
        package='arm_serial_bridge',
        executable='serial_bridge',
        output='screen',
        parameters=[{
            'device': host_device,
            'baudrate': ParameterValue(host_baudrate, value_type=int),
        }])

    return LaunchDescription([
        arm_device_arg,
        arm_baudrate_arg,
        host_device_arg,
        host_baudrate_arg,
        driver,
        gateway,
        bridge,
    ])


if __name__ == '__main__':
    ld = generate_launch_description()

    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()
