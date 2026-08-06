#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CSV_FILE = os.path.join(REPO_ROOT, 'qos_results.csv')
OUTPUT_PNG = os.path.join(REPO_ROOT, 'qos_comparison.png')

# Medical = fast (green), IoT = throttled (red)
AFTER_COLORS = {'Medical (Queue 1)': '#2ca02c', 'IoT (Queue 2)': '#d62728'}


def plot_qos_results():
    if not os.path.exists(CSV_FILE):
        print(f"Error: {CSV_FILE} not found. Please run run_experiments.py first.")
        return

    print(f"Reading data from {CSV_FILE}...")
    df = pd.read_csv(CSV_FILE)

    if 'Phase' not in df.columns:
        print("Error: CSV has no 'Phase' column (old format). "
              "Please re-run run_experiments.py.")
        return

    # Pivot so each Traffic_Type has a Before and an After value.
    pivot = df.pivot(index='Traffic_Type', columns='Phase',
                     values='Bandwidth_Mbps').reindex(columns=['Before', 'After'])

    fig, ax = plt.subplots(figsize=(9, 6))
    x = list(range(len(pivot.index)))
    width = 0.35

    bars_before = ax.bar([i - width / 2 for i in x], pivot['Before'], width,
                         label='Before QoS', color='#999999')
    bars_after = ax.bar(
        [i + width / 2 for i in x], pivot['After'], width,
        label='After QoS', color=[AFTER_COLORS.get(t, '#1f77b4') for t in pivot.index])

    ax.set_title('SDN QoS Performance Analysis (Rubric Point 5)\n'
                 'Throughput Before vs After QoS', fontsize=14, fontweight='bold')
    ax.set_xlabel('Traffic Source', fontsize=12)
    ax.set_ylabel('Throughput (Mbps)', fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index)
    ax.legend()

    max_bw = max(pivot['Before'].max(), pivot['After'].max())
    ax.set_ylim(0, max_bw * 1.25 if max_bw > 0 else 10)

    # Add data labels on top of bars
    for bars in (bars_before, bars_after):
        for bar in bars:
            yval = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2,
                    yval + (max_bw * 0.02),
                    f'{yval:.2f}', ha='center', va='bottom',
                    fontsize=10, fontweight='bold')

    ax.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()

    plt.savefig(OUTPUT_PNG, dpi=300)
    print(f"Chart successfully saved to: {OUTPUT_PNG}")


if __name__ == '__main__':
    try:
        plot_qos_results()
    except ImportError:
        print("Error: Required libraries not found. Please install pandas and matplotlib:")
        print("pip install pandas matplotlib")
