"""Setup script for the arm_vofaUDP_bridge package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'arm_vofaUDP_bridge'

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
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.json'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='u24',
    maintainer_email='Rui@SZ.com',
    description='UDP bridge between host VOFA+ (RawData ASCII) and /servo_controller.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'vofa_udp_bridge = arm_vofaUDP_bridge.vofa_udp_bridge:main'
        ],
    },
)
