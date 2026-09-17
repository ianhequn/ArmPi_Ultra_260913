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

"""Unit tests for the pure downlink helpers (no ROS, no hardware)."""

from arm_lerobot_dataset_stream.downlink import (
    extract_targets, parse_line, SafetyState)


def test_parse_line_accepts_known_command():
    """A well formed line is decoded into a dict."""
    msg = parse_line(b'{"cmd":"joints","names":["joint1"],"q":[0.5]}')
    assert msg['cmd'] == 'joints'


def test_parse_line_rejects_unusable_lines():
    """Garbage, non-dict JSON and unknown verbs all return None."""
    assert parse_line(b'not json') is None
    assert parse_line(b'[1, 2]') is None
    assert parse_line(b'{"cmd":"fly"}') is None
    assert parse_line(b'{"no":"cmd"}') is None
    assert parse_line(b'\xff\xfe') is None


def test_extract_targets_filters_bad_channels():
    """Unknown names and bad values are skipped, good ones survive."""
    msg = {
        'names': ['joint1', 'nope', 'joint2', 'joint3', 'joint4'],
        'q': [0.1, 0.2, 'x', float('nan'), float('inf')],
    }
    out = extract_targets(msg, {'joint1', 'joint2', 'joint3', 'joint4'})
    assert out == {'joint1': 0.1}


def test_extract_targets_handles_missing_fields():
    """A joints command without names/q yields no targets."""
    assert extract_targets({'cmd': 'joints'}, {'joint1'}) == {}


def test_safety_state_lifecycle():
    """IDLE -> ARMED -> SAFE -> IDLE, with a working watchdog."""
    state = SafetyState(0.3)
    assert state.state == SafetyState.IDLE
    assert not state.armed

    assert state.arm(10.0) is True
    assert state.armed
    assert state.arm(10.1) is False
    assert not state.timed_out(10.2)
    assert state.timed_out(10.5)

    state.touch(20.0)
    assert not state.timed_out(20.1)

    state.safe()
    assert state.state == SafetyState.SAFE
    assert not state.timed_out(99.0)

    state.idle()
    assert state.state == SafetyState.IDLE
