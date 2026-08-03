#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib.pyplot as plt

def plot_qos_results():
    csv_file = '../qos_results.csv'
    
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found. Please run run_experiments.py first.")
        return

    print(f"Reading data from {csv_file}...")
    df = pd.read_csv(csv_file)
    
    # Setup chart
    plt.figure(figsize=(8, 6))
    colors = ['#2ca02c', '#d62728'] # Green for fast, Red for throttled
    
    bars = plt.bar(df['Traffic_Type'], df['Bandwidth_Mbps'], color=colors)
    
    # Chart styling
    plt.title('SDN QoS Performance Analysis (Rubric Point 5)', fontsize=16, fontweight='bold')
    plt.xlabel('Traffic Source', fontsize=12)
    plt.ylabel('Throughput (Mbps)', fontsize=12)
    
    # Ensure y-axis has enough headroom for labels
    max_bw = df['Bandwidth_Mbps'].max()
    plt.ylim(0, max_bw * 1.2 if max_bw > 0 else 10)

    # Add data labels on top of bars
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval + (max_bw * 0.02), 
                 f'{yval:.2f} Mbps', ha='center', va='bottom', fontsize=11, fontweight='bold')

    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    # Save chart
    output_png = '../qos_comparison.png'
    plt.savefig(output_png, dpi=300)
    print(f"Chart successfully saved to: {output_png}")

if __name__ == '__main__':
    try:
        plot_qos_results()
    except ImportError:
        print("Error: Required libraries not found. Please install pandas and matplotlib:")
        print("pip install pandas matplotlib")
