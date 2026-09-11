from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch import LaunchDescription, LaunchService
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    device = LaunchConfiguration('device')
    device_arg = DeclareLaunchArgument(
        'device',
        default_value='/dev/ttyUSB0',
        description='Serial device of the STM32 board '
                    '(e.g. /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0)')

    baudrate = LaunchConfiguration('baudrate')
    baudrate_arg = DeclareLaunchArgument(
        'baudrate',
        default_value='1000000',
        description='Serial baudrate')

    ros_robot_controller_node = Node(
        package='ros_robot_controller',
        executable='ros_robot_controller',
        parameters=[{
            'device': device,
            'baudrate': ParameterValue(baudrate, value_type=int),
        }],
        output='screen',
    )

    return LaunchDescription([
        device_arg,
        baudrate_arg,
        ros_robot_controller_node,
    ])


if __name__ == '__main__':
    ld = generate_launch_description()

    ls = LaunchService()
    ls.include_launch_description(ld)
    ls.run()
