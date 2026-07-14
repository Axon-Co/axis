#!/usr/bin/env python3
"""
Axis Offline Simulation — complete EEG→hand pipeline on your PC.
No ESP32, no TGAM, no servo hardware required.

Generates realistic EEG, runs the same command_interpreter logic,
shows live hand visualization, and logs everything to CSV.

Usage:
    python tools/simulate_axis.py
    python tools/simulate_axis.py --state focused --mode grip
    python tools/simulate_axis.py --log output.csv --plot
"""

import argparse
import csv
import math
import random
import time
from datetime import datetime

try:
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ── EEG Simulator (lightweight, embedded) ─────────────────────────────

PINK_OCTAVES = 6

BANDS = ['delta', 'theta', 'low_alpha', 'high_alpha',
         'low_beta', 'high_beta', 'low_gamma', 'high_gamma']

STATES = {
    'relaxed': {
        'delta': 0.05, 'theta': 0.15, 'low_alpha': 0.30, 'high_alpha': 0.25,
        'low_beta': 0.12, 'high_beta': 0.08, 'low_gamma': 0.03, 'high_gamma': 0.02,
        'attention': 35, 'meditation': 75,
    },
    'focused': {
        'delta': 0.02, 'theta': 0.05, 'low_alpha': 0.08, 'high_alpha': 0.05,
        'low_beta': 0.30, 'high_beta': 0.25, 'low_gamma': 0.15, 'high_gamma': 0.10,
        'attention': 82, 'meditation': 22,
    },
    'meditative': {
        'delta': 0.08, 'theta': 0.35, 'low_alpha': 0.25, 'high_alpha': 0.10,
        'low_beta': 0.10, 'high_beta': 0.05, 'low_gamma': 0.04, 'high_gamma': 0.03,
        'attention': 42, 'meditation': 88,
    },
    'drowsy': {
        'delta': 0.25, 'theta': 0.35, 'low_alpha': 0.15, 'high_alpha': 0.08,
        'low_beta': 0.08, 'high_beta': 0.04, 'low_gamma': 0.03, 'high_gamma': 0.02,
        'attention': 18, 'meditation': 58,
    },
    'stressed': {
        'delta': 0.03, 'theta': 0.08, 'low_alpha': 0.05, 'high_alpha': 0.04,
        'low_beta': 0.25, 'high_beta': 0.30, 'low_gamma': 0.15, 'high_gamma': 0.10,
        'attention': 68, 'meditation': 12,
    },
    'active': {
        'delta': 0.04, 'theta': 0.10, 'low_alpha': 0.12, 'high_alpha': 0.08,
        'low_beta': 0.25, 'high_beta': 0.20, 'low_gamma': 0.12, 'high_gamma': 0.09,
        'attention': 72, 'meditation': 32,
    },
}


class LightEEG:
    def __init__(self, state='relaxed', noise=0.1, blink_rate=0.25):
        self.state = state
        self.noise = noise
        self.blink_rate = blink_rate
        self.t = 0.0
        self.profile = STATES[state].copy()
        self.target = self.profile.copy()
        self.transition_t = 1.0

        self.pink = [0.0] * PINK_OCTAVES
        self.pink_counts = [0] * PINK_OCTAVES
        self.pink_periods = [1 << i for i in range(PINK_OCTAVES)]

        self.phases = {b: random.random() * 2 * math.pi for b in BANDS}
        self.next_blink = random.expovariate(blink_rate)
        self.blink_active = False

        self._att_noise = 0.0
        self._med_noise = 0.0

    def set_state(self, name):
        if name in STATES:
            self.target = STATES[name].copy()
            self.transition_t = 0.0

    def pink_noise(self):
        val = 0.0
        for i in range(PINK_OCTAVES):
            self.pink_counts[i] += 1
            if self.pink_counts[i] >= self.pink_periods[i]:
                self.pink[i] = random.random() * 2 - 1
                self.pink_counts[i] = 0
            val += self.pink[i]
        return val / PINK_OCTAVES

    def blink(self, t):
        if not self.blink_active and t >= self.next_blink:
            self.blink_active = True
            self.blink_t = t
            self.blink_amp = random.uniform(200, 500)
            self.next_blink = t + random.expovariate(self.blink_rate)
            return 0.0
        if self.blink_active:
            dt = t - self.blink_t
            if dt < 0.15:
                return self.blink_amp * math.exp(
                    -((dt - 0.075) ** 2) / (2 * (0.025) ** 2)
                )
            self.blink_active = False
        return 0.0

    def sample(self):
        self.t += 0.02  # 50Hz

        if self.transition_t < 1.0:
            self.transition_t += 0.02 / 3.0
            if self.transition_t >= 1.0:
                self.profile = self.target.copy()
                self.state = [k for k, v in STATES.items()
                             if v == self.target][0] if self.target in STATES.values() else self.state
            else:
                t = self.transition_t
                s = t * t * (3 - 2 * t)
                for k in self.profile:
                    self.profile[k] += (self.target[k] - (self.profile[k] - self.target[k] * 0)) * s
                    # simplified: just blend

        # Proper blending
        if self.transition_t < 1.0:
            t = self.transition_t
            s = t * t * (3 - 2 * t)
            for k in self.profile:
                self.profile[k] = STATES[self.state][k] + (self.target[k] - STATES[self.state][k]) * s
                if self.transition_t >= 1.0:
                    self.profile[k] = self.target[k]

        # Generate raw EEG-like value
        raw = 0.0
        band_powers = {}
        for i, b in enumerate(BANDS):
            amp = self.profile.get(b, 0.05) * 500
            raw += amp * math.sin(2 * math.pi * (3 + i * 5) * self.t + self.phases[b])
            band_powers[b] = max(1, int(amp * 200 * (0.9 + 0.2 * random.random())))

        raw += self.pink_noise() * 20 * self.noise
        blink_val = self.blink(self.t)
        raw += blink_val
        raw = max(-32768, min(32767, int(raw)))

        att = max(0, min(100,
            self.profile.get('attention', 50) + random.gauss(0, 4)))
        med = max(0, min(100,
            self.profile.get('meditation', 50) + random.gauss(0, 4)))

        blink_out = int(abs(blink_val)) if abs(blink_val) > 30 else 0
        poor = 0 if self.noise < 0.3 else int(self.noise * 50)

        return {
            'attention': int(att), 'meditation': int(med),
            'blink': min(255, blink_out), 'poor_signal': poor,
            'raw_wave': int(raw), 'eeg_power': band_powers,
        }


# ── Servo Hand Model ──────────────────────────────────────────────────

SERVO_NAMES = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
SERVO_OPEN  = [30, 10, 10, 10, 10]
SERVO_CLOSE = [150, 170, 170, 170, 160]


class Hand:
    def __init__(self):
        self.angles = list(SERVO_OPEN)
        self.targets = list(SERVO_OPEN)

    def set_all(self, angles):
        self.targets = list(angles)

    def smooth_to(self, target, duration=0.3):
        self.targets = list(target)
        steps = int(duration / 0.02)
        for s in range(1, steps + 1):
            t = s / steps
            st = t * t * (3 - 2 * t)
            for i in range(5):
                self.angles[i] = self.angles[i] + (target[i] - self.angles[i]) * 0.3
            time.sleep(0.02)

    def update(self):
        for i in range(5):
            diff = self.targets[i] - self.angles[i]
            self.angles[i] += diff * 0.3

    def grip_from_attention(self, att, thr_low=30, thr_high=70):
        if att < thr_low:
            grip = 0
        elif att > thr_high:
            grip = 100
        else:
            grip = (att - thr_low) * 100 // (thr_high - thr_low)

        for i in range(5):
            self.targets[i] = SERVO_OPEN[i] + \
                (SERVO_CLOSE[i] - SERVO_OPEN[i]) * grip // 100


# ── Hand Visualization ────────────────────────────────────────────────

def draw_hand(angles, ax):
    ax.clear()
    ax.set_xlim(-2, 8)
    ax.set_ylim(-1, 6)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Axis — Robotic Hand', fontsize=14, fontweight='bold')

    base_x = [0, 2, 3.5, 5, 6.5]
    base_y = [0, 0, 0, 0, 0]

    for i in range(5):
        a = angles[i]
        length = 2.0 + (a / 180.0) * 2.0
        angle_rad = math.radians(max(10, 90 - a * 0.4))

        bx, by = base_x[i], base_y[i]
        ex = bx + length * math.cos(angle_rad)
        ey = by + length * math.sin(angle_rad)

        color = plt.cm.RdYlGn(1.0 - a / 180.0)
        ax.plot([bx, ex], [by, ey], 'o-', color=color, linewidth=6,
                markersize=10, markerfacecolor=color, markeredgecolor='black')
        ax.text(bx, by - 0.3, SERVO_NAMES[i], ha='center', fontsize=8)
        ax.text(ex, ey + 0.2, f'{a}°', ha='center', fontsize=7, alpha=0.7)

    # Palm
    palm = plt.Circle((3.25, -0.3), 2.0, color='lightgray', ec='black', lw=1, zorder=0)
    ax.add_patch(palm)


# ── CSV Logger (same format as Axis firmware) ────────────────────────

CSV_HEADER = ('timestamp_ms,attention,meditation,blink_strength,raw_wave,'
              'delta,theta,low_alpha,high_alpha,low_beta,high_beta,'
              'low_gamma,high_gamma,'
              'servo0,servo1,servo2,servo3,servo4,state')


def init_csv(path):
    f = open(path, 'w', newline='')
    w = csv.writer(f)
    w.writerow(CSV_HEADER.split(','))
    return f, w


def write_row(w, t, eeg, hand, state):
    row = [
        int(t * 1000),
        eeg['attention'], eeg['meditation'], eeg['blink'],
        eeg['raw_wave'],
        eeg['eeg_power']['delta'], eeg['eeg_power']['theta'],
        eeg['eeg_power']['low_alpha'], eeg['eeg_power']['high_alpha'],
        eeg['eeg_power']['low_beta'], eeg['eeg_power']['high_beta'],
        eeg['eeg_power']['low_gamma'], eeg['eeg_power']['high_gamma'],
        hand.angles[0], hand.angles[1], hand.angles[2],
        hand.angles[3], hand.angles[4],
        state,
    ]
    w.writerow(row)


# ── Terminal UI ───────────────────────────────────────────────────────

def render_terminal(eeg, hand, state, t, blink_flag, log_count):
    servo_bar = ''
    for i in range(5):
        filled = int(hand.angles[i] / 180 * 10)
        bar = '█' * filled + '░' * (10 - filled)
        servo_bar += f"  {SERVO_NAMES[i][0]}: {bar} {int(hand.angles[i]):3d}°"

    blink_mark = ' 👁 BLINK' if blink_flag else '      '
    state_line = f"🧠 [{state:12s}] Att={eeg['attention']:3d}  Med={eeg['meditation']:3d}{blink_mark}"
    signal = '🟢' if eeg['poor_signal'] == 0 else '🔴'
    log_line = f"💾 Logged: {log_count} rows  |  t={t:.1f}s  |  Signal: {signal}"

    print(f"\033[2J\033[H", end='')  # clear
    print("╔════════════════════════════════════════════════════╗")
    print("║              Axis — EEG → Hand Simulation         ║")
    print("╚════════════════════════════════════════════════════╝")
    print()
    print(f"  {state_line}")
    print(f"  Raw: {eeg['raw_wave']:6d}  |  "
          f"δ:{eeg['eeg_power']['delta']:6d} θ:{eeg['eeg_power']['theta']:6d} "
          f"α:{eeg['eeg_power']['low_alpha']:6d} β:{eeg['eeg_power']['low_beta']:6d}")
    print()
    print(f"  {'─' * 45}")
    print(f"  SERVOS:")
    print(f"  {servo_bar}")
    print()
    print(f"  {log_line}")
    print()
    print(f"  ── Commands ──")
    print(f"  s <state>    : set state ({', '.join(STATES.keys())})")
    print(f"  q            : quit")
    print(f"  ─────────────────────────────")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Axis Offline Simulation — test EEG→hand pipeline on PC')
    parser.add_argument('--state', default='relaxed', choices=list(STATES.keys()))
    parser.add_argument('--noise', type=float, default=0.08)
    parser.add_argument('--blink-rate', type=float, default=0.25)
    parser.add_argument('--thr-low', type=int, default=30)
    parser.add_argument('--thr-high', type=int, default=70)
    parser.add_argument('--log', default=None,
                        help='Save CSV log to file')
    parser.add_argument('--plot', action='store_true',
                        help='Show matplotlib visualization')
    parser.add_argument('--duration', type=float, default=0,
                        help='Auto-stop after N seconds (0=infinite)')
    parser.add_argument('--auto-state', type=float, default=0,
                        help='Auto-cycle states every N seconds')

    args = parser.parse_args()

    eeg_gen = LightEEG(args.state, args.noise, args.blink_rate)
    hand = Hand()
    state_names = list(STATES.keys())
    state_idx = state_names.index(args.state)

    log_file = None
    log_writer = None
    if args.log:
        log_file, log_writer = init_csv(args.log)
        print(f"Logging to {args.log}")

    plot_win = None
    if args.plot and HAS_MPL:
        plt.ion()
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('Axis Simulation', fontsize=16)
    elif args.plot and not HAS_MPL:
        print("matplotlib not installed. Install: pip install matplotlib")

    import sys
    import select

    t0 = time.time()
    last_cycle = t0
    log_count = 0
    running = True

    print(f"\nAxis Simulation — State: {args.state} | Log: {args.log or 'none'}")
    print("Type commands or wait...\n")

    while running:
        now = time.time()
        elapsed = now - t0

        if args.duration > 0 and elapsed > args.duration:
            break

        # Generate EEG
        eeg = eeg_gen.sample()

        # Process → hand
        hand.grip_from_attention(eeg['attention'], args.thr_low, args.thr_high)
        hand.update()

        # Log
        if log_writer:
            write_row(log_writer, elapsed, eeg, hand, eeg_gen.state)
            log_count += 1

        # Auto-state cycle
        if args.auto_state > 0 and elapsed - (last_cycle - t0) > args.auto_state:
            state_idx = (state_idx + 1) % len(state_names)
            eeg_gen.set_state(state_names[state_idx])
            last_cycle = now
            print(f"\n[Auto] → {state_names[state_idx]}")

        # Terminal render
        render_terminal(eeg, hand, eeg_gen.state, elapsed,
                        eeg['blink'] > 0, log_count)

        # Plot
        if args.plot and HAS_MPL:
            if plot_win is None:
                plot_win = True
            ax1.clear()
            draw_hand(hand.angles, ax1)
            ax2.clear()
            bands = list(eeg['eeg_power'].keys())
            vals = [eeg['eeg_power'][b] for b in bands]
            colors = ['#ff0000', '#ff8800', '#ffff00', '#00cc00',
                      '#00ccff', '#0066ff', '#8800ff', '#ff00ff']
            bars = ax2.barh(bands, vals, color=colors)
            ax2.set_xscale('log')
            ax2.set_title('EEG Power Bands')
            ax2.set_xlabel('Power (log)')
            for bar, v in zip(bars, vals):
                ax2.text(bar.get_width() * 1.05, bar.get_y() + bar.get_height()/2,
                        f'{v:,}', va='center', fontsize=7)
            plt.pause(0.001)

        # Keyboard input
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip().lower()
            if cmd == 'q':
                running = False
            elif cmd.startswith('s '):
                state_name = cmd.split()[1]
                if state_name in STATES:
                    eeg_gen.set_state(state_name)
                    print(f"→ State: {state_name}")

        time.sleep(0.02)

    # Cleanup
    if log_file:
        log_file.close()
        print(f"\nSaved {log_count} rows to {args.log}")

    if args.plot and HAS_MPL:
        plt.ioff()
        plt.close()

    print(f"\nDone. Simulated {elapsed:.1f}s, logged {log_count} rows.")


if __name__ == '__main__':
    main()
