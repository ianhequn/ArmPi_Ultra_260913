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
Pure parsing/formatting for the host<->VM serial protocol.

No ROS and no pyserial imports here, so this module is unit-testable in
isolation.  Protocol: one ASCII command per line, terminated by '\\n'.

    PING                     -> PONG
    Q                        -> STATE J1=.. J2=.. ...
    H                        -> OK H              (home, all joints 0 deg)
    A J5 23.3                -> OK A J5 23.3      (one joint, deg)
    A J1 10 J5 40 T 800      -> OK ...            (multi joint, 800 ms)

Joint tokens: J1..J5 and G (gripper) or numeric 1..6.
"""

import math

# Short command name -> servo bus id (must match servo_controller.yaml)
JOINT_TO_ID = {
    'J1': 6,
    'J2': 5,
    'J3': 4,
    'J4': 3,
    'J5': 2,
    'G': 1,
}

# Controller joint name -> short command name
NAME_TO_CMD = {
    'joint1': 'J1',
    'joint2': 'J2',
    'joint3': 'J3',
    'joint4': 'J4',
    'joint5': 'J5',
    'r_joint': 'G',
}

# Order used when formatting the STATE reply
NAME_ORDER = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'r_joint']

# Numeric aliases: '1'..'5' -> J1..J5, '6' -> G
_NUMERIC_ALIAS = {
    '1': 'J1', '2': 'J2', '3': 'J3', '4': 'J4', '5': 'J5', '6': 'G',
}


class ProtocolError(ValueError):
    """Raised when a command line cannot be parsed."""


def resolve_joint(token):
    """Return ``(command_name, servo_id)`` for a joint token."""
    key = token.upper()
    key = _NUMERIC_ALIAS.get(key, key)
    if key not in JOINT_TO_ID:
        raise ProtocolError('unknown_joint ' + token)
    return key, JOINT_TO_ID[key]


def parse_command(line, default_duration=0.5):
    """
    Parse one ASCII command line into a dict.

    Returns a dict with an ``op`` key ('PING', 'Q' or 'SET').  ``SET``
    carries ``duration`` (s) and ``targets`` (``joint``/``deg``/``id``).
    Raises :class:`ProtocolError` on bad input.
    """
    tokens = line.strip().split()
    if not tokens:
        raise ProtocolError('empty')

    op = tokens[0].upper()
    if op == 'PING':
        return {'op': 'PING'}
    if op == 'Q':
        return {'op': 'Q'}
    if op == 'H':
        targets = [{'joint': name, 'deg': 0.0, 'id': servo_id}
                   for name, servo_id in JOINT_TO_ID.items()]
        return {'op': 'SET', 'duration': default_duration,
                'targets': targets}
    if op != 'A':
        raise ProtocolError('unknown_cmd ' + tokens[0])

    duration = default_duration
    targets = []
    i = 1
    while i < len(tokens):
        if tokens[i].upper() == 'T':
            if i + 1 >= len(tokens):
                raise ProtocolError('bad_arg T')
            try:
                duration = float(tokens[i + 1]) / 1000.0
            except ValueError:
                raise ProtocolError('bad_arg T ' + tokens[i + 1])
            i += 2
            continue
        if i + 1 >= len(tokens):
            raise ProtocolError('missing_angle ' + tokens[i])
        joint, servo_id = resolve_joint(tokens[i])
        try:
            deg = float(tokens[i + 1])
        except ValueError:
            raise ProtocolError('bad_angle ' + tokens[i + 1])
        targets.append({'joint': joint, 'deg': deg, 'id': servo_id})
        i += 2

    if not targets:
        raise ProtocolError('no_target')
    return {'op': 'SET', 'duration': duration, 'targets': targets}


def format_state(joint_states):
    """Format a ``{joint_name: rad}`` dict as a ``STATE`` reply line."""
    parts = []
    for name in NAME_ORDER:
        if name in joint_states:
            cmd = NAME_TO_CMD[name]
            parts.append('%s=%.1f' % (cmd, math.degrees(joint_states[name])))
    if not parts:
        return 'STATE none'
    return 'STATE ' + ' '.join(parts)
