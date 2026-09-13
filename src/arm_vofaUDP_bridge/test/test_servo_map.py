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

"""Unit tests for :mod:`arm_vofaUDP_bridge.servo_map`."""

from arm_vofaUDP_bridge.servo_map import load_joint_map, pulse_to_deg
import pytest


def test_pulse_to_deg_center():
    assert pulse_to_deg(500, 500, False) == pytest.approx(0.0)


def test_pulse_to_deg_span():
    assert pulse_to_deg(1000, 500, False) == pytest.approx(120.0)


def test_pulse_to_deg_flipped():
    assert pulse_to_deg(1000, 500, True) == pytest.approx(-120.0)


def test_load_joint_map(tmp_path):
    path = tmp_path / 'c.yaml'
    path.write_text(
        '/**:\n'
        '  ros__parameters:\n'
        '    joint1:\n'
        '      id: 6\n      init: 500\n      min: 0\n      max: 1000\n'
        '    joint3:\n'
        '      id: 4\n      init: 500\n      min: 1000\n      max: 500\n'
        '    arm_controller:\n'
        '      joint_controllers:\n        - "joint1"\n')
    mapping = load_joint_map(str(path))
    assert len(mapping) == 2
    assert mapping[6]['name'] == 'joint1'
    assert mapping[6]['flipped'] is False
    assert mapping[4]['flipped'] is True
    assert mapping[4]['min'] == 500 and mapping[4]['max'] == 1000
