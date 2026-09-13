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

"""Unit tests for :mod:`arm_vofaUDP_bridge.config`."""

import json

from arm_vofaUDP_bridge.config import DEFAULTS, load_config


def test_defaults_when_missing(tmp_path):
    assert load_config(str(tmp_path / 'nope.json')) == DEFAULTS


def test_partial_override(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'remote_ip': '10.0.0.5'}))
    cfg = load_config(str(path))
    assert cfg['remote_ip'] == '10.0.0.5'
    assert cfg['local_port'] == DEFAULTS['local_port']


def test_ports_are_int(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'local_port': '5000', 'remote_port': '5001'}))
    cfg = load_config(str(path))
    assert cfg['local_port'] == 5000
    assert cfg['remote_port'] == 5001


def test_extra_keys_ignored(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'_note': 'hi', 'local_ip': '1.2.3.4'}))
    cfg = load_config(str(path))
    assert cfg['local_ip'] == '1.2.3.4'
    assert '_note' not in cfg
