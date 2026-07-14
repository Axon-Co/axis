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

import os, sys, json, time, math, random, struct, csv
import argparse, threading, webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ── EEG Simulation Engine (embedded, same as simulate_eeg.py) ──────────

FS = 512.0
PINK_NOISE_OCTAVES = 6
BLINK_DURATION = 0.15

BANDS = {
    'delta': (0.5, 4), 'theta': (4, 8), 'low_alpha': (8, 10),
    'high_alpha': (10, 13), 'low_beta': (13, 18), 'high_beta': (18, 30),
    'low_gamma': (30, 40), 'high_gamma': (40, 50),
}

BAND_NAMES = list(BANDS.keys())

STATES = {
    'relaxed':   {'delta': 0.05, 'theta': 0.15, 'low_alpha': 0.30, 'high_alpha': 0.25, 'low_beta': 0.12, 'high_beta': 0.08, 'low_gamma': 0.03, 'high_gamma': 0.02, 'attention': 35, 'meditation': 75, 'desc': 'Eyes closed, relaxed alpha'},
    'focused':   {'delta': 0.02, 'theta': 0.05, 'low_alpha': 0.08, 'high_alpha': 0.05, 'low_beta': 0.30, 'high_beta': 0.25, 'low_gamma': 0.15, 'high_gamma': 0.10, 'attention': 82, 'meditation': 22, 'desc': 'Active concentration'},
    'meditative':{'delta': 0.08, 'theta': 0.35, 'low_alpha': 0.25, 'high_alpha': 0.10, 'low_beta': 0.10, 'high_beta': 0.05, 'low_gamma': 0.04, 'high_gamma': 0.03, 'attention': 42, 'meditation': 88, 'desc': 'Deep meditation'},
    'drowsy':    {'delta': 0.25, 'theta': 0.35, 'low_alpha': 0.15, 'high_alpha': 0.08, 'low_beta': 0.08, 'high_beta': 0.04, 'low_gamma': 0.03, 'high_gamma': 0.02, 'attention': 18, 'meditation': 58, 'desc': 'Drowsy'},
    'stressed':  {'delta': 0.03, 'theta': 0.08, 'low_alpha': 0.05, 'high_alpha': 0.04, 'low_beta': 0.25, 'high_beta': 0.30, 'low_gamma': 0.15, 'high_gamma': 0.10, 'attention': 68, 'meditation': 12, 'desc': 'Anxious/stressed'},
    'active':    {'delta': 0.04, 'theta': 0.10, 'low_alpha': 0.12, 'high_alpha': 0.08, 'low_beta': 0.25, 'high_beta': 0.20, 'low_gamma': 0.12, 'high_gamma': 0.09, 'attention': 72, 'meditation': 32, 'desc': 'Normal active'},
}

SERVO_OPEN  = [30, 10, 10, 10, 10]
SERVO_CLOSE = [150, 170, 170, 170, 160]


class EEGSimulator:
    def __init__(self, state='relaxed', noise=0.08, blink_rate=0.25, line_freq=50, rate=50):
        self.t = 0.0
        self.rate = rate
        self.dt = 1.0 / rate
        self.noise = noise
        self.line_freq = line_freq
        self.state = state
        self.profile = STATES[state].copy()
        self.target = self.profile.copy()
        self.transition_t = 1.0
        self.transition_dur = 3.0

        self.pink = [0.0] * PINK_NOISE_OCTAVES
        self.pink_counts = [0] * PINK_NOISE_OCTAVES
        self.pink_periods = [1 << i for i in range(PINK_NOISE_OCTAVES)]
        self.phases = {b: random.random() * 2 * math.pi for b in BAND_NAMES}
        self.osc_amps = {b: random.uniform(0.5, 1.5) for b in BAND_NAMES}
        self.next_blink = random.expovariate(blink_rate)
        self.blink_active = False
        self.blink_val = 0
        self.last_blink_strength = 0

        self.servo_angles = list(SERVO_OPEN)
        self.servo_targets = list(SERVO_OPEN)
        self.history = []

        self.sse_clients = []

    def set_state(self, name):
        if name in STATES and name != self.state:
            self.target = STATES[name].copy()
            self.transition_t = 0.0
            return True
        return False

    def pink_noise(self):
        val = 0.0
        for i in range(PINK_NOISE_OCTAVES):
            self.pink_counts[i] += 1
            if self.pink_counts[i] >= self.pink_periods[i]:
                self.pink[i] = random.random() * 2 - 1
                self.pink_counts[i] = 0
            val += self.pink[i]
        return val / PINK_NOISE_OCTAVES

    def blink(self):
        if not self.blink_active and self.t >= self.next_blink:
            self.blink_active = True
            self.blink_t = self.t
            self.blink_amp = random.uniform(200, 500)
            self.next_blink = self.t + random.expovariate(self.blink_rate)
            return 0.0
        if self.blink_active:
            dt = self.t - self.blink_t
            if dt < BLINK_DURATION:
                v = self.blink_amp * math.exp(-((dt - 0.075)**2) / (2 * (0.025)**2))
                return v
            self.blink_active = False
        return 0.0

    def update_servos(self, att, med):
        grip = 0
        if att > 55: grip = 100
        elif att > 30: grip = (att - 30) * 100 // 25
        for i in range(5):
            self.servo_targets[i] = SERVO_OPEN[i] + (SERVO_CLOSE[i] - SERVO_OPEN[i]) * grip // 100
        for i in range(5):
            diff = self.servo_targets[i] - self.servo_angles[i]
            self.servo_angles[i] += diff * 0.15 + random.gauss(0, 0.5)
            self.servo_angles[i] = max(0, min(180, self.servo_angles[i]))

    def step(self):
        self.t += self.dt

        if self.transition_t < 1.0:
            self.transition_t += self.dt / self.transition_dur
            if self.transition_t >= 1.0:
                self.profile = self.target.copy()
                self.state = [k for k,v in STATES.items() if v == self.target][0] if self.target in STATES.values() else self.state
            else:
                s = self.transition_t * self.transition_t * (3 - 2 * self.transition_t)
                for k in self.profile:
                    if k in ('attention', 'meditation'):
                        base = STATES.get(self.state, STATES['relaxed']).get(k, 50)
                        self.profile[k] = base + (self.target[k] - base) * s
                    elif k in BANDS:
                        base = STATES.get(self.state, STATES['relaxed']).get(k, 0.05)
                        self.profile[k] = base + (self.target[k] - base) * s

        raw = 0.0
        band_powers = {}
        for i, b in enumerate(BAND_NAMES):
            amp = self.profile.get(b, 0.05) * 500
            raw += amp * math.sin(2 * math.pi * (3 + i * 5) * self.t + self.phases[b])
            band_powers[b] = max(1, int(amp * 200 * (0.85 + 0.3 * random.random())))

        raw += self.pink_noise() * 20 * self.noise
        bv = self.blink()
        raw += bv
        raw = max(-32768, min(32767, int(raw)))

        att = max(0, min(100, self.profile.get('attention', 50) + random.gauss(0, 4)))
        med = max(0, min(100, self.profile.get('meditation', 50) + random.gauss(0, 4)))
        blink_out = int(abs(bv)) if abs(bv) > 30 else 0
        poor = 0 if self.noise < 0.3 else int(self.noise * 50)

        self.last_blink_strength = blink_out
        self.update_servos(att, med)

        alpha = band_powers['low_alpha'] + band_powers['high_alpha']
        beta = band_powers['low_beta'] + band_powers['high_beta']
        theta = band_powers['theta']
        gamma = band_powers['low_gamma'] + band_powers['high_gamma']

        data = {
            't': round(self.t, 3),
            'attention': int(att),
            'meditation': int(med),
            'blink': min(255, blink_out),
            'signal_quality': max(0, 100 - poor * 10),
            'raw_wave': int(raw),
            'band_powers': {b: band_powers[b] for b in BAND_NAMES},
            'alpha_beta_ratio': round(alpha / beta, 3) if beta > 0 else 0,
            'theta_gamma_ratio': round(theta / gamma, 3) if gamma > 0 else 0,
            'att_med_ratio': round(att / (med + 1), 3),
            'servos': [round(a, 1) for a in self.servo_angles],
            'state': self.state,
        }
        self.history.append(data)
        if len(self.history) > 5000:
            self.history = self.history[-5000:]
        return data


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
                if sim.set_state(name):
                    self.send_json({'status': 'ok', 'state': name, 'desc': STATES[name]['desc']})
                else:
                    self.send_json({'status': 'error', 'message': f'Unknown or current state: {name}'}, 400)
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
<title>Axis Simulation Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #070b18; color: #c8d6e5; padding: 16px; }

.header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.header h1 { color: #00ff88; font-size: 22px; }
.header .badge { padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.badge-state { background: #1a3a2a; color: #00ff88; }
.badge-online { background: #1a2a3a; color: #00ccff; }
.header .controls { margin-left: auto; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.controls select, .controls input { background: #141a2e; color: #c8d6e5; border: 1px solid #2a3460; padding: 4px 10px; border-radius: 4px; font-size: 12px; }
.controls button { background: #00ff88; color: #070b18; border: none; padding: 4px 14px; border-radius: 4px; font-weight: 600; cursor: pointer; font-size: 12px; }
.controls button:hover { background: #00cc6a; }

.top-row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.metric { flex: 1; min-width: 140px; background: #101624; border: 1px solid #1a2240; border-radius: 10px; padding: 12px 16px; text-align: center; position: relative; overflow: hidden; }
.metric .label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #576574; }
.metric .value { font-size: 32px; font-weight: 700; margin: 2px 0; font-family: 'JetBrains Mono', monospace; }
.metric .unit { font-size: 11px; color: #576574; }
.metric .mini-bar { height: 3px; border-radius: 2px; margin-top: 4px; transition: width 0.3s; }

.chart-row { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-bottom: 12px; }
.chart-row-full { grid-template-columns: 1fr; }

.card { background: #101624; border: 1px solid #1a2240; border-radius: 10px; padding: 14px; }
.card h3 { color: #88a0c0; font-size: 12px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
.card canvas { width: 100% !important; max-height: 200px; }

.bottom-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }

.stat-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.stat-table td { padding: 3px 6px; }
.stat-table .key { color: #576574; }
.stat-table .val { color: #c8d6e5; font-weight: 600; text-align: right; font-family: monospace; }

#servo-viz { display: flex; gap: 8px; justify-content: center; align-items: flex-end; height: 140px; padding: 10px 0; }
.servo-col { display: flex; flex-direction: column; align-items: center; gap: 4px; width: 50px; }
.servo-col .bar { width: 30px; border-radius: 4px 4px 0 0; transition: height 0.3s; min-height: 4px; }
.servo-col .s-name { font-size: 9px; color: #576574; text-transform: uppercase; }
.servo-col .s-val { font-size: 10px; font-weight: 600; color: #c8d6e5; }

@media (max-width: 900px) {
  .chart-row { grid-template-columns: 1fr; }
  .bottom-row { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<div class="header">
  <h1>🧠 Axis Simulation</h1>
  <span class="badge badge-state" id="stateBadge">relaxed</span>
  <span class="badge badge-online" id="onlineBadge">● LIVE</span>
  <span style="font-size:12px;color:#576574" id="timeDisplay">0s</span>
  <div class="controls">
    <select id="stateSelect" onchange="setState(this.value)">
      <option value="relaxed">Relaxed</option>
      <option value="focused">Focused</option>
      <option value="meditative">Meditative</option>
      <option value="drowsy">Drowsy</option>
      <option value="stressed">Stressed</option>
      <option value="active">Active</option>
    </select>
    <select id="autoCycle" onchange="setAutoCycle(this.value)">
      <option value="0">No auto-cycle</option>
      <option value="5">Cycle every 5s</option>
      <option value="10">Cycle every 10s</option>
      <option value="20">Cycle every 20s</option>
    </select>
    <button onclick="resetStats()">Reset</button>
  </div>
</div>

<div class="top-row" id="metrics"></div>

<div class="chart-row">
  <div class="card"><h3>📈 Attention & Meditation</h3><canvas id="chartAttMed"></canvas></div>
  <div class="card"><h3>🥧 Band Power</h3><canvas id="chartPie"></canvas></div>
</div>

<div class="chart-row chart-row-full">
  <div class="card"><h3>🌊 EEG Frequency Bands (log scale)</h3><canvas id="chartBands"></canvas></div>
</div>

<div class="bottom-row">
  <div class="card"><h3>🤖 Servo Positions</h3><div id="servo-viz"></div></div>
  <div class="card"><h3>📊 Statistics</h3><table class="stat-table" id="statsTable"></table></div>
  <div class="card"><h3>📐 EEG Ratios</h3>
    <table class="stat-table" id="ratiosTable">
      <tr><td class="key">α/β Ratio</td><td class="val" id="rAb">—</td></tr>
      <tr><td class="key">θ/γ Ratio</td><td class="val" id="rTg">—</td></tr>
      <tr><td class="key">Att/Med Ratio</td><td class="val" id="rAm">—</td></tr>
      <tr><td class="key">Signal Quality</td><td class="val" id="rSig">—</td></tr>
    </table>
  </div>
</div>

<script>
const BAND_COLORS = ['#ff0000','#ff8800','#ffff00','#00ff00','#00ccff','#0066ff','#8800ff','#ff00ff'];
const SERVO_COLORS = ['#ff6b6b','#ffaa00','#ffdd00','#00ccff','#00ff88'];
const BAND_NAMES = ['delta','theta','low_alpha','high_alpha','low_beta','high_beta','low_gamma','high_gamma'];
const METRIC_KEYS = [
  {key:'attention', label:'Attention', color:'#00ff88', max:100, unit:'%'},
  {key:'meditation', label:'Meditation', color:'#00ccff', max:100, unit:'%'},
  {key:'blink', label:'Blink', color:'#ff00ff', max:255, unit:''},
  {key:'signal_quality', label:'Signal', color:'#ffaa00', max:100, unit:'%'},
];

let charts = {};
let history = [];
const MAX_HISTORY = 300;
let autoCycleTimer = null;
let stateNames = ['relaxed','focused','meditative','drowsy','stressed','active'];
let stateIdx = 0;

function createChart(id, type, datasets, extra) {
  const ctx = document.getElementById(id).getContext('2d');
  return new Chart(ctx, {
    type,
    data: { labels: [], datasets },
    options: Object.assign({
      responsive: true, maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'nearest', intersect: false },
      plugins: { legend: { labels: { color: '#88a0c0', font: { size: 10 } } } },
      scales: {
        x: { ticks: { color: '#576574', maxTicksLimit: 10, font: { size: 9 } }, grid: { color: '#1a2240' } },
        y: { ticks: { color: '#576574', font: { size: 9 } }, grid: { color: '#1a2240' } },
      }
    }, extra)
  });
}

function initCharts() {
  charts.attMed = createChart('chartAttMed', 'line', [
    { label: 'Attention', data: [], borderColor: '#00ff88', backgroundColor: 'rgba(0,255,136,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
    { label: 'Meditation', data: [], borderColor: '#00ccff', backgroundColor: 'rgba(0,204,255,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
    { label: 'Blink', data: [], borderColor: '#ff00ff', backgroundColor: 'rgba(255,0,255,0.05)', fill: true, tension: 0.1, pointRadius: 0 },
  ], { scales: { y: { min: 0, max: 100 } } });

  charts.pie = new Chart(document.getElementById('chartPie'), {
    type: 'doughnut',
    data: { labels: BAND_NAMES, datasets: [{ data: BAND_NAMES.map(() => 0), backgroundColor: BAND_COLORS }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { position: 'right', labels: { color: '#88a0c0', font: { size: 9 } } },
        tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.parsed.toLocaleString() } }
      }
    }
  });

  charts.bands = createChart('chartBands', 'line',
    BAND_NAMES.map((b, i) => ({ label: b, data: [], borderColor: BAND_COLORS[i], fill: false, tension: 0.3, pointRadius: 0 })),
    { scales: { y: { type: 'logarithmic', min: 1 } } }
  );
}

function updateMetrics(data) {
  const container = document.getElementById('metrics');
  let html = '';
  METRIC_KEYS.forEach(m => {
    const v = data[m.key] || 0;
    const pct = (v / m.max * 100).toFixed(0);
    html += `<div class="metric">
      <div class="label">${m.label}</div>
      <div class="value" style="color:${m.color}">${v}</div>
      <div class="mini-bar" style="width:${pct}%;background:${m.color}"></div>
    </div>`;
  });
  html += `<div class="metric">
    <div class="label">STATE</div>
    <div class="value" style="color:#ffdd00;font-size:22px">${data.state||'?'}</div>
    <div class="unit">${data.state_desc||''}</div>
  </div>`;
  container.innerHTML = html;
}

function updateServos(data) {
  const s = data.servos || [0,0,0,0,0];
  const names = ['Thumb','Index','Middle','Ring','Pinky'];
  const maxH = 120;
  let html = '';
  s.forEach((v, i) => {
    const h = Math.max(4, v / 180 * maxH);
    html += `<div class="servo-col">
      <div class="bar" style="height:${h}px;background:${SERVO_COLORS[i]}"></div>
      <div class="s-val">${v.toFixed(0)}°</div>
      <div class="s-name">${names[i]}</div>
    </div>`;
  });
  document.getElementById('servo-viz').innerHTML = html;
}

function updateStats(data) {
  const s = data || {};
  const stats = [
    ['Attention', s.attention?.avg || '—', s.attention?.max || '—'],
    ['Meditation', s.meditation?.avg || '—', s.meditation?.max || '—'],
    ['Blinks', s.blink?.count || 0, s.blink?.max || '—'],
  ];
  let html = '<tr><td></td><td class="val">Avg</td><td class="val">Max</td></tr>';
  stats.forEach(([label, avg, max]) => {
    html += `<tr><td class="key">${label}</td><td class="val">${avg}</td><td class="val">${max}</td></tr>`;
  });
  html += `<tr><td class="key">Samples</td><td class="val" colspan="2">${s.samples||0}</td></tr>`;
  html += `<tr><td class="key">Uptime</td><td class="val" colspan="2">${(s.uptime||0).toFixed(1)}s</td></tr>`;
  document.getElementById('statsTable').innerHTML = html;
}

function updateRatios(data) {
  document.getElementById('rAb').textContent = data.alpha_beta_ratio || '—';
  document.getElementById('rTg').textContent = data.theta_gamma_ratio || '—';
  document.getElementById('rAm').textContent = data.att_med_ratio || '—';
  document.getElementById('rSig').textContent = (data.signal_quality || 0) + '%';
}

function updateCharts(data) {
  history.push(data);
  if (history.length > MAX_HISTORY) history.shift();
  const labels = history.map(d => d.t.toFixed(1));

  if (!charts.attMed) initCharts();

  // Att/Med chart — in-place update
  charts.attMed.data.labels = labels;
  charts.attMed.data.datasets[0].data = history.map(d => d.attention);
  charts.attMed.data.datasets[1].data = history.map(d => d.meditation);
  charts.attMed.data.datasets[2].data = history.map(d => d.blink);
  charts.attMed.update('none');

  // Pie chart — in-place update
  const last = history[history.length - 1];
  const bp = last ? last.band_powers : {};
  const pieVals = BAND_NAMES.map(b => bp[b] || 1);
  const total = pieVals.reduce((a, b) => a + b, 0);
  charts.pie.data.datasets[0].data = pieVals;
  charts.pie.data.labels = BAND_NAMES.map((b, i) =>
    b + ' (' + (total > 0 ? (pieVals[i]/total*100).toFixed(1) : 0) + '%)');
  charts.pie.update('none');

  // Band power chart — in-place update
  charts.bands.data.labels = labels;
  for (let i = 0; i < BAND_NAMES.length; i++) {
    charts.bands.data.datasets[i].data = history.map(d => Math.max(1, (d.band_powers||{})[BAND_NAMES[i]] || 1));
  }
  charts.bands.update('none');
}

async function poll() {
  try {
    const r = await fetch('/api/latest');
    const data = await r.json();
    document.getElementById('stateBadge').textContent = data.state || '?';
    document.getElementById('stateSelect').value = data.state || 'relaxed';
    document.getElementById('timeDisplay').textContent = (data.t || 0).toFixed(1) + 's';
    updateMetrics(data);
    updateServos(data);
    updateRatios(data);
    updateCharts(data);

    const r2 = await fetch('/api/stats');
    const stats = await r2.json();
    updateStats(stats);
  } catch(e) {}
}

async function setState(name) {
  await fetch('/api/state?name=' + name);
}

function setAutoCycle(secs) {
  if (autoCycleTimer) { clearInterval(autoCycleTimer); autoCycleTimer = null; }
  if (secs > 0) {
    autoCycleTimer = setInterval(async () => {
      const r = await fetch('/api/state');
      const data = await r.json();
      stateIdx = (stateNames.indexOf(data.state) + 1) % stateNames.length;
      await setState(stateNames[stateIdx]);
    }, secs * 1000);
  }
}

function resetStats() {
  history = [];
  Object.values(charts).forEach(c => c.destroy());
  charts = {};
}

initCharts();
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
