import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'ros_robot_controller'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*.*'))),
        (os.path.join('share', package_name, 'scripts'), glob(os.path.join('scripts', '*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='u24',
    maintainer_email='u24@todo.todo',
    description='ROS2 driver node for the Hiwonder ros_robot_controller (STM32 main board).',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'ros_robot_controller = ros_robot_controller.ros_robot_controller_node:main',
        ],
    },
)
