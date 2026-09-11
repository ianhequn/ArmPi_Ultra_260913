"""Setup script for the arm_serial_bridge package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'arm_serial_bridge'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
        (os.path.join('share', package_name, 'scripts'),
            glob(os.path.join('scripts', '*.py'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='u24',
    maintainer_email='Rui@SZ.com',
    description='Serial ASCII bridge from the host machine to /servo_controller.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'serial_bridge = arm_serial_bridge.serial_bridge:main'
        ],
    },
)
