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

"""
Load the UDP network configuration from a JSON file.

The file only needs the four keys below; missing keys fall back to the
defaults.  Example:

    {
      "local_ip": "0.0.0.0",
      "local_port": 1347,
      "remote_ip": "192.168.174.1",
      "remote_port": 1347
    }
"""

import json
import os

DEFAULTS = {
    'local_ip': '0.0.0.0',
    'local_port': 1347,
    'remote_ip': '127.0.0.1',
    'remote_port': 1347,
}

KEYS = tuple(DEFAULTS)


def load_config(path):
    """
    Return the UDP config dict, with defaults filled in.

    Missing or unreadable files simply yield the defaults.
    """
    config = dict(DEFAULTS)
    if not path or not os.path.isfile(path):
        return config

    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)

    for key in KEYS:
        if key in data:
            config[key] = data[key]

    config['local_port'] = int(config['local_port'])
    config['remote_port'] = int(config['remote_port'])
    return config
