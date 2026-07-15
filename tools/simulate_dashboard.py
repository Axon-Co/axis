#!/usr/bin/env python3
"""
Axis Simulation Dashboard — real-time EEG simulation with browser-based web dashboard.

Runs the professional EEG simulator and serves a live Chart.js dashboard via HTTP.
No ESP32 hardware required. Streams attention, meditation, blink, band powers, 
and simulated servo positions directly to your browser in real-time.

Usage:
    python tools/simulate_dashboard.py
    python tools/simulate_dashboard.py --port 8080 --state focused
    python tools/simulate_dashboard.py --auto-cycle 10 --log data.csv
    python tools/simulate_dashboard.py --no-browser
"""

import os, sys, json, time, math, random, csv
import argparse, threading, webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ── Professional EEG Simulation Engine ──────────────────────────────
# Models: 1/f pink noise, 8-band neural oscillators with frequency
# jitter, alpha spindles, beta bursts, blink/muscle/line artifacts,
# state-dependent spectral profiles.

PINK_OCT = 8
BLINK_DUR = 0.15
MUSCLE_PROB = 0.008
BASE_POWER = 100000.0

BANDS = {
    'delta':     (0.5, 4),    'theta':     (4, 8),
    'low_alpha': (8, 10),     'high_alpha': (10, 13),
    'low_beta':  (13, 18),    'high_beta':  (18, 30),
    'low_gamma': (30, 40),    'high_gamma': (40, 50),
}
BAND_NAMES = list(BANDS.keys())

# Neurophysiological state profiles: relative spectral power (sum=1)
# Each state mimics real EEG from clinical literature.
STATES = {
    'relaxed': {
        'delta': 0.04, 'theta': 0.12, 'low_alpha': 0.32, 'high_alpha': 0.24,
        'low_beta': 0.14, 'high_beta': 0.08, 'low_gamma': 0.04, 'high_gamma': 0.02,
        'attention': 32, 'meditation': 78,
        'desc': 'Eyes closed — posterior alpha dominant (8-12 Hz)',
        'alpha_peak': 10.5, 'alpha_width': 1.5,
    },
    'focused': {
        'delta': 0.02, 'theta': 0.04, 'low_alpha': 0.05, 'high_alpha': 0.03,
        'low_beta': 0.34, 'high_beta': 0.28, 'low_gamma': 0.14, 'high_gamma': 0.10,
        'attention': 88, 'meditation': 18,
        'desc': 'Active concentration — frontal beta/gamma (13-40 Hz)',
        'alpha_peak': 10.0, 'alpha_width': 0.8,
    },
    'meditative': {
        'delta': 0.06, 'theta': 0.40, 'low_alpha': 0.28, 'high_alpha': 0.10,
        'low_beta': 0.08, 'high_beta': 0.04, 'low_gamma': 0.02, 'high_gamma': 0.02,
        'attention': 38, 'meditation': 92,
        'desc': 'Deep meditation — frontal theta (4-8 Hz) + alpha',
        'alpha_peak': 9.5, 'alpha_width': 2.0,
    },
    'drowsy': {
        'delta': 0.30, 'theta': 0.38, 'low_alpha': 0.12, 'high_alpha': 0.05,
        'low_beta': 0.08, 'high_beta': 0.03, 'low_gamma': 0.02, 'high_gamma': 0.02,
        'attention': 12, 'meditation': 52,
        'desc': 'Drowsy/sleep onset — delta+theta (0.5-8 Hz)',
        'alpha_peak': 9.0, 'alpha_width': 0.5,
    },
    'stressed': {
        'delta': 0.02, 'theta': 0.05, 'low_alpha': 0.03, 'high_alpha': 0.02,
        'low_beta': 0.28, 'high_beta': 0.36, 'low_gamma': 0.14, 'high_gamma': 0.10,
        'attention': 62, 'meditation': 8,
        'desc': 'Anxious — high beta (18-30 Hz), low alpha',
        'alpha_peak': 11.0, 'alpha_width': 0.6,
    },
    'active': {
        'delta': 0.03, 'theta': 0.07, 'low_alpha': 0.09, 'high_alpha': 0.05,
        'low_beta': 0.30, 'high_beta': 0.24, 'low_gamma': 0.12, 'high_gamma': 0.10,
        'attention': 76, 'meditation': 32,
        'desc': 'Normal alert — mixed beta with frontal alpha',
        'alpha_peak': 10.0, 'alpha_width': 1.2,
    },
}

SERVO_OPEN  = [30, 10, 10, 10, 10]
SERVO_CLOSE = [150, 170, 170, 170, 160]


class PinkNoise:
    """Voss-McCartney pink noise (1/f) with configurable octaves."""
    def __init__(self, octaves=PINK_OCT):
        self.n = octaves
        self.vals = [random.random() * 2 - 1 for _ in range(octaves)]
        self.cnt = [0] * octaves
        self.per = [1 << i for i in range(octaves)]

    def sample(self):
        for i in range(self.n):
            self.cnt[i] += 1
            if self.cnt[i] >= self.per[i]:
                self.vals[i] = random.random() * 2 - 1
                self.cnt[i] = 0
        return sum(self.vals) / self.n


class NeuralOscillator:
    """
    Single EEG frequency band oscillator.
    Generates band-limited oscillations by summing multiple
    sinusoidal components with frequency jitter for natural rhythm.
    """
    def __init__(self, name, f_lo, f_hi, n_components=5):
        self.name = name
        self.f_lo = f_lo
        self.f_hi = f_hi
        self.amp = 1.0
        self.alpha_peak = 10.0
        self.alpha_width = 1.0

        n = max(3, min(n_components, int((f_hi - f_lo) * 2)))
        self.phases = [random.random() * 2 * math.pi for _ in range(n)]
        self.freqs = [f_lo + (f_hi - f_lo) * (i + 0.5) / n for i in range(n)]
        self.jitter = [random.gauss(0, 0.15) for _ in range(n)]
        self.jitter_t = [0.0] * n
        self.jitter_per = [random.uniform(0.3, 0.8) for _ in range(n)]
        weights = [1.0 / (i + 1) for i in range(n)]
        self.weights = [w / sum(weights) for w in weights]

    def set_amplitude(self, amp):
        self.amp = amp

    def sample(self, t):
        val = 0.0
        for i in range(len(self.freqs)):
            self.jitter_t[i] += 0.02
            if self.jitter_t[i] > self.jitter_per[i]:
                self.jitter[i] = random.gauss(0, 0.15)
                self.jitter_t[i] = 0.0
            fj = self.freqs[i] + self.jitter[i]
            val += self.weights[i] * math.sin(2 * math.pi * fj * t + self.phases[i])
        return val * self.amp


class BlinkGenerator:
    """Realistic eye-blink artifact (Gaussian wavelet)."""
    def __init__(self, rate=0.25):
        self.rate = rate
        self.next_t = random.expovariate(rate)
        self.start_t = -1
        self.peak_amp = 0

    def sample(self, t):
        if t >= self.next_t:
            self.start_t = t
            self.peak_amp = random.uniform(200, 600)
            self.next_t = t + random.expovariate(self.rate)
        if self.start_t >= 0:
            dt = t - self.start_t
            if dt < BLINK_DUR:
                return self.peak_amp * math.exp(
                    -((dt - BLINK_DUR / 2) ** 2) / (2 * (BLINK_DUR / 6) ** 2))
            self.start_t = -1
        return 0.0


class MuscleNoise:
    """Random high-frequency muscle artifact bursts."""
    def __init__(self, prob=MUSCLE_PROB, amp=40):
        self.prob = prob
        self.amp = amp
        self.remaining = 0
        self.burst_len = 0

    def sample(self):
        if self.remaining > 0:
            self.remaining -= 1
            return random.gauss(0, self.amp)
        if random.random() < self.prob:
            self.burst_len = random.randint(5, 40)
            self.remaining = self.burst_len
            return random.gauss(0, self.amp)
        return 0.0


class LineNoise:
    """Mains hum (50/60 Hz) with harmonics."""
    def __init__(self, freq=50, amp=8):
        self.freq = freq
        self.amp = amp
        self.harms = [(1, 1.0), (2, 0.25), (3, 0.08), (4, 0.03)]

    def sample(self, t):
        val = 0.0
        for h, w in self.harms:
            val += w * math.sin(2 * math.pi * self.freq * h * t + h * 0.7)
        return val * self.amp


class AlphaSpindle:
    """
    Simulates sleep-like alpha spindles — brief (0.5-2s) bursts
    of waxing-and-waning alpha activity.
    """
    def __init__(self, prob=0.002):
        self.prob = prob
        self.active = False
        self.t_start = 0
        self.dur = 0
        self.amp = 0

    def sample(self, t, alpha_amp):
        if not self.active and random.random() < self.prob:
            self.active = True
            self.t_start = t
            self.dur = random.uniform(0.5, 2.0)
            self.amp = random.uniform(2.0, 5.0)
        if self.active:
            dt = t - self.t_start
            if dt < self.dur:
                envelope = math.sin(math.pi * dt / self.dur)  # wax-wane
                return alpha_amp * self.amp * envelope * math.sin(
                    2 * math.pi * 12 * t)
            self.active = False
        return 0.0


class EEGSimulator:
    """
    Professional EEG simulator producing realistic multi-band signals.
    Combines: neural oscillators × 8 bands, pink noise, blinks,
    muscle noise, line noise, alpha spindles.
    """

    def __init__(self, state='relaxed', noise=0.06, blink_rate=0.25, line_freq=50, rate=50):
        self.t = 0.0
        self.rate = rate
        self.dt = 1.0 / rate
        self.noise = noise
        self.line_freq = line_freq

        self.state = state
        self.profile = STATES[state].copy()
        self.target = self.profile.copy()
        self.transition_t = 1.0
        self.transition_dur = 0.4

        self.pink = PinkNoise()
        self.oscillators = {}
        for name, (lo, hi) in BANDS.items():
            self.oscillators[name] = NeuralOscillator(name, lo, hi)
        self.blinks = BlinkGenerator(rate=blink_rate)
        self.muscle = MuscleNoise()
        self.line = LineNoise(freq=line_freq)
        self.spindle = AlphaSpindle()

        self.servo_angles = list(SERVO_OPEN)
        self.servo_targets = list(SERVO_OPEN)
        self.history = []

        self._apply_profile()
        print(f"[Sim] Initialized: {state} (rate={rate}Hz)")

    def _apply_profile(self):
        p = self.profile
        total = sum(p.get(b, 0) for b in BAND_NAMES) or 1.0
        for name in BAND_NAMES:
            norm = p.get(name, 0) / total
            self.oscillators[name].set_amplitude(norm * 1.5)
            if 'alpha' in name:
                self.oscillators[name].alpha_peak = p.get('alpha_peak', 10.0)
                self.oscillators[name].alpha_width = p.get('alpha_width', 1.0)

    def set_state(self, name):
        if name in STATES and name != self.state:
            self.state = name
            self.target = STATES[name].copy()
            self.profile = STATES[name].copy()
            self.transition_t = 1.0
            self._apply_profile()
            return True
        return False

    def step(self):
        self.t += self.dt
        p = self.profile
        total_power = sum(p.get(b, 0) for b in BAND_NAMES) or 1.0

        # Generate raw EEG (microvolts): oscillators + pink noise + artifacts
        raw = 0.0
        band_powers = {}
        for b in BAND_NAMES:
            norm = p.get(b, 0) / total_power
            osc_amp = norm * 500
            raw += self.oscillators[b].sample(self.t) * osc_amp / (len(BAND_NAMES) ** 0.5)
            band_powers[b] = norm * BASE_POWER * (0.92 + 0.16 * random.random())

        raw += self.pink.sample() * 30 * self.noise
        raw += self.blinks.sample(self.t)
        raw += self.muscle.sample()
        raw += self.line.sample(self.t)
        raw += self.spindle.sample(self.t, p.get('low_alpha', 0) * 200)
        raw = round(max(-100.0, min(100.0, raw)), 4)

        # Derive attention/meditation from spectral state + noise
        base_att = p.get('attention', 50)
        base_med = p.get('meditation', 50)
        att_drift = math.sin(self.t * 0.05) * 3 + random.gauss(0, 3)
        med_drift = math.cos(self.t * 0.04) * 3 + random.gauss(0, 3)
        att = max(0, min(100, base_att + att_drift))
        med = max(0, min(100, base_med + med_drift))

        blink_out = int(self.blinks.peak_amp) if (
            self.blinks.start_t >= 0 and
            self.t - self.blinks.start_t < BLINK_DUR / 2
        ) else 0
        blink_out = min(255, blink_out)

        poor = 0 if self.noise < 0.3 else int(self.noise * 50)

        self.servo_angles = self._update_servos(att, med)

        la = band_powers['low_alpha']
        ha = band_powers['high_alpha']
        lb = band_powers['low_beta']
        hb = band_powers['high_beta']
        lg = band_powers['low_gamma']
        hg = band_powers['high_gamma']
        total = la + ha + lb + hb + lg + hg + band_powers['delta'] + band_powers['theta']

        data = {
            't': round(self.t, 3),
            'attention': int(att),
            'meditation': int(med),
            'blink': blink_out,
            'signal_quality': max(0, 100 - poor * 2),
            'raw_wave': raw,
            'band_powers': {b: round(band_powers[b], 1) for b in BAND_NAMES},
            'alpha_beta_ratio': round((la + ha) / (lb + hb + 1), 3),
            'theta_gamma_ratio': round(band_powers['theta'] / (lg + hg + 1), 3),
            'att_med_ratio': round(att / (med + 1), 3),
            'servos': [round(a, 1) for a in self.servo_angles],
            'state': self.state,
        }
        self.history.append(data)
        if len(self.history) > 5000:
            self.history = self.history[-5000:]
        return data

    def _update_servos(self, att, med):
        grip = 0
        if att > 55:
            grip = 100
        elif att > 25:
            grip = (att - 25) * 100 // 30
        angles = list(self.servo_angles)
        for i in range(5):
            tgt = SERVO_OPEN[i] + (SERVO_CLOSE[i] - SERVO_OPEN[i]) * grip // 100
            diff = tgt - angles[i]
            angles[i] += diff * 0.2 + random.gauss(0, 0.3)
            angles[i] = max(0, min(180, angles[i]))
        return angles


# ── Global Simulator ──────────────────────────────────────────────────

sim = EEGSimulator()
sim_running = True


def simulation_thread():
    global sim_running
    while sim_running:
        sim.step()
        time.sleep(1.0 / sim.rate)


# ── HTTP Handler ──────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())

        elif path == '/api/latest':
            d = sim.history[-1] if sim.history else {}
            d['state'] = sim.state
            s = STATES.get(sim.state, {})
            d['state_desc'] = s.get('desc', '')
            d['uptime'] = round(sim.t, 1)
            d['total_samples'] = len(sim.history)
            self.send_json(d)

        elif path == '/api/history':
            n = min(int(params.get('n', [500])[0]), 5000)
            data = sim.history[-n:] if sim.history else []
            self.send_json({'data': data, 'count': len(data)})

        elif path == '/api/stats':
            h = sim.history
            if len(h) < 2:
                self.send_json({'error': 'Not enough data'})
                return
            atts = [d['attention'] for d in h]
            meds = [d['meditation'] for d in h]
            blinks = [d['blink'] for d in h]
            bs = {b: [d['band_powers'][b] for d in h] for b in BAND_NAMES}
            stats = {
                'attention':  {'min': min(atts), 'max': max(atts), 'avg': round(sum(atts)/len(atts), 1), 'current': atts[-1]},
                'meditation': {'min': min(meds), 'max': max(meds), 'avg': round(sum(meds)/len(meds), 1), 'current': meds[-1]},
                'blink':      {'count': sum(1 for b in blinks if b > 0), 'max': max(blinks)},
            }
            for b in BAND_NAMES:
                vals = bs[b]
                stats[b] = {'avg': round(sum(vals)/len(vals), 0), 'current': vals[-1]}

            alphas = [d['band_powers']['low_alpha'] + d['band_powers']['high_alpha'] for d in h]
            betas = [d['band_powers']['low_beta'] + d['band_powers']['high_beta'] for d in h]
            stats['alpha_beta_avg'] = round(sum(a/(b+1) for a,b in zip(alphas,betas))/len(alphas), 3)
            stats['state'] = sim.state
            stats['uptime'] = round(sim.t, 1)
            stats['samples'] = len(h)
            self.send_json(stats)

        elif path == '/api/state':
            if params.get('name'):
                name = params['name'][0]
                ok = sim.set_state(name)
                self.send_json({'status': 'ok', 'state': name, 'desc': STATES.get(name, {}).get('desc', '')})
            else:
                self.send_json({'state': sim.state, 'states': list(STATES.keys())})

        elif path == '/api/config':
            if params.get('noise'):
                sim.noise = max(0, min(1, float(params['noise'][0])))
            if params.get('blink_rate'):
                sim.blink_rate = max(0, float(params['blink_rate'][0]))
            self.send_json({'noise': sim.noise, 'blink_rate': sim.blink_rate, 'rate': sim.rate})

        elif path == '/api/states':
            self.send_json(STATES)

        else:
            self.send_error(404)

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        if args[0] != '/api/latest' and not args[0].startswith('/api/stream'):
            super().log_message(fmt, *args)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Axis EEG</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Helvetica Neue', sans-serif; background: #f5f5f5; color: #333; padding: 24px; }

.top { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.top h1 { font-size: 16px; font-weight: 600; color: #222; letter-spacing: -0.3px; }
.top .sep { color: #ccc; }
.top .badge { font-size: 13px; color: #555; }
.top .right { margin-left: auto; display: flex; gap: 8px; align-items: center; }
.top select { background: #fff; border: 1px solid #ddd; padding: 4px 8px; border-radius: 4px; font-size: 12px; color: #333; cursor: pointer; }
.top select:hover { border-color: #aaa; }
.top button { background: #fff; border: 1px solid #ddd; padding: 4px 12px; border-radius: 4px; font-size: 12px; color: #333; cursor: pointer; }
.top button:hover { border-color: #aaa; background: #fafafa; }

.row1 { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.mtr { flex: 1; min-width: 90px; background: #fff; border: 1px solid #e0e0e0; border-radius: 4px; padding: 8px 12px; }
.mtr .l { font-size: 9px; color: #999; text-transform: uppercase; letter-spacing: 0.3px; }
.mtr .v { font-size: 22px; font-weight: 500; color: #222; font-family: 'SF Mono', 'Menlo', monospace; }
.mtr .b { height: 2px; background: #e0e0e0; margin-top: 4px; border-radius: 1px; overflow: hidden; }
.mtr .b i { display: block; height: 100%; background: #666; border-radius: 1px; }

.gr { display: grid; grid-template-columns: 3fr 2fr; gap: 12px; margin-bottom: 12px; }
.gr2 { grid-template-columns: 1fr; }
.cd { background: #fff; border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; }
.cd h3 { font-size: 10px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.cd canvas { width: 100% !important; max-height: 200px; }

.r3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.sv { display: flex; gap: 4px; justify-content: center; align-items: flex-end; height: 100px; }
.sc { display: flex; flex-direction: column; align-items: center; gap: 2px; width: 40px; }
.sc .b { width: 20px; border-radius: 2px 2px 0 0; background: #888; min-height: 2px; }
.sc .n { font-size: 8px; color: #999; }
.sc .d { font-size: 10px; color: #555; font-weight: 500; font-family: 'SF Mono', monospace; }

table.st { width: 100%; font-size: 11px; border-collapse: collapse; }
table.st td { padding: 2px 4px; }
table.st .k { color: #999; }
table.st .v { color: #333; text-align: right; font-family: 'SF Mono', monospace; }
table.st tr:nth-child(even) { background: #fafafa; }

.rg { display: flex; gap: 4px; }
.ri { flex: 1; text-align: center; padding: 6px 4px; background: #fafafa; border-radius: 3px; }
.ri .rl { font-size: 8px; color: #999; text-transform: uppercase; }
.ri .rv { font-size: 16px; font-weight: 500; color: #444; }

@media (max-width: 700px) { .gr { grid-template-columns: 1fr; } .r3 { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<div class="top">
  <h1>Axis</h1>
  <span class="sep">/</span>
  <span class="badge" id="stateBadge">relaxed</span>
  <span style="font-size:11px;color:#999" id="timeDisplay">0s</span>
  <div class="right">
    <select id="stateSelect" onchange="setState(this.value)">
      <option value="relaxed">Relaxed</option>
      <option value="focused">Focused</option>
      <option value="meditative">Meditative</option>
      <option value="drowsy">Drowsy</option>
      <option value="stressed">Stressed</option>
      <option value="active">Active</option>
    </select>
    <select id="autoCycle" onchange="setAutoCycle(this.value)">
      <option value="0">Static</option>
      <option value="5">5s</option>
      <option value="10">10s</option>
      <option value="20">20s</option>
    </select>
    <button onclick="resetStats()">Reset</button>
  </div>
</div>

<div class="row1" id="mtrs"></div>

<div class="gr">
  <div class="cd"><h3>Attention & Meditation</h3><canvas id="chartAttMed"></canvas></div>
  <div class="cd"><h3>Band Distribution</h3><canvas id="chartPie"></canvas></div>
</div>

<div class="gr gr2">
  <div class="cd"><h3>Frequency Bands</h3><canvas id="chartBands"></canvas></div>
</div>

<div class="r3">
  <div class="cd"><h3>Servos</h3><div class="sv" id="sv"></div></div>
  <div class="cd"><h3>Stats</h3><table class="st" id="st"></table></div>
  <div class="cd"><h3>Ratios</h3>
    <div class="rg">
      <div class="ri"><div class="rl">a/b</div><div class="rv" id="rAb">—</div></div>
      <div class="ri"><div class="rl">t/g</div><div class="rv" id="rTg">—</div></div>
      <div class="ri"><div class="rl">a/m</div><div class="rv" id="rAm">—</div></div>
      <div class="ri"><div class="rl">sig</div><div class="rv" id="rSig">—</div></div>
    </div>
  </div>
</div>

<script>
const BCOL = ['#e74c3c','#e67e22','#f1c40f','#2ecc71','#3498db','#2980b9','#9b59b6','#e91e63'];
const SCOL = ['#c0392b','#d35400','#f39c12','#2980b9','#27ae60'];
const BN = ['delta','theta','low_alpha','high_alpha','low_beta','high_beta','low_gamma','high_gamma'];
const MK = [
  {k:'attention', l:'Att', m:100, u:'%'},
  {k:'meditation', l:'Med', m:100, u:'%'},
  {k:'blink', l:'Blink', m:255, u:''},
  {k:'signal_quality', l:'Signal', m:100, u:'%'},
  {k:'raw_wave', l:'EEG', m:100, u:'uv'},
];
const SN = ['relaxed','focused','meditative','drowsy','stressed','active'];

let ch = {}, hx = [], act = null, si = 0;

function mkChart(id, type, data, extra) {
  return new Chart(document.getElementById(id), {type, data,
    options: Object.assign({responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{mode:'nearest',intersect:false},
      plugins:{legend:{labels:{color:'#999',font:{size:9}}}},
      scales:{x:{ticks:{color:'#bbb',maxTicksLimit:8,font:{size:8}},grid:{color:'#eee'}},
              y:{ticks:{color:'#bbb',font:{size:8}},grid:{color:'#eee'}}}
    }, extra)
  });
}

function initCh() {
  ch.att = mkChart('chartAttMed', 'line', {
    labels:[], datasets:[
      {label:'Att', data:[], borderColor:'#333', backgroundColor:'rgba(0,0,0,0.04)', fill:true, tension:0.3, pointRadius:0},
      {label:'Med', data:[], borderColor:'#888', backgroundColor:'rgba(0,0,0,0.03)', fill:true, tension:0.3, pointRadius:0},
      {label:'Blink', data:[], borderColor:'#ccc', fill:false, tension:0.1, pointRadius:0},
    ]
  }, {scales:{y:{min:0,max:100}}});

  ch.pie = mkChart('chartPie', 'doughnut', {
    labels:BN, datasets:[{data:BN.map(()=>0), backgroundColor:BCOL}]
  }, {cutout:'60%', plugins:{legend:{position:'right',labels:{color:'#999',font:{size:8}}}}});

  ch.band = mkChart('chartBands', 'line', {
    labels:[], datasets:BN.map((b,i)=>({label:b, data:[], borderColor:BCOL[i], fill:false, tension:0.3, pointRadius:0}))
  }, {scales:{y:{type:'logarithmic',min:1}}});
}

function updM(d) {
  document.getElementById('mtrs').innerHTML =
    MK.map(m => {
      const v = d[m.k] || 0;
      return `<div class="mtr"><div class="l">${m.l}</div><div class="v">${v}${m.u}</div><div class="b"><i style="width:${(v/m.m*100).toFixed(0)}%"></i></div></div>`;
    }).join('') +
    `<div class="mtr"><div class="l">State</div><div class="v" style="font-size:18px;color:#333">${d.state||'?'}</div><div style="font-size:8px;color:#999">${d.state_desc||''}</div></div>`;
}

function updS(d) {
  const s = d.servos || [0,0,0,0,0];
  const nm = ['Th','Ix','Md','Ri','Pi'];
  document.getElementById('sv').innerHTML = s.map((v,i) =>
    `<div class="sc"><div class="b" style="height:${Math.max(2,v/180*85)}px;background:${SCOL[i]}"></div><div class="d">${v.toFixed(0)}</div><div class="n">${nm[i]}</div></div>`
  ).join('');
}

function updSt(d) {
  const s = d || {};
  document.getElementById('st').innerHTML =
    [['Att', s.attention?.avg], ['Med', s.meditation?.avg], ['Blinks', s.blink?.count]].map(([l,a]) =>
      `<tr><td class="k">${l}</td><td class="v">${a||'—'}</td><td class="v">${l==='Blinks'?s.blink?.max||'—':s[l.toLowerCase()]?.max||'—'}</td></tr>`
    ).join('') +
    `<tr><td class="k">Samples</td><td class="v" colspan="2">${s.samples||0}</td></tr>` +
    `<tr><td class="k">Uptime</td><td class="v" colspan="2">${(s.uptime||0).toFixed(1)}s</td></tr>`;
}

function updR(d) {
  document.getElementById('rAb').textContent = d.alpha_beta_ratio || '—';
  document.getElementById('rTg').textContent = d.theta_gamma_ratio || '—';
  document.getElementById('rAm').textContent = d.att_med_ratio || '—';
  document.getElementById('rSig').textContent = (d.signal_quality || 0) + '%';
}

function updC(d) {
  hx.push(d);
  if (hx.length > 300) hx.shift();
  const lb = hx.map(x => x.t.toFixed(1));
  if (!ch.att) initCh();

  ch.att.data.labels = lb;
  ch.att.data.datasets[0].data = hx.map(x => x.attention);
  ch.att.data.datasets[1].data = hx.map(x => x.meditation);
  ch.att.data.datasets[2].data = hx.map(x => x.blink);
  ch.att.update('none');

  const last = hx[hx.length - 1];
  const bp = last ? last.band_powers : {};
  const pv = BN.map(b => bp[b] || 1);
  const tt = pv.reduce((a,b) => a+b, 0);
  ch.pie.data.datasets[0].data = pv;
  ch.pie.data.labels = BN.map((b,i) => b + ' ' + (tt > 0 ? (pv[i]/tt*100).toFixed(1) : 0) + '%');
  ch.pie.update('none');

  ch.band.data.labels = lb;
  BN.forEach((b,i) => { ch.band.data.datasets[i].data = hx.map(x => Math.max(1, (x.band_powers||{})[b] || 1)); });
  ch.band.update('none');
}

async function poll() {
  try {
    const r = await fetch('/api/latest');
    const d = await r.json();
    document.getElementById('stateBadge').textContent = d.state || '?';
    document.getElementById('timeDisplay').textContent = (d.t || 0).toFixed(1) + 's';
    updM(d); updS(d); updR(d); updC(d);
    const r2 = await fetch('/api/stats');
    updSt(await r2.json());
  } catch(e) {}
}

function setState(n) {
  document.getElementById('stateSelect').value = n;
  document.getElementById('stateBadge').textContent = n;
  fetch('/api/state?name=' + n);
}

function setAutoCycle(s) {
  if (act) { clearInterval(act); act = null; }
  if (s > 0) act = setInterval(() => {
    const cur = document.getElementById('stateSelect').value;
    si = (SN.indexOf(cur) + 1) % SN.length;
    setState(SN[si]);
  }, s * 1000);
}

function resetStats() { hx = []; Object.values(ch).forEach(c => c.destroy()); ch = {}; }

initCh();
poll();
setInterval(poll, 350);
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description='Axis Simulation Dashboard — real-time EEG simulation in your browser')
    parser.add_argument('--port', '-p', type=int, default=8080,
                        help='HTTP server port (default: 8080)')
    parser.add_argument('--bind', '-b', default='0.0.0.0',
                        help='Bind address (default: 0.0.0.0)')
    parser.add_argument('--state', '-s', default='relaxed',
                        choices=list(STATES.keys()),
                        help='Initial mental state')
    parser.add_argument('--noise', type=float, default=0.08,
                        help='Noise level (0.0-1.0)')
    parser.add_argument('--blink-rate', type=float, default=0.25,
                        help='Blink rate per second')
    parser.add_argument('--no-browser', action='store_true',
                        help='Don\'t open browser automatically')
    parser.add_argument('--auto-cycle', type=float, default=0,
                        help='Auto-cycle states every N seconds')
    parser.add_argument('--log', type=str, default=None,
                        help='Save CSV log to file')

    args = parser.parse_args()

    global sim
    sim = EEGSimulator(
        state=args.state,
        noise=args.noise,
        blink_rate=args.blink_rate,
    )

    log_file = None
    log_writer = None
    if args.log:
        log_file = open(args.log, 'w', newline='')
        log_writer = csv.writer(log_file)
        log_writer.writerow([
            'timestamp_ms', 'attention', 'meditation', 'blink',
            'raw_wave', 'delta', 'theta', 'low_alpha', 'high_alpha',
            'low_beta', 'high_beta', 'low_gamma', 'high_gamma',
            'servo0', 'servo1', 'servo2', 'servo3', 'servo4', 'state'
        ])

    t_sim = threading.Thread(target=simulation_thread, daemon=True)
    t_sim.start()

    if args.auto_cycle > 0:
        state_names = list(STATES.keys())
        def cycler():
            idx = state_names.index(args.state)
            while True:
                time.sleep(args.auto_cycle)
                idx = (idx + 1) % len(state_names)
                sim.set_state(state_names[idx])
        t_cycle = threading.Thread(target=cycler, daemon=True)
        t_cycle.start()

    server = HTTPServer((args.bind, args.port), Handler)

    url = f"http://{'localhost' if args.bind == '0.0.0.0' else args.bind}:{args.port}"
    print(f"\n{'='*60}")
    print(f"  Axis Simulation Dashboard")
    print(f"  State: {args.state} ({STATES[args.state]['desc']})")
    print(f"  {'Logging: ' + args.log if args.log else 'No logging'}")
    print(f"{'='*60}")
    print(f"\n  🌐  Open browser:  {url}")
    print(f"\n  Controls in browser:")
    print(f"    • Change mental state from dropdown")
    print(f"    • Auto-cycle through states")
    print(f"    • Reset chart data")
    print(f"\n  Press Ctrl+C to stop\n")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        global sim_running
        sim_running = False
        server.server_close()
        if log_file:
            log_file.close()
            print(f"Saved {len(sim.history)} rows to {args.log}")


if __name__ == '__main__':
    main()
