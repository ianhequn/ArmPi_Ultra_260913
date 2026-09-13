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

r"""
Launch the whole "VOFA+ UDP controls the arm" chain.

Nodes started (in order of data flow):

    vofa_udp_bridge     : VOFA+ UDP ASCII -> /servo_controller (deg)
    servo_controller    : deg/rad/pulse   -> pulse + joint limits
    ros_robot_controller: pulse           -> STM32 over CH340

Network addresses/ports are read from the JSON file given by
``config_file`` (default: the installed ``config/vofa_udp.json``).

    ros2 launch arm_vofaUDP_bridge arm_vofa_control.launch.py
    ros2 launch arm_vofaUDP_bridge arm_vofa_control.launch.py \\
      config_file:=/path/to/my_vofa_udp.json
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
    """Return the launch description for the arm VOFA UDP chain."""
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

    default_config = os.path.join(
        get_package_share_directory('arm_vofaUDP_bridge'),
        'config', 'vofa_udp.json')
    config_file = LaunchConfiguration('config_file')
    config_file_arg = DeclareLaunchArgument(
        'config_file',
        default_value=default_config,
        description='JSON file with local_ip/local_port/remote_ip/remote_port')

    state_rate = LaunchConfiguration('state_rate_hz')
    state_rate_arg = DeclareLaunchArgument(
        'state_rate_hz',
        default_value='0.0',
        description='Periodic STATE push rate to VOFA+ (0 = off)')

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
        package='arm_vofaUDP_bridge',
        executable='vofa_udp_bridge',
        output='screen',
        parameters=[{
            'config_file': config_file,
            'state_rate_hz': ParameterValue(state_rate, value_type=float),
        }])

    return LaunchDescription([
        arm_device_arg,
        arm_baudrate_arg,
        config_file_arg,
        state_rate_arg,
        driver,
        gateway,
        bridge,
    ])


if __name__ == '__main__':
    ld = generate_launch_description()

    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()
