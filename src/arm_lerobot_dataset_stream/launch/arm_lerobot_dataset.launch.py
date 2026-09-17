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
Launch the LeRobot dataset chain: driver + gateway + TCP JSON stream.

Nodes started:

    dataset_stream      : measured joints -> TCP newline JSON (for the host)
    servo_controller    : semantic gateway (deg/rad/pulse -> pulse)
    ros_robot_controller: pulse -> STM32 over CH340

The host (Windows/LeRobot) connects with a plain TCP client to
``<vm-ip>:<tcp_port>`` and reads one JSON line per sample.

    ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py
    ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py \\
      tcp_port:=1348 poll_rate_hz:=30.0 release_torque:=true

Replay (host drives the arm) additionally needs ``enable_downlink:=true``::

    ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py \\
      enable_downlink:=true
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
    """Return the launch description for the dataset streaming chain."""
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

    tcp_port = LaunchConfiguration('tcp_port')
    tcp_port_arg = DeclareLaunchArgument(
        'tcp_port',
        default_value='1348',
        description='TCP port the host LeRobot client connects to')

    poll_rate = LaunchConfiguration('poll_rate_hz')
    poll_rate_arg = DeclareLaunchArgument(
        'poll_rate_hz',
        default_value='30.0',
        description='Measured-state streaming rate (Hz)')

    release_torque = LaunchConfiguration('release_torque')
    release_torque_arg = DeclareLaunchArgument(
        'release_torque',
        default_value='false',
        description='On startup, disable torque (loose arm) for hand guiding')

    enable_downlink = LaunchConfiguration('enable_downlink')
    enable_downlink_arg = DeclareLaunchArgument(
        'enable_downlink',
        default_value='false',
        description='Execute host servo commands (replay); off = recording only')

    max_step_rad = LaunchConfiguration('max_step_rad')
    max_step_rad_arg = DeclareLaunchArgument(
        'max_step_rad',
        default_value='0.5',
        description='Per-cycle position limit while ramping (rad/tick)')

    max_velocity = LaunchConfiguration('max_velocity_rad_s')
    max_velocity_arg = DeclareLaunchArgument(
        'max_velocity_rad_s',
        default_value='15.0',
        description='Velocity limit while ramping (rad/s); raise for replay')

    watchdog = LaunchConfiguration('watchdog_timeout')
    watchdog_arg = DeclareLaunchArgument(
        'watchdog_timeout',
        default_value='1.0',
        description='Seconds without a host command before SAFE (releasing)')

    release_timeout = LaunchConfiguration('release_on_timeout')
    release_timeout_arg = DeclareLaunchArgument(
        'release_on_timeout',
        default_value='true',
        description='Release torque when the watchdog fires')

    release_disconnect = LaunchConfiguration('release_on_disconnect')
    release_disconnect_arg = DeclareLaunchArgument(
        'release_on_disconnect',
        default_value='true',
        description='Release torque when the host disconnects')

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

    stream = Node(
        package='arm_lerobot_dataset_stream',
        executable='dataset_stream',
        output='screen',
        parameters=[{
            'tcp_port': ParameterValue(tcp_port, value_type=int),
            'poll_rate_hz': ParameterValue(poll_rate, value_type=float),
            'release_torque': ParameterValue(release_torque, value_type=bool),
            'enable_downlink': ParameterValue(
                enable_downlink, value_type=bool),
            'max_step_rad': ParameterValue(max_step_rad, value_type=float),
            'max_velocity_rad_s': ParameterValue(
                max_velocity, value_type=float),
            'watchdog_timeout': ParameterValue(
                watchdog, value_type=float),
            'release_on_timeout': ParameterValue(
                release_timeout, value_type=bool),
            'release_on_disconnect': ParameterValue(
                release_disconnect, value_type=bool),
        }])

    return LaunchDescription([
        arm_device_arg,
        arm_baudrate_arg,
        tcp_port_arg,
        poll_rate_arg,
        release_torque_arg,
        enable_downlink_arg,
        max_step_rad_arg,
        max_velocity_arg,
        watchdog_arg,
        release_timeout_arg,
        release_disconnect_arg,
        driver,
        gateway,
        stream,
    ])


if __name__ == '__main__':
    ld = generate_launch_description()

    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()
