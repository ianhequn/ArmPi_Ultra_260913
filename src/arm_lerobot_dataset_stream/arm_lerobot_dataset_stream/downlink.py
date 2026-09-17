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
Pure downlink logic for LeRobot replay / rollout commands.

Nothing here touches ROS or sockets: it only parses command lines, filters
targets and tracks the safety state, so it can be unit tested on its own.

One JSON object per line, sent by the host on the same TCP connection::

    {"cmd":"joints","names":["joint1",...],"q":[0.21,...],"seq":1,"t":...}
    {"cmd":"arm"} / {"cmd":"disarm"}
    {"cmd":"stop","release":true} / {"cmd":"ping"}

Only ``joints`` actually moves the arm; see the design document
``My_note/dev/stream_docs/lerobot下行控制协议与VM设计.md``.
"""

import json
import math

COMMANDS = ('joints', 'arm', 'disarm', 'stop', 'ping')


def parse_line(raw):
    """
    Decode one downlink line into a command dict.

    Returns ``None`` for anything that is not a known command, so the
    caller can simply count it as a malformed line and keep streaming.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode('utf-8')
        except UnicodeDecodeError:
            return None
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get('cmd') not in COMMANDS:
        return None
    return msg


def extract_targets(msg, joint_names):
    """
    Return ``{joint_name: radians}`` from a ``joints`` command.

    Unknown names, non-numeric values and NaN/Inf entries are skipped, so
    one bad channel never throws away the whole command.
    """
    names = msg.get('names')
    values = msg.get('q')
    if not isinstance(names, list) or not isinstance(values, list):
        return {}
    targets = {}
    for name, value in zip(names, values):
        if name not in joint_names:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(value) or math.isinf(value):
            continue
        targets[name] = value
    return targets


def limit_step(current, target, max_step):
    """Move ``current`` towards ``target`` by at most ``max_step`` rad."""
    delta = target - current
    if delta > max_step:
        return current + max_step
    if delta < -max_step:
        return current - max_step
    return target


def step_for_rate(max_step_rad, max_velocity_rad_s, rate_hz):
    """Return the per-cycle step allowed by the position/velocity limits."""
    if rate_hz <= 0:
        return max_step_rad
    return min(max_step_rad, max_velocity_rad_s / rate_hz)


class SafetyState:
    """Track the IDLE / ARMED / SAFE state and the watchdog deadline."""

    IDLE = 'IDLE'
    ARMED = 'ARMED'
    SAFE = 'SAFE'

    def __init__(self, watchdog_timeout):
        """Start in IDLE with the given watchdog timeout (seconds)."""
        self.watchdog_timeout = float(watchdog_timeout)
        self.state = self.IDLE
        self.last_command_time = 0.0

    @property
    def armed(self):
        """Return True while joint targets are being executed."""
        return self.state == self.ARMED

    def touch(self, now):
        """Refresh the watchdog without changing the state."""
        self.last_command_time = now

    def arm(self, now):
        """Enter ARMED and refresh the watchdog; True when it changed."""
        changed = self.state != self.ARMED
        self.state = self.ARMED
        self.last_command_time = now
        return changed

    def idle(self):
        """Enter IDLE (torque released, arm loose, safe for hand guiding)."""
        self.state = self.IDLE

    def safe(self):
        """Enter SAFE (stop sending until a new command arrives)."""
        self.state = self.SAFE

    def timed_out(self, now):
        """Return True when ARMED but no command arrived in time."""
        return (self.state == self.ARMED
                and now - self.last_command_time > self.watchdog_timeout)
