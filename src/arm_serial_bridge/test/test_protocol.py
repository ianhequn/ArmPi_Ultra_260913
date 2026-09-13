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

"""Unit tests for :mod:`arm_serial_bridge.protocol`."""

import math

from arm_serial_bridge.protocol import (
    format_state, parse_command, ProtocolError, resolve_joint, split_commands)
import pytest


def test_resolve_joint():
    assert resolve_joint('j5') == ('J5', 2)
    assert resolve_joint('G') == ('G', 1)
    assert resolve_joint('2') == ('J2', 5)


def test_resolve_joint_unknown():
    with pytest.raises(ProtocolError):
        resolve_joint('J9')


def test_ping_and_query():
    assert parse_command('PING') == {'op': 'PING'}
    assert parse_command('q') == {'op': 'Q'}


def test_single_target():
    cmd = parse_command('A J5 23.3')
    assert cmd['op'] == 'SET'
    assert cmd['duration'] == 0.5
    assert cmd['targets'] == [{'joint': 'J5', 'deg': 23.3, 'id': 2}]


def test_multi_target_and_duration():
    cmd = parse_command('A J1 10 J5 40 T 800')
    assert cmd['duration'] == 0.8
    assert [t['id'] for t in cmd['targets']] == [6, 2]


def test_home_sets_all_zero():
    cmd = parse_command('H')
    assert len(cmd['targets']) == 6
    assert all(t['deg'] == 0.0 for t in cmd['targets'])


def test_bad_commands():
    for bad in ['', 'X', 'A', 'A J9 1', 'A J5', 'A J5 abc', 'A J5 1 T']:
        with pytest.raises(ProtocolError):
            parse_command(bad)


def test_state_format():
    states = {'joint5': math.radians(23.3), 'r_joint': 0.0}
    assert format_state(states) == 'STATE J5=23.3 G=0.0'


def test_state_empty():
    assert format_state({}) == 'STATE none'


def test_split_normal_command():
    assert split_commands('A J1 10 J5 40 T 800') == ['A J1 10 J5 40 T 800']


def test_split_newlines():
    assert split_commands('PING\nQ\nH') == ['PING', 'Q', 'H']


def test_split_glued_rawdata():
    text = 'A J1 5.9A J1 -12.1A J2 -35.7H'
    assert split_commands(text) == [
        'A J1 5.9', 'A J1 -12.1', 'A J2 -35.7', 'H']


def test_split_glued_duration():
    assert split_commands('A J5 1 T800') == ['A J5 1 T 800']
