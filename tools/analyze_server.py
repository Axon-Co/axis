#!/usr/bin/env python3
"""
Axis Web Analysis Dashboard — real-time CSV visualization in your browser.

Serves a Chart.js dashboard with EEG statistics, time-series plots,
band power distribution, and servo position history.

Usage:
    python tools/analyze_server.py /path/to/csv_logs/  --port 8080
    python tools/analyze_server.py /sdcard/             # default port 8080
    python tools/analyze_server.py single_log.csv       # single file mode
"""

import os
import sys
import csv
import json
import math
import argparse
import statistics
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


DATA_DIR = None
SINGLE_FILE = None
CACHED_RECORDS = {}
CACHED_STATS = {}


def load_csv(path):
    rows = []
    try:
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception as e:
        return [], str(e)
    return rows, None


def compute_stats(rows):
    fields = ['attention', 'meditation', 'blink_strength', 'raw_wave',
              'delta', 'theta', 'low_alpha', 'high_alpha',
              'low_beta', 'high_beta', 'low_gamma', 'high_gamma']
    stats = {}
    for field in fields:
        vals = []
        for r in rows:
            try:
                v = float(r.get(field, 0))
                vals.append(v)
            except (ValueError, TypeError):
                continue
        if vals:
            stats[field] = {
                'min': round(min(vals), 1),
                'max': round(max(vals), 1),
                'mean': round(statistics.mean(vals), 1),
                'median': round(statistics.median(vals), 1),
                'stdev': round(statistics.stdev(vals), 2) if len(vals) > 1 else 0,
                'p25': round(statistics.quantiles(vals, n=4)[0], 1) if len(vals) >= 4 else 0,
                'p75': round(statistics.quantiles(vals, n=4)[2], 1) if len(vals) >= 4 else 0,
            }
    return stats


def compute_correlations(rows):
    fields = ['attention', 'meditation', 'delta', 'theta', 'low_alpha',
              'high_alpha', 'low_beta', 'high_beta', 'low_gamma', 'high_gamma']
    data = {f: [] for f in fields}
    for r in rows:
        for f in fields:
            try:
                data[f].append(float(r.get(f, 0)))
            except (ValueError, TypeError):
                data[f].append(0)

    correlations = {}
    for i, f1 in enumerate(fields):
        for f2 in fields[i + 1:]:
            n = min(len(data[f1]), len(data[f2]))
            if n < 3:
                continue
            m1, m2 = sum(data[f1][:n]) / n, sum(data[f2][:n]) / n
            num = sum((data[f1][j] - m1) * (data[f2][j] - m2) for j in range(n))
            d1 = math.sqrt(sum((data[f1][j] - m1) ** 2 for j in range(n)))
            d2 = math.sqrt(sum((data[f2][j] - m2) ** 2 for j in range(n)))
            corr = num / (d1 * d2 + 1e-10)
            correlations[f"{f1}_vs_{f2}"] = round(corr, 3)
    return correlations


def compute_band_ratios(rows):
    ratios = {'alpha_beta': [], 'theta_gamma': [], 'att_med': []}
    for r in rows:
        try:
            lb = float(r.get('low_beta', 0))
            hb = float(r.get('high_beta', 0))
            la = float(r.get('low_alpha', 0))
            ha = float(r.get('high_alpha', 0))
            t = float(r.get('theta', 0))
            lg = float(r.get('low_gamma', 0))
            hg = float(r.get('high_gamma', 0))
            att = float(r.get('attention', 0))
            med = float(r.get('meditation', 0))

            beta = lb + hb
            alpha = la + ha
            gamma = lg + hg

            ratios['alpha_beta'].append(round(alpha / beta, 3) if beta > 0 else 0)
            ratios['theta_gamma'].append(round(t / gamma, 3) if gamma > 0 else 0)
            ratios['att_med'].append(round(att / (med + 1), 3))
        except (ValueError, TypeError):
            continue
    return ratios


def get_servo_data(rows):
    servos = {i: [] for i in range(5)}
    for r in rows:
        for i in range(5):
            try:
                servos[i].append(float(r.get(f'servo{i}', 0)))
            except (ValueError, TypeError):
                servos[i].append(0)
    return servos


def find_csv_files(directory):
    files = []
    for f in sorted(os.listdir(directory)):
        if f.endswith('.csv') and not f.startswith('.'):
            path = os.path.join(directory, f)
            size = os.path.getsize(path)
            mtime = os.path.getmtime(path)
            files.append({
                'name': f,
                'path': path,
                'size': size,
                'mtime': datetime.fromtimestamp(mtime).isoformat(),
                'rows': 0,
            })
    for f in files:
        try:
            with open(f['path'], 'r') as fh:
                f['rows'] = sum(1 for _ in fh) - 1
        except:
            f['rows'] = 0
    return files


class AnalysisHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/':
            self.send_html(INDEX_HTML)
        elif path == '/api/files':
            if DATA_DIR and os.path.isdir(DATA_DIR):
                files = find_csv_files(DATA_DIR)
                self.send_json({'files': files})
            elif SINGLE_FILE:
                self.send_json({'files': [{
                    'name': os.path.basename(SINGLE_FILE),
                    'path': SINGLE_FILE,
                    'size': os.path.getsize(SINGLE_FILE),
                    'mtime': datetime.fromtimestamp(os.path.getmtime(SINGLE_FILE)).isoformat(),
                    'rows': 0,
                }]})
            else:
                self.send_json({'files': []})

        elif path == '/api/data':
            file_path = params.get('file', [None])[0]
            if not file_path:
                if SINGLE_FILE:
                    file_path = SINGLE_FILE
                elif DATA_DIR:
                    files = find_csv_files(DATA_DIR)
                    file_path = files[0]['path'] if files else None

            if not file_path or not os.path.isfile(file_path):
                self.send_json({'error': 'File not found'}, 404)
                return

            if file_path in CACHED_RECORDS:
                rows = CACHED_RECORDS[file_path]
            else:
                rows, err = load_csv(file_path)
                if err:
                    self.send_json({'error': err}, 500)
                    return
                CACHED_RECORDS[file_path] = rows

            stats = compute_stats(rows)
            correlations = compute_correlations(rows)
            ratios = compute_band_ratios(rows)
            servos = get_servo_data(rows)

            # Time series (downsample to max 2000 points for performance)
            max_points = 2000
            step = max(1, len(rows) // max_points)
            time_series = []
            for i, r in enumerate(rows):
                if i % step == 0:
                    try:
                        time_series.append({
                            't': int(r.get('timestamp_ms', i * 100)) / 1000.0,
                            'att': int(r.get('attention', 0)),
                            'med': int(r.get('meditation', 0)),
                            'blink': int(r.get('blink_strength', 0)),
                            'raw': int(r.get('raw_wave', 0)),
                            'delta': int(r.get('delta', 0)),
                            'theta': int(r.get('theta', 0)),
                            'low_alpha': int(r.get('low_alpha', 0)),
                            'high_alpha': int(r.get('high_alpha', 0)),
                            'low_beta': int(r.get('low_beta', 0)),
                            'high_beta': int(r.get('high_beta', 0)),
                            'low_gamma': int(r.get('low_gamma', 0)),
                            'high_gamma': int(r.get('high_gamma', 0)),
                            's0': int(r.get('servo0', 0)),
                            's1': int(r.get('servo1', 0)),
                            's2': int(r.get('servo2', 0)),
                            's3': int(r.get('servo3', 0)),
                            's4': int(r.get('servo4', 0)),
                        })
                    except (ValueError, TypeError):
                        continue

            self.send_json({
                'filename': os.path.basename(file_path),
                'total_records': len(rows),
                'duration_s': round((time_series[-1]['t'] - time_series[0]['t']) if len(time_series) > 1 else 0, 1),
                'stats': stats,
                'correlations': correlations,
                'ratios': ratios,
                'servos': servos,
                'time_series': time_series,
            })

        elif path == '/api/clear_cache':
            CACHED_RECORDS.clear()
            CACHED_STATS.clear()
            self.send_json({'status': 'ok'})

        else:
            self.send_error(404)

    def send_html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))

    def log_message(self, format, *args):
        if args[0] != '/api/data':
            super().log_message(format, *args)


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Axis EEG Analysis Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0e1a; color: #c8d6e5; padding: 20px; }
h1 { color: #00ff88; font-size: 24px; margin-bottom: 4px; }
h2 { color: #88ffbb; font-size: 18px; margin: 20px 0 10px; }
.subtitle { color: #576574; font-size: 13px; margin-bottom: 20px; }
.controls { background: #141a2e; border: 1px solid #1e2744; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.controls label { color: #88a0c0; font-size: 13px; }
.controls select { background: #1a2040; color: #c8d6e5; border: 1px solid #2a3460; padding: 6px 12px; border-radius: 4px; font-size: 13px; min-width: 220px; }
.controls button { background: #00ff88; color: #0a0e1a; border: none; padding: 6px 16px; border-radius: 4px; font-weight: 600; cursor: pointer; font-size: 13px; }
.controls button:hover { background: #00cc6a; }
.controls .file-info { font-size: 12px; color: #576574; margin-left: auto; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat-card { background: #141a2e; border: 1px solid #1e2744; border-radius: 8px; padding: 12px 16px; }
.stat-card h3 { color: #88a0c0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.stat-row { display: flex; justify-content: space-between; font-size: 13px; padding: 2px 0; }
.stat-row .label { color: #576574; }
.stat-row .value { color: #c8d6e5; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
.stat-row .value.high { color: #00ff88; }
.stat-row .value.low { color: #ff6b6b; }

.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 16px; margin-bottom: 20px; }
.chart-card { background: #141a2e; border: 1px solid #1e2744; border-radius: 8px; padding: 16px; }
.chart-card h3 { color: #88a0c0; font-size: 13px; margin-bottom: 10px; }
.chart-card canvas { max-height: 300px; }

.ratio-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.ratio-card { background: #141a2e; border: 1px solid #1e2744; border-radius: 8px; padding: 16px; text-align: center; }
.ratio-card h3 { color: #88a0c0; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
.ratio-card .value { font-size: 28px; font-weight: 700; margin: 4px 0; }
.ratio-card .desc { font-size: 11px; color: #576574; }

.server-info { text-align: center; padding: 20px; color: #576574; font-size: 12px; }

.loading { text-align: center; padding: 60px; color: #576574; font-size: 16px; }
.error { text-align: center; padding: 40px; color: #ff6b6b; }
</style>
</head>
<body>
<h1>🧠 Axis EEG Analysis Dashboard</h1>
<div class="subtitle">CSV log analyzer with real-time statistics and visualization</div>

<div class="controls">
  <label for="fileSelect">Log File:</label>
  <select id="fileSelect" onchange="loadFile(this.value)"><option value="">Loading...</option></select>
  <button onclick="loadFile(document.getElementById('fileSelect').value)">↻ Reload</button>
  <button onclick="clearCache()">🗑 Clear Cache</button>
  <span class="file-info" id="fileInfo">—</span>
</div>

<div id="dashboard">
  <div class="loading">Loading data...</div>
</div>

<div class="server-info" id="serverInfo"></div>

<script>
let charts = {};

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}

async function init() {
  const data = await fetchJSON('/api/files');
  const sel = document.getElementById('fileSelect');
  sel.innerHTML = '';
  if (data.files && data.files.length > 0) {
    data.files.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.path;
      opt.textContent = f.name + ' (' + f.rows + ' rows, ' + (f.size / 1024).toFixed(1) + ' KB)';
      sel.appendChild(opt);
    });
    loadFile(data.files[0].path);
  } else {
    sel.innerHTML = '<option value="">No CSV files found</option>';
    document.getElementById('dashboard').innerHTML = '<div class="error">No CSV log files found in the data directory.</div>';
  }
}

async function loadFile(path) {
  if (!path) return;
  document.getElementById('dashboard').innerHTML = '<div class="loading">📊 Loading analysis...</div>';
  document.getElementById('fileInfo').textContent = 'Loading...';

  const data = await fetchJSON('/api/data?file=' + encodeURIComponent(path));
  if (data.error) {
    document.getElementById('dashboard').innerHTML = '<div class="error">Error: ' + data.error + '</div>';
    return;
  }

  document.getElementById('fileInfo').textContent =
    data.filename + ' — ' + data.total_records.toLocaleString() + ' records, ' +
    data.duration_s.toFixed(1) + 's duration';
  renderDashboard(data);
}

function renderDashboard(data) {
  const stats = data.stats;
  const ts = data.time_series;
  const n = data.total_records;

  // Destroy old charts
  Object.values(charts).forEach(c => c.destroy());
  charts = {};

  let html = '';

  // Stats cards
  html += '<div class="stats-grid">';
  const att = stats.attention || {};
  const med = stats.meditation || {};
  const blink = stats.blink_strength || {};
  html += statCard('Attention', att, '%');
  html += statCard('Meditation', med, '%');
  html += statCard('Blink Strength', blink, '');
  html += statCard('Signal Quality', {
    mean: (100 - (stats.raw_wave ? stats.raw_wave.mean * 0.01 : 0)).toFixed(1),
    min: '—', max: '—', median: '—', stdev: '—'
  }, '%');
  html += '</div>';

  // Ratios
  const ratios = data.ratios || {};
  const rab = ratios.alpha_beta || [];
  const rtg = ratios.theta_gamma || [];
  const ram = ratios.att_med || [];
  const avg = a => a.length ? (a.reduce((s, v) => s + v, 0) / a.length).toFixed(3) : '—';
  html += '<div class="ratio-grid">';
  html += ratioCard('α/β Ratio', avg(rab), 'Relaxation vs Focus', '#00ff88');
  html += ratioCard('θ/γ Ratio', avg(rtg), 'Meditation vs Processing', '#ffaa00');
  html += ratioCard('Att/Med Ratio', avg(ram), 'Focus vs Relaxation', '#00ccff');
  html += '</div>';

  // Charts
  html += '<div class="chart-grid">';
  html += '<div class="chart-card"><h3>📈 Attention & Meditation</h3><canvas id="chartAttMed"></canvas></div>';
  html += '<div class="chart-card"><h3>📊 Servo Positions</h3><canvas id="chartServos"></canvas></div>';
  html += '<div class="chart-card"><h3>🌊 EEG Frequency Bands</h3><canvas id="chartBands"></canvas></div>';
  html += '<div class="chart-card"><h3>🥧 Band Power Distribution</h3><canvas id="chartPie"></canvas></div>';
  html += '<div class="chart-card" style="grid-column: 1 / -1;"><h3>📉 All Signals Overview</h3><canvas id="chartOverview"></canvas></div>';
  html += '</div>';

  document.getElementById('dashboard').innerHTML = html;

  // Chart 1: Attention & Meditation
  charts.attMed = new Chart(document.getElementById('chartAttMed'), {
    type: 'line',
    data: {
      labels: ts.map(r => r.t.toFixed(1)),
      datasets: [
        { label: 'Attention', data: ts.map(r => r.att), borderColor: '#00ff88', backgroundColor: 'rgba(0,255,136,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
        { label: 'Meditation', data: ts.map(r => r.med), borderColor: '#00ccff', backgroundColor: 'rgba(0,204,255,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
        { label: 'Blink', data: ts.map(r => r.blink), borderColor: '#ff00ff', backgroundColor: 'rgba(255,0,255,0.05)', fill: true, tension: 0.1, pointRadius: 0 },
      ]
    },
    options: chartOpts('Time (s)', 'Value', { y: { max: 100 } })
  });

  // Chart 2: Servos
  charts.servos = new Chart(document.getElementById('chartServos'), {
    type: 'line',
    data: {
      labels: ts.map(r => r.t.toFixed(1)),
      datasets: ['s0','s1','s2','s3','s4'].map((k, i) => ({
        label: 'Servo ' + i, data: ts.map(r => r[k]), borderColor: servoColors[i],
        tension: 0.3, pointRadius: 0
      }))
    },
    options: chartOpts('Time (s)', 'Angle (°)', { y: { min: 0, max: 180 } })
  });

  // Chart 3: EEG Bands
  const bandKeys = ['delta','theta','low_alpha','high_alpha','low_beta','high_beta','low_gamma','high_gamma'];
  const bandColors = ['#ff0000','#ff8800','#ffff00','#00ff00','#00ccff','#0066ff','#8800ff','#ff00ff'];
  charts.bands = new Chart(document.getElementById('chartBands'), {
    type: 'line',
    data: {
      labels: ts.map(r => r.t.toFixed(1)),
      datasets: bandKeys.map((k, i) => ({
        label: k, data: ts.map(r => r[k]), borderColor: bandColors[i],
        backgroundColor: bandColors[i].replace(')', ',0.1)').replace('rgb', 'rgba'),
        fill: false, tension: 0.3, pointRadius: 0, yAxisID: 'y1',
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top', labels: { color: '#88a0c0', font: { size: 10 } } } },
      scales: {
        x: { title: { display: true, text: 'Time (s)', color: '#576574' }, ticks: { color: '#576574', maxTicksLimit: 20 } },
        y1: { type: 'logarithmic', title: { display: true, text: 'Power (log)', color: '#576574' }, ticks: { color: '#576574' }, grid: { color: '#1e2744' } },
      }
    }
  });

  // Chart 4: Band Power Pie
  if (ts.length > 0) {
    const last = ts[ts.length - 1];
    const pieData = bandKeys.map(k => last[k] || 0);
    const total = pieData.reduce((a, b) => a + b, 0);
    charts.pie = new Chart(document.getElementById('chartPie'), {
      type: 'doughnut',
      data: {
        labels: bandKeys.map((k, i) => k + ' (' + (total > 0 ? (pieData[i] / total * 100).toFixed(1) : 0) + '%)'),
        datasets: [{ data: pieData, backgroundColor: bandColors }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { color: '#88a0c0', font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.parsed.toLocaleString() } }
        }
      }
    });
  }

  // Chart 5: Overview (mixed)
  charts.overview = new Chart(document.getElementById('chartOverview'), {
    type: 'line',
    data: {
      labels: ts.map(r => r.t.toFixed(1)),
      datasets: [
        { label: 'Attention', data: ts.map(r => r.att), borderColor: '#00ff88', tension: 0.3, pointRadius: 0, yAxisID: 'y' },
        { label: 'Meditation', data: ts.map(r => r.med), borderColor: '#00ccff', tension: 0.3, pointRadius: 0, yAxisID: 'y' },
        { label: 'Delta', data: ts.map(r => r.delta), borderColor: '#ff0000', tension: 0.3, pointRadius: 0, yAxisID: 'y1' },
        { label: 'Theta', data: ts.map(r => r.theta), borderColor: '#ff8800', tension: 0.3, pointRadius: 0, yAxisID: 'y1' },
        { label: 'Low Alpha', data: ts.map(r => r.low_alpha), borderColor: '#ffff00', tension: 0.3, pointRadius: 0, yAxisID: 'y1' },
        { label: 'Low Beta', data: ts.map(r => r.low_beta), borderColor: '#00ccff', tension: 0.3, pointRadius: 0, yAxisID: 'y1' },
        { label: 'Servo 0', data: ts.map(r => r.s0), borderColor: '#ffffff', borderDash: [4, 2], tension: 0.3, pointRadius: 0, yAxisID: 'y2' },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top', labels: { color: '#88a0c0', font: { size: 10 } } } },
      scales: {
        x: { title: { display: true, text: 'Time (s)', color: '#576574' }, ticks: { color: '#576574', maxTicksLimit: 30 } },
        y: { position: 'left', title: { display: true, text: 'EEG Value', color: '#00ff88' }, min: 0, max: 100, ticks: { color: '#576574' }, grid: { color: '#1e2744' } },
        y1: { position: 'right', type: 'logarithmic', title: { display: true, text: 'Band Power (log)', color: '#ff8800' }, ticks: { color: '#576574' }, grid: { display: false } },
        y2: { position: 'right', title: { display: true, text: 'Servo Angle', color: '#ffffff' }, min: 0, max: 180, ticks: { color: '#576574' }, grid: { display: false } },
      }
    }
  });
}

function statCard(title, s, unit) {
  if (!s || !s.mean) return '';
  return `<div class="stat-card">
    <h3>${title}</h3>
    <div class="stat-row"><span class="label">Mean</span><span class="value high">${s.mean}${unit}</span></div>
    <div class="stat-row"><span class="label">Median</span><span class="value">${s.median}${unit}</span></div>
    <div class="stat-row"><span class="label">Min / Max</span><span class="value">${s.min}${unit} / ${s.max}${unit}</span></div>
    <div class="stat-row"><span class="label">P25 / P75</span><span class="value">${s.p25 || '—'}${unit} / ${s.p75 || '—'}${unit}</span></div>
    <div class="stat-row"><span class="label">Std Dev</span><span class="value low">${s.stdev}${unit}</span></div>
  </div>`;
}

function ratioCard(title, val, desc, color) {
  return `<div class="ratio-card">
    <h3>${title}</h3>
    <div class="value" style="color:${color}">${val}</div>
    <div class="desc">${desc}</div>
  </div>`;
}

function chartOpts(xLabel, yLabel, extra) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'nearest', intersect: false },
    plugins: {
      legend: { labels: { color: '#88a0c0', font: { size: 10 } } }
    },
    scales: Object.assign({
      x: { title: { display: true, text: xLabel, color: '#576574' }, ticks: { color: '#576574', maxTicksLimit: 15 } },
      y: Object.assign({ title: { display: true, text: yLabel, color: '#576574' }, ticks: { color: '#576574' }, grid: { color: '#1e2744' } }, extra?.y || {}),
    }, extra?.x ? { x2: extra.x } : {})
  };
}

const servoColors = ['#ff6b6b', '#ffaa00', '#ffdd00', '#00ccff', '#00ff88'];

async function clearCache() {
  await fetchJSON('/api/clear_cache');
  const sel = document.getElementById('fileSelect');
  if (sel.value) loadFile(sel.value);
}

init();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description='Axis Web Analysis Dashboard — visualize EEG CSV logs in browser')
    parser.add_argument('path', nargs='?', default='.',
                        help='Directory with CSV files or single CSV file')
    parser.add_argument('--port', '-p', type=int, default=8080,
                        help='HTTP server port (default: 8080)')
    parser.add_argument('--bind', '-b', default='0.0.0.0',
                        help='Bind address (default: 0.0.0.0)')

    args = parser.parse_args()

    global DATA_DIR, SINGLE_FILE
    if os.path.isfile(args.path):
        SINGLE_FILE = os.path.abspath(args.path)
        print(f"📄 Single file mode: {SINGLE_FILE}")
    elif os.path.isdir(args.path):
        DATA_DIR = os.path.abspath(args.path)
        files = find_csv_files(DATA_DIR)
        print(f"📂 Directory mode: {DATA_DIR} ({len(files)} CSV files)")
        for f in files[:5]:
            print(f"   {f['name']} — {f['rows']} rows, {f['size'] / 1024:.1f} KB")
        if len(files) > 5:
            print(f"   ... and {len(files) - 5} more")
    else:
        print(f"❌ Path not found: {args.path}")
        sys.exit(1)

    server = HTTPServer((args.bind, args.port), AnalysisHandler)
    print(f"\n🌐 Server started: http://{args.bind if args.bind != '0.0.0.0' else 'localhost'}:{args.port}")
    print(f"   Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == '__main__':
    main()
