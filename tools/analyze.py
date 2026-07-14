#!/usr/bin/env python3
"""
Axis EEG Data Analyzer
Analyze CSV logs from the Axis data logger for ML training.

Usage:
    python tools/analyze.py /sdcard/eeg_log.csv
    python tools/analyze.py /sdcard/eeg_log.csv --plot --stats
"""

import csv
import sys
import argparse
import statistics
from collections import Counter

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def load_csv(path):
    rows = []
    with open(path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def compute_stats(rows):
    fields = ['attention', 'meditation', 'blink_strength', 'raw_wave',
              'delta', 'theta', 'low_alpha', 'high_alpha',
              'low_beta', 'high_beta', 'low_gamma', 'high_gamma']
    stats = {}
    for field in fields:
        vals = [float(r[field]) for r in rows if r.get(field)]
        if vals:
            stats[field] = {
                'min': min(vals),
                'max': max(vals),
                'mean': statistics.mean(vals),
                'median': statistics.median(vals),
                'stdev': statistics.stdev(vals) if len(vals) > 1 else 0,
            }
    return stats


def print_stats(stats):
    print(f"{'Field':<20} {'Min':>8} {'Max':>8} {'Mean':>8} {'Median':>8} {'StDev':>8}")
    print('-' * 68)
    for field, s in stats.items():
        print(f"{field:<20} {s['min']:>8.1f} {s['max']:>8.1f} "
              f"{s['mean']:>8.1f} {s['median']:>8.1f} {s['stdev']:>8.1f}")


def plot_data(rows):
    if not HAS_MPL:
        print("matplotlib not installed. Install with: pip install matplotlib")
        return

    timestamps = [int(r['timestamp_ms']) for r in rows]
    t0 = timestamps[0] if timestamps else 0
    time_sec = [(t - t0) / 1000.0 for t in timestamps]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    ax = axes[0]
    ax.plot(time_sec, [float(r['attention']) for r in rows], label='Attention', color='#00ff00')
    ax.plot(time_sec, [float(r['meditation']) for r in rows], label='Meditation', color='#00ccff')
    ax.plot(time_sec, [float(r['blink_strength']) for r in rows], label='Blink', color='#ff00ff')
    ax.set_ylabel('EEG Value')
    ax.set_title('EEG Signals over Time')
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    bands = ['delta', 'theta', 'low_alpha', 'high_alpha',
             'low_beta', 'high_beta', 'low_gamma', 'high_gamma']
    colors = ['#ff0000', '#ff8800', '#ffff00', '#00ff00',
              '#00ccff', '#0066ff', '#8800ff', '#ff00ff']
    for band, color in zip(bands, colors):
        vals = [float(r[band]) for r in rows]
        ax.plot(time_sec, vals, label=band, color=color, alpha=0.7)
    ax.set_ylabel('Power')
    ax.set_title('EEG Frequency Bands')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')

    ax = axes[2]
    for i in range(5):
        sv = [float(r[f'servo{i}']) for r in rows]
        ax.plot(time_sec, sv, label=f'Servo {i}', linewidth=2)
    ax.set_xlabel('Time (seconds)')
    ax.set_ylabel('Angle (°)')
    ax.set_title('Servo Positions')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


def extract_features(rows):
    features = []
    for i, r in enumerate(rows):
        f = {
            'att': float(r['attention']),
            'med': float(r['meditation']),
            'blink': float(r['blink_strength']),
            'raw': float(r['raw_wave']),
            'delta': float(r['delta']),
            'theta': float(r['theta']),
            'low_alpha': float(r['low_alpha']),
            'high_alpha': float(r['high_alpha']),
            'low_beta': float(r['low_beta']),
            'high_beta': float(r['high_beta']),
            'low_gamma': float(r['low_gamma']),
            'high_gamma': float(r['high_gamma']),
            'alpha_beta_ratio': 0,
            'theta_gamma_ratio': 0,
            'attention_relax_ratio': 0,
        }

        beta = f['low_beta'] + f['high_beta']
        f['alpha_beta_ratio'] = (
            (f['low_alpha'] + f['high_alpha']) / beta
            if beta > 0 else 0
        )
        gamma = f['low_gamma'] + f['high_gamma']
        f['theta_gamma_ratio'] = (
            f['theta'] / gamma if gamma > 0 else 0
        )
        f['attention_relax_ratio'] = (
            f['att'] / (f['med'] + 1)
        )

        target = [float(r[f'servo{j}']) for j in range(5)]
        f['target_servos'] = target
        features.append(f)

    return features


def main():
    parser = argparse.ArgumentParser(description='Axis EEG Data Analyzer')
    parser.add_argument('csv_file', help='Path to CSV log file')
    parser.add_argument('--stats', action='store_true', help='Print statistics')
    parser.add_argument('--plot', action='store_true', help='Plot graphs')
    parser.add_argument('--features', action='store_true', help='Extract ML features')
    parser.add_argument('--output', '-o', help='Save features to CSV')

    args = parser.parse_args()

    rows = load_csv(args.csv_file)
    print(f"Loaded {len(rows)} records from {args.csv_file}")

    if args.stats:
        s = compute_stats(rows)
        print_stats(s)

    if args.plot:
        plot_data(rows)

    if args.features:
        features = extract_features(rows)
        if args.output:
            with open(args.output, 'w') as f:
                keys = list(features[0].keys())
                keys.remove('target_servos')
                f.write(','.join(keys + [f'servo{j}' for j in range(5)]) + '\n')
                for feat in features:
                    vals = [str(feat[k]) for k in keys] + \
                           [str(s) for s in feat['target_servos']]
                    f.write(','.join(vals) + '\n')
            print(f"Features saved to {args.output}")
        else:
            print(f"\nExtracted {len(features)} samples.")
            print("Use --output to save as CSV for ML training.")

    if not any([args.stats, args.plot, args.features]):
        parser.print_help()


if __name__ == '__main__':
    main()
