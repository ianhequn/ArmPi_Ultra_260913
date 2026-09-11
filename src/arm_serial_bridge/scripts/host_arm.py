#!/usr/bin/env python3
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
Send one ASCII command to the arm over the host<->VM serial link.

Run this on the *host* machine (Linux or Windows).  Only ``pyserial`` is
required; no ROS installation needed.

    python3 host_arm.py --device /dev/ttyS0 A J5 23.3
    python3 host_arm.py --device COM5 A J1 10 J5 40 T 800
    python3 host_arm.py Q
"""

import argparse
import sys

import serial


def main(argv=None):
    """Send one command line and print the reply."""
    parser = argparse.ArgumentParser(
        description='Send one command to the arm over a serial link.')
    parser.add_argument('--device', default='/dev/ttyS0',
                        help='serial device, e.g. /dev/ttyS0 or COM5')
    parser.add_argument('--baudrate', type=int, default=115200,
                        help='serial baudrate (default: 115200)')
    parser.add_argument('--timeout', type=float, default=1.0,
                        help='reply timeout in seconds (default: 1.0)')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='command, e.g. A J5 23.3 or Q')
    args = parser.parse_args(argv)

    line = ' '.join(args.command).strip()
    if not line:
        parser.error('no command given')

    with serial.Serial(args.device, args.baudrate,
                       timeout=args.timeout) as port:
        port.reset_input_buffer()
        port.write((line + '\n').encode('ascii'))
        port.flush()
        reply = port.readline().decode('ascii', errors='ignore').strip()

    print(reply if reply else '(no response)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
