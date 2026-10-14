#!/usr/bin/env python3
"""
Generate Grouped Bar Chart for SDN QoS and Code Blue Preemption Benchmarks.
Reads qos_results.csv and outputs qos_comparison.png.
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
    pivot = df.pivot(index='Traffic_Type', columns='Phase', values='Bandwidth_Mbps').reindex(columns=available_phases)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    x = list(range(len(pivot.index)))
    num_phases = len(available_phases)
    total_width = 0.7
    bar_width = total_width / num_phases

    colors = {
        'Before': '#7f7f7f',       # Baseline grey
        'After': '#1f77b4',        # Standard QoS blue
        'Code_Blue': '#d62728'     # Emergency red
    }

    labels = {
        'Before': 'Baseline (No QoS)',
        'After': 'Standard QoS Enforced',
        'Code_Blue': 'Code Blue Preemption Active'
    }

    rects = []
    for i, phase in enumerate(available_phases):
        offsets = [pos - (total_width / 2) + (i * bar_width) + (bar_width / 2) for pos in x]
        bars = ax.bar(offsets, pivot[phase], bar_width, label=labels.get(phase, phase),
                      color=colors.get(phase, '#2ca02c'), edgecolor='black', linewidth=0.8)
        rects.append(bars)

    ax.set_title('Hospital SDN Dynamic QoS & Preemption Evaluation\n'
                 'Throughput Comparison Across Operational States', fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel('Department Traffic Category', fontsize=12, fontweight='bold', labelpad=10)
    ax.set_ylabel('Bandwidth (Mbps)', fontsize=12, fontweight='bold', labelpad=10)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index, fontsize=11, fontweight='bold')
    ax.legend(frameon=True, facecolor='#f8f9fa', edgecolor='#cccccc', fontsize=10)

    max_val = pivot.max().max() if not pivot.empty else 10
    ax.set_ylim(0, max_val * 1.25)

    # Add numeric labels on top of bars
    for bars in rects:
        for bar in bars:
            height = bar.get_height()
            if height is not None and not pd.isna(height):
                ax.annotate(f'{height:.2f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 4), textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.grid(axis='y', linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(OUTPUT_PNG)
    print(f"[+] High-resolution chart saved to: {OUTPUT_PNG}")


if __name__ == '__main__':
    plot_qos_results()
