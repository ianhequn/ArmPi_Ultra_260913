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
Joint map (servo id -> init/flipped) and pulse -> degree conversion.

The map is read from the same ``servo_controller.yaml`` used by the
semantic gateway, so the conversion stays consistent with the rest of the
system.  ``flipped`` mirrors ``JointPositionController``: a joint is
flipped when its configured ``min`` is greater than ``max``.
"""

import math

import yaml

RADIANS_PER_ENCODER_TICK = 240 / 360 * (math.pi * 2) / 1000


def load_joint_map(path):
    """
    Return ``{servo_id: {'name', 'init', 'flipped', 'min', 'max'}}``.

    Parameter groups without an ``id`` (e.g. controller config) are
    ignored; unreadable paths yield an empty map.
    """
    if not path:
        return {}

    with open(path, 'r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}
    params = data.get('/**', {}).get('ros__parameters', {})

    result = {}
    for name, cfg in params.items():
        if not isinstance(cfg, dict) or 'id' not in cfg:
            continue
        min_raw = int(cfg['min'])
        max_raw = int(cfg['max'])
        result[int(cfg['id'])] = {
            'name': name,
            'init': int(cfg['init']),
            'flipped': min_raw > max_raw,
            'min': min(min_raw, max_raw),
            'max': max(min_raw, max_raw),
        }
    return result


def pulse_to_deg(pulse, init, flipped):
    """Convert a raw servo pulse (0..1000) to degrees."""
    delta = (init - pulse) if flipped else (pulse - init)
    return math.degrees(delta * RADIANS_PER_ENCODER_TICK)
