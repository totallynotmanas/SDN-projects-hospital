#!/usr/bin/env python3
"""
Generate Grouped Bar Chart for SDN Dynamic QoS and Code Blue Preemption Benchmarks.
Reads qos_results.csv and outputs qos_comparison.png with accurate 100 Mbps trunk capacity.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CSV_FILE = os.path.join(REPO_ROOT, 'qos_results.csv')
OUTPUT_PNG = os.path.join(REPO_ROOT, 'qos_comparison.png')


def plot_qos_results():
    if not os.path.exists(CSV_FILE):
        print(f"Error: {CSV_FILE} not found. Please run run_experiments.py first.")
        return

    print(f"Reading data from {CSV_FILE}...")
    df = pd.read_csv(CSV_FILE)

    if 'Phase' not in df.columns or 'Traffic_Type' not in df.columns:
        print("Error: Invalid CSV format. Expected 'Traffic_Type', 'Phase', 'Bandwidth_Mbps'.")
        return

    # Check available phases
    available_phases = [p for p in ['Before', 'After', 'Code_Blue'] if p in df['Phase'].values]
    pivot = df.pivot(index='Traffic_Type', columns='Phase', values='Bandwidth_Mbps')

    # Desired order for traffic categories
    category_order = ['ICU Telemetry', 'Admin Staff', 'IoT Devices', 'Guest WiFi']
    ordered_index = [c for c in category_order if c in pivot.index] + [c for c in pivot.index if c not in category_order]
    pivot = pivot.reindex(index=ordered_index, columns=available_phases)

    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=300)
    x = list(range(len(pivot.index)))
    num_phases = len(available_phases)
    total_width = 0.72
    bar_width = total_width / num_phases

    colors = {
        'Before': '#7f8c8d',       # Baseline slate grey
        'After': '#2980b9',        # Standard QoS corporate blue
        'Code_Blue': '#c0392b'     # Emergency vibrant crimson red
    }

    labels = {
        'Before': 'Phase 1: Baseline (Unmanaged 100M Contention)',
        'After': 'Phase 2: Standard QoS Enforced (Queue 1: Med, Queue 0: Admin, Queue 2: IoT)',
        'Code_Blue': 'Phase 3: Code Blue Dynamic Preemption (Queue 3: 85M, Admin Throttled, Guest Dropped)'
    }

    rects = []
    for i, phase in enumerate(available_phases):
        offsets = [pos - (total_width / 2) + (i * bar_width) + (bar_width / 2) for pos in x]
        bars = ax.bar(offsets, pivot[phase], bar_width, label=labels.get(phase, phase),
                      color=colors.get(phase, '#2ca02c'), edgecolor='#2c3e50', linewidth=0.9)
        rects.append(bars)

    max_val = pivot.max().max() if not pivot.empty else 10
    if max_val > 60:
        # 100 Mbps Trunk Link Capacity reference line
        ax.axhline(100, color='#e74c3c', linestyle='--', linewidth=1.8, alpha=0.85, label='Trunk Link Capacity (100 Mbps)')
        ax.set_ylim(0, 115)
        ax.set_yticks(range(0, 121, 20))
    else:
        # Scale to data height so bars are prominent
        y_top = int(max(40, ((int(max_val) // 10) + 2) * 10))
        ax.set_ylim(0, y_top)
        ax.set_yticks(range(0, y_top + 1, 10))

    ax.set_title('Hospital SDN Event-Driven Dynamic QoS & Preemption Evaluation\n'
                 'Throughput Comparison Across Operational States', fontsize=14, fontweight='bold', pad=18)
    ax.set_xlabel('Department Traffic Category', fontsize=12, fontweight='bold', labelpad=12)
    ax.set_ylabel('Measured Bandwidth (Mbps)', fontsize=12, fontweight='bold', labelpad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index, fontsize=11, fontweight='bold')
    ax.legend(frameon=True, facecolor='#ffffff', edgecolor='#bdc3c7', fontsize=9, loc='upper right')

    # Add numeric labels on top of bars
    for bars in rects:
        for bar in bars:
            height = bar.get_height()
            if height is not None and not pd.isna(height):
                ax.annotate(f'{height:.2f}M',
                            xy=(bar.get_x() + bar.get_width() / 2, max(height, 1.5)),
                            xytext=(0, 4), textcoords="offset points",
                            ha='center', va='bottom', fontsize=8.5, fontweight='bold')

    ax.grid(axis='y', linestyle=':', alpha=0.7)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(OUTPUT_PNG)
    print(f"[+] High-resolution chart saved to: {OUTPUT_PNG}")


if __name__ == '__main__':
    plot_qos_results()
