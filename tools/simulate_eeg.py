#!/usr/bin/env python3
"""
Axis TGAM EEG Simulator — Professional-grade realistic EEG signal generation.
Generates valid NeuroSky ThinkGear protocol packets over serial.

Models real EEG physiology: 1/f noise, band-limited oscillations, 
state-dependent spectral profiles, blink/muscle/line-noise artifacts.

Usage:
    python tools/simulate_eeg.py /dev/ttyUSB0
    python tools/simulate_eeg.py /dev/ttyUSB0 --state focused --noise 0.05
    python tools/simulate_eeg.py /dev/ttyUSB0 --script scenario.json
"""

import serial
import struct
import time
import random
import math
import json
import argparse
import threading
from collections import deque


# ── EEG Physiology Constants ──────────────────────────────────────────

FS = 512.0                     # TGAM internal sample rate (Hz)
PINK_NOISE_OCTAVES = 6         # 1/f noise detail level
BLINK_DURATION = 0.15          # Typical blink duration (s)

# Frequency band boundaries (Hz)
BANDS = {
    'delta':     (0.5, 4),
    'theta':     (4,   8),
    'low_alpha': (8,  10),
    'high_alpha':(10, 13),
    'low_beta':  (13, 18),
    'high_beta': (18, 30),
    'low_gamma': (30, 40),
    'high_gamma':(40, 50),
}

# Mental state spectral profiles: (relative power per band, base att/med)
# Powers normalized so sum = 1.0
STATES = {
    'relaxed': {
        'delta': 0.05, 'theta': 0.15, 'low_alpha': 0.30, 'high_alpha': 0.25,
        'low_beta': 0.12, 'high_beta': 0.08, 'low_gamma': 0.03, 'high_gamma': 0.02,
        'attention': 35, 'meditation': 75,
        'desc': 'Eyes closed, relaxed — dominant alpha'
    },
    'focused': {
        'delta': 0.02, 'theta': 0.05, 'low_alpha': 0.08, 'high_alpha': 0.05,
        'low_beta': 0.30, 'high_beta': 0.25, 'low_gamma': 0.15, 'high_gamma': 0.10,
        'attention': 80, 'meditation': 25,
        'desc': 'Active concentration — dominant beta/gamma'
    },
    'meditative': {
        'delta': 0.08, 'theta': 0.35, 'low_alpha': 0.25, 'high_alpha': 0.10,
        'low_beta': 0.10, 'high_beta': 0.05, 'low_gamma': 0.04, 'high_gamma': 0.03,
        'attention': 45, 'meditation': 85,
        'desc': 'Deep meditation — dominant theta/alpha'
    },
    'drowsy': {
        'delta': 0.25, 'theta': 0.35, 'low_alpha': 0.15, 'high_alpha': 0.08,
        'low_beta': 0.08, 'high_beta': 0.04, 'low_gamma': 0.03, 'high_gamma': 0.02,
        'attention': 20, 'meditation': 60,
        'desc': 'Drowsy / sleep onset — dominant delta/theta'
    },
    'stressed': {
        'delta': 0.03, 'theta': 0.08, 'low_alpha': 0.05, 'high_alpha': 0.04,
        'low_beta': 0.25, 'high_beta': 0.30, 'low_gamma': 0.15, 'high_gamma': 0.10,
        'attention': 65, 'meditation': 15,
        'desc': 'Anxious/stressed — high beta, low alpha'
    },
    'active': {
        'delta': 0.04, 'theta': 0.10, 'low_alpha': 0.12, 'high_alpha': 0.08,
        'low_beta': 0.25, 'high_beta': 0.20, 'low_gamma': 0.12, 'high_gamma': 0.09,
        'attention': 70, 'meditation': 35,
        'desc': 'Normal active/alert — mixed beta + gamma'
    },
}


# ── Signal Generators ─────────────────────────────────────────────────

class PinkNoise:
    """Voss-McCartney pink noise generator (1/f spectrum)."""
    def __init__(self, n_octaves=PINK_NOISE_OCTAVES):
        self.n_octaves = n_octaves
        self.values = [random.random() * 2 - 1 for _ in range(n_octaves)]
        self.counts = [0] * n_octaves
        self.periods = [1 << i for i in range(n_octaves)]

    def sample(self):
        for i in range(self.n_octaves):
            self.counts[i] += 1
            if self.counts[i] >= self.periods[i]:
                self.values[i] = random.random() * 2 - 1
                self.counts[i] = 0
        return sum(self.values) / self.n_octaves


class BandOscillator:
    """Synthesize a frequency band from multiple sinusoidal components."""
    def __init__(self, name, f_lo, f_hi, amplitude=1.0):
        self.name = name
        self.f_lo = f_lo
        self.f_hi = f_hi
        self.amplitude = amplitude
        n_components = max(3, int((f_hi - f_lo) * 2))
        self.phases = [random.random() * 2 * math.pi for _ in range(n_components)]
        self.freqs = [f_lo + (f_hi - f_lo) * (i + 0.5) / n_components
                      for i in range(n_components)]
        self.amplitudes = [1.0 / (i + 1) for i in range(n_components)]
        norm = sum(self.amplitudes)
        self.amplitudes = [a / norm for a in self.amplitudes]

    def set_amplitude(self, amp):
        self.amplitude = amp

    def sample(self, t):
        val = 0.0
        for i, f in enumerate(self.freqs):
            val += self.amplitudes[i] * math.sin(2 * math.pi * f * t + self.phases[i])
        return val * self.amplitude


class BlinkGenerator:
    """Generate realistic blink artifacts (Gaussian-shaped)."""
    def __init__(self, rate=0.25):
        self.rate = rate           # blinks per second
        self.next_blink = random.expovariate(rate)
        self.blink_start = -1
        self.blink_amplitude = 0

    def sample(self, t):
        if t >= self.next_blink:
            self.blink_start = t
            self.blink_amplitude = random.uniform(200, 500) * random.choice([-1, 1])
            self.next_blink = t + random.expovariate(self.rate)

        if self.blink_start >= 0:
            dt = t - self.blink_start
            if dt < BLINK_DURATION:
                return self.blink_amplitude * math.exp(
                    -((dt - BLINK_DURATION / 2) ** 2) / (2 * (BLINK_DURATION / 6) ** 2)
                )
            else:
                self.blink_start = -1
        return 0.0


class MuscleNoise:
    """Random high-frequency bursts simulating muscle artifacts."""
    def __init__(self, probability=0.01, amplitude=30):
        self.prob = probability
        self.amplitude = amplitude
        self.active = False
        self.burst_len = 0
        self.burst_remaining = 0

    def sample(self):
        if self.burst_remaining > 0:
            self.burst_remaining -= 1
            return random.gauss(0, self.amplitude)
        if not self.active and random.random() < self.prob:
            self.active = True
            self.burst_len = random.randint(5, 30)
            self.burst_remaining = self.burst_len
            return random.gauss(0, self.amplitude)
        if self.active and self.burst_remaining <= 0:
            self.active = False
        return 0.0


class LineNoise:
    """50/60 Hz mains hum with harmonics."""
    def __init__(self, freq=50, amplitude=5):
        self.freq = freq
        self.amplitude = amplitude
        self.harmonics = [(1, 1.0), (2, 0.3), (3, 0.1)]

    def sample(self, t):
        val = 0.0
        for h, w in self.harmonics:
            val += w * math.sin(2 * math.pi * self.freq * h * t)
        return val * self.amplitude


# ── TGAM Packet Builder ───────────────────────────────────────────────

def build_tgam_packet(attention=50, meditation=50, blink=0,
                      poor_signal=0, raw_wave=0, eeg_power=None):
    """Construct a valid NeuroSky ThinkGear protocol packet."""
    payload = b''
    payload += struct.pack('BB', 0x02, poor_signal & 0xFF)
    payload += struct.pack('BB', 0x04, attention & 0xFF)
    payload += struct.pack('BB', 0x05, meditation & 0xFF)
    payload += struct.pack('BB', 0x16, blink & 0xFF)

    raw_clamped = max(-32768, min(32767, raw_wave))
    payload += struct.pack('BB', 0x80, 2) + struct.pack('>h', raw_clamped)

    if eeg_power is None:
        eeg_power = {k: 100000 for k in BANDS}
    eeg_data = b''
    for band in ['delta', 'theta', 'low_alpha', 'high_alpha',
                  'low_beta', 'high_beta', 'low_gamma', 'high_gamma']:
        val = max(0, min(0xFFFFFF, int(eeg_power.get(band, 0))))
        eeg_data += struct.pack('>I', val)[1:]
    payload += struct.pack('BB', 0x83, 24) + eeg_data

    sync = b'\xaa\xaa'
    length = len(payload)
    checksum = (~sum(payload)) & 0xFF
    return sync + struct.pack('B', length) + payload + struct.pack('B', checksum)


# ── EEG Simulator Core ────────────────────────────────────────────────

class EEGSimulator:
    """
    Professional EEG signal simulator producing valid TGAM packets.

    Generates realistic EEG by summing band-limited oscillators,
    pink noise, blink artifacts, muscle noise, and line noise.
    Supports dynamic state transitions for realistic signal evolution.
    """

    def __init__(self, state='relaxed', noise_level=0.1, 
                 blink_rate=0.25, line_freq=50, rate=50):
        self.t = 0.0
        self.rate = rate
        self.dt = 1.0 / rate
        self.noise_level = noise_level
        self.line_freq = line_freq

        self.pink = PinkNoise()
        self.oscillators = {}
        for name, (lo, hi) in BANDS.items():
            self.oscillators[name] = BandOscillator(name, lo, hi)
        self.blinks = BlinkGenerator(rate=blink_rate)
        self.muscle = MuscleNoise()
        self.line = LineNoise(freq=line_freq)

        self.base_power = 100000.0
        self.state = state
        self.state_profile = STATES[state].copy()
        self._apply_state()

        self.target_state = state
        self.transition_progress = 1.0
        self.transition_duration = 3.0  # seconds
        self.from_profile = self.state_profile.copy()

        self.blink_detected = False
        self.blink_cooldown = 0

    def _apply_state(self):
        profile = self.state_profile
        power_sum = sum(profile.get(b, 0) for b in BANDS)
        for name in BANDS:
            norm = profile.get(name, 0) / power_sum if power_sum > 0 else 1/len(BANDS)
            self.oscillators[name].set_amplitude(norm * self.base_power)

    def set_state(self, state_name, transition_s=3.0):
        if state_name in STATES and state_name != self.state:
            self.from_profile = self.state_profile.copy()
            self.target_state = state_name
            self.transition_progress = 0.0
            self.transition_duration = transition_s

    def set_parameterized(self, params):
        for k, v in params.items():
            if k in BANDS or k in ('attention', 'meditation'):
                self.state_profile[k] = v
        self._apply_state()

    def transition_tick(self, dt):
        if self.transition_progress < 1.0:
            self.transition_progress += dt / self.transition_duration
            if self.transition_progress >= 1.0:
                self.transition_progress = 1.0
                self.state = self.target_state
                self.state_profile = STATES[self.state].copy()
            else:
                t = self.transition_progress
                smooth = t * t * (3 - 2 * t)
                target = STATES[self.target_state]
                for key in self.state_profile:
                    if key in ('attention', 'meditation'):
                        f = self.from_profile.get(key, 50)
                        t_val = target.get(key, 50)
                        self.state_profile[key] = f + (t_val - f) * smooth
                    elif key in BANDS:
                        f = self.from_profile.get(key, 0)
                        t_val = target.get(key, 0)
                        self.state_profile[key] = f + (t_val - f) * smooth
            self._apply_state()

    def generate_sample(self):
        self.transition_tick(self.dt)
        os_val = sum(self.oscillators[b].sample(self.t) for b in BANDS)
        pink_val = self.pink.sample() * self.noise_level * 50
        blink_val = self.blinks.sample(self.t)
        muscle_val = self.muscle.sample()
        line_val = self.line.sample(self.t)

        raw = os_val + pink_val + blink_val + muscle_val + line_val
        raw = max(-32768, min(32767, raw))

        if abs(blink_val) > 50 and self.blink_cooldown == 0:
            self.blink_detected = True
            self.blink_cooldown = int(FS * 0.3 / self.rate)
        else:
            self.blink_detected = False
        if self.blink_cooldown > 0:
            self.blink_cooldown -= 1

        profile = self.state_profile
        power_sum = sum(profile.get(b, 0) for b in BANDS)
        band_powers = {}
        for b in BANDS:
            norm = profile.get(b, 0) / power_sum if power_sum > 0 else 1/len(BANDS)
            band_powers[b] = norm * self.base_power * (0.9 + 0.2 * random.random())

        att = profile.get('attention', 50)
        med = profile.get('meditation', 50)
        noise_att = random.gauss(0, 3)
        noise_med = random.gauss(0, 3)
        att = max(0, min(100, att + noise_att))
        med = max(0, min(100, med + noise_med))

        blink_strength = int(abs(blink_val)) if abs(blink_val) > 30 else 0
        poor_signal = 0 if self.noise_level < 0.3 else int(self.noise_level * 50)

        return {
            'attention': int(att),
            'meditation': int(med),
            'blink': min(255, blink_strength),
            'poor_signal': poor_signal,
            'raw_wave': int(raw),
            'eeg_power': {b: int(band_powers[b]) for b in BANDS},
        }

    def next_packet(self):
        data = self.generate_sample()
        self.t += self.dt
        return build_tgam_packet(
            attention=data['attention'],
            meditation=data['meditation'],
            blink=data['blink'],
            poor_signal=data['poor_signal'],
            raw_wave=data['raw_wave'],
            eeg_power=data['eeg_power'],
        )


# ── Script Engine ─────────────────────────────────────────────────────

class ScriptEngine:
    """Execute timed state-change scripts for repeatable test scenarios."""

    def __init__(self, sim, script_path):
        self.sim = sim
        with open(script_path) as f:
            self.events = json.load(f)
        self.events.sort(key=lambda e: e.get('t', 0))
        self.index = 0
        self.start_time = time.time()
        print(f"[Script] Loaded {len(self.events)} events from {script_path}")

    def tick(self, elapsed):
        while self.index < len(self.events):
            ev = self.events[self.index]
            if elapsed >= ev.get('t', 0):
                if 'state' in ev:
                    print(f"[Script] t={elapsed:.1f}s → state={ev['state']}")
                    self.sim.set_state(ev['state'], ev.get('transition', 3.0))
                elif 'params' in ev:
                    print(f"[Script] t={elapsed:.1f}s → custom params")
                    self.sim.set_parameterized(ev['params'])
                elif 'noise' in ev:
                    self.sim.noise_level = ev['noise']
                    print(f"[Script] t={elapsed:.1f}s → noise={ev['noise']}")
                self.index += 1
            else:
                break


# ── Interactive Console UI ────────────────────────────────────────────

class ConsoleUI(threading.Thread):
    def __init__(self, sim):
        super().__init__(daemon=True)
        self.sim = sim
        self.running = True

    def run(self):
        while self.running:
            try:
                cmd = input().strip().lower()
                if cmd == 'q' or cmd == 'quit':
                    self.running = False
                elif cmd.startswith('state '):
                    s = cmd.split()[1]
                    if s in STATES:
                        self.sim.set_state(s)
                        print(f"→ State: {s} ({STATES[s]['desc']})")
                    else:
                        print(f"Unknown state. Options: {', '.join(STATES.keys())}")
                elif cmd == 'states':
                    for name, info in STATES.items():
                        print(f"  {name:12s} {info['desc']}")
                elif cmd.startswith('noise '):
                    self.sim.noise_level = float(cmd.split()[1])
                    print(f"→ Noise: {self.sim.noise_level:.2f}")
                elif cmd == 'status':
                    s = self.sim.state
                    print(f"  State: {s} ({STATES[s]['desc']})")
                    print(f"  Noise: {self.sim.noise_level:.2f}")
                    print(f"  Rate:  {self.sim.rate} Hz")
                elif cmd == 'help':
                    print("Commands:")
                    print("  state <name>   Set mental state")
                    print("  states         List all states")
                    print("  noise <level>  Set noise level (0-1)")
                    print("  status         Show simulator status")
                    print("  q              Quit")
            except (EOFError, KeyboardInterrupt):
                self.running = False

    def stop(self):
        self.running = False


# ── Entry Point ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Axis Professional EEG Simulator — realistic TGAM signal generation')
    parser.add_argument('port', nargs='?', help='Serial port (e.g. /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=57600, help='Serial baud rate')
    parser.add_argument('--state', default='relaxed', choices=list(STATES.keys()),
                        help='Initial mental state')
    parser.add_argument('--noise', type=float, default=0.08,
                        help='Noise level (0.0-1.0)')
    parser.add_argument('--blink-rate', type=float, default=0.25,
                        help='Blink rate (per second, 0=disable)')
    parser.add_argument('--line-freq', type=int, default=50, choices=[50, 60],
                        help='Mains frequency for line noise')
    parser.add_argument('--rate', type=int, default=50,
                        help='Packet output rate (Hz)')
    parser.add_argument('--script', type=str, default=None,
                        help='JSON scenario script')
    parser.add_argument('--dry', action='store_true',
                        help='Print packets to stdout instead of serial')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive state control')
    parser.add_argument('--auto-cycle', type=float, default=0,
                        help='Auto-cycle through states every N seconds')

    args = parser.parse_args()

    sim = EEGSimulator(
        state=args.state,
        noise_level=args.noise,
        blink_rate=args.blink_rate,
        line_freq=args.line_freq,
        rate=args.rate,
    )

    ser = None
    if args.port and not args.dry:
        try:
            ser = serial.Serial(args.port, args.baud, timeout=1)
            print(f"[Serial] Connected to {args.port} @ {args.baud} baud")
        except serial.SerialException as e:
            print(f"[ERROR] {e}")
            print("[INFO] Falling back to --dry mode")
            args.dry = True

    script = None
    if args.script:
        script = ScriptEngine(sim, args.script)

    ui = None
    if args.interactive:
        ui = ConsoleUI(sim)
        ui.start()

    state_names = list(STATES.keys())
    state_idx = state_names.index(args.state)
    last_cycle = time.time()

    print(f"\n{'='*60}")
    print(f"  Axis EEG Simulator")
    print(f"  State: {args.state} ({STATES[args.state]['desc']})")
    print(f"  Noise: {args.noise:.2f} | Rate: {args.rate} Hz")
    print(f"  Output: {'Serial ' + args.port if ser else 'stdout (dry)'}")
    print(f"{'='*60}\n")

    try:
        while True:
            packet = sim.next_packet()

            if ser:
                ser.write(packet)
            else:
                if sim.blink_detected:
                    blink_mark = " [BLINK]"
                else:
                    blink_mark = ""
                d = sim.generate_sample()  # get latest values for display
                state_str = f"[{args.script + ' ' if script else ''}{sim.state}]".ljust(20)
                print(f"\r{state_str} "
                      f"Att={d['attention']:3d} Med={d['meditation']:3d} "
                      f"Blink={d['blink']:4d} Raw={d['raw_wave']:6d} "
                      f"Noise={sim.noise_level:.2f}{blink_mark}", end='',
                      flush=True)

            elapsed = time.time() - (script.start_time if script else time.time())

            if script:
                script.tick(elapsed)

            if args.auto_cycle > 0:
                if time.time() - last_cycle > args.auto_cycle:
                    state_idx = (state_idx + 1) % len(state_names)
                    sim.set_state(state_names[state_idx])
                    print(f"\n[Auto] → {state_names[state_idx]}")
                    last_cycle = time.time()

            time.sleep(1.0 / args.rate)

            if ui and not ui.running:
                break

    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        if ser:
            ser.close()
        if ui:
            ui.stop()


if __name__ == '__main__':
    main()
