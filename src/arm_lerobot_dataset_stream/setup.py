"""Setup script for the arm_lerobot_dataset_stream package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'arm_lerobot_dataset_stream'

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
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='u24',
    maintainer_email='Rui@SZ.com',
    description='Stream measured arm joint states over TCP JSON for LeRobot.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'dataset_stream = arm_lerobot_dataset_stream.dataset_stream:main'
        ],
    },
)
