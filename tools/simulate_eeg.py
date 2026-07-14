#!/usr/bin/env python3
"""
EspBrain TGAM EEG Simulator
Generates valid ThinkGear protocol packets over serial.
Useful for testing without physical TGAM hardware.

Usage:
    python tools/simulate_eeg.py /dev/ttyUSB0
    python tools/simulate_eeg.py /dev/ttyUSB0 --attention 80 --meditation 40
"""

import serial
import struct
import time
import random
import argparse


def tgam_packet(payload: bytes) -> bytes:
    sync = b'\xaa\xaa'
    length = len(payload)
    checksum = (~sum(payload)) & 0xFF
    return sync + struct.pack('B', length) + payload + struct.pack('B', checksum)


def build_payload(attention=50, meditation=50, blink=0,
                  poor_signal=0, raw_wave=0, eeg_power=None):
    payload = b''
    payload += struct.pack('BB', 0x02, poor_signal)
    payload += struct.pack('BB', 0x04, attention)
    payload += struct.pack('BB', 0x05, meditation)
    payload += struct.pack('BB', 0x16, blink)

    raw_bytes = struct.pack('>h', raw_wave)
    payload += struct.pack('BB', 0x80, 2) + raw_bytes

    if eeg_power is None:
        eeg_power = {
            'delta': 150000, 'theta': 80000, 'low_alpha': 40000,
            'high_alpha': 25000, 'low_beta': 18000, 'high_beta': 12000,
            'low_gamma': 8000, 'high_gamma': 5000,
        }

    eeg_data = b''
    for band in ['delta', 'theta', 'low_alpha', 'high_alpha',
                  'low_beta', 'high_beta', 'low_gamma', 'high_gamma']:
        eeg_data += struct.pack('>I', eeg_power[band])[1:]

    payload += struct.pack('BB', 0x83, 24) + eeg_data
    return payload


def main():
    parser = argparse.ArgumentParser(description='TGAM EEG Simulator')
    parser.add_argument('port', help='Serial port (e.g. /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=57600, help='Baud rate')
    parser.add_argument('--attention', type=int, default=50, help='Attention 0-100')
    parser.add_argument('--meditation', type=int, default=50, help='Meditation 0-100')
    parser.add_argument('--blink-interval', type=float, default=5.0,
                        help='Blink every N seconds (0=disable)')
    parser.add_argument('--noise', type=float, default=0.1,
                        help='Random noise amplitude (fraction of value)')
    parser.add_argument('--rate', type=float, default=10.0, help='Packets per second')

    args = parser.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=1)
    print(f"TGAM Simulator running on {args.port} @ {args.baud} baud")
    print(f"Attention={args.attention} Meditation={args.meditation}")
    print("Press Ctrl+C to stop")

    last_blink = time.time()
    blink_cooldown = 0

    try:
        while True:
            att = max(0, min(255, int(args.attention *
                      (1 + random.uniform(-args.noise, args.noise)))))
            med = max(0, min(255, int(args.meditation *
                      (1 + random.uniform(-args.noise, args.noise)))))
            raw = random.randint(-500, 500)
            poor = 0
            blink = 0

            if args.blink_interval > 0 and not blink_cooldown:
                if time.time() - last_blink > args.blink_interval:
                    blink = random.randint(80, 200)
                    last_blink = time.time()
                    blink_cooldown = 10
            if blink_cooldown:
                blink_cooldown -= 1

            payload = build_payload(
                attention=att, meditation=med,
                blink=blink, poor_signal=poor, raw_wave=raw
            )
            packet = tgam_packet(payload)
            ser.write(packet)

            time.sleep(1.0 / args.rate)

    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        ser.close()


if __name__ == '__main__':
    main()
