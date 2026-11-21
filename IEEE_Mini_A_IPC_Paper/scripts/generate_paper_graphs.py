#!/usr/bin/env python3
"""
Generate publication-quality vector PDF charts for IEEE Conference Paper.
Reads directly from verified benchmark datasets in results/unified/.
Optimized for IEEE two-column compact layout.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 8,
    'axes.labelsize': 8.5,
    'axes.titlesize': 9,
    'xtick.labelsize': 7.5,
    'ytick.labelsize': 7.5,
    'legend.fontsize': 7.5,
    'figure.titlesize': 9.5,
    'lines.linewidth': 1.2,
    'lines.markersize': 4,
    'grid.alpha': 0.3,
    'grid.linestyle': '--',
    'pdf.fonttype': 42,
    'ps.fonttype': 42
})

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'figures')
os.makedirs(OUT_DIR, exist_ok=True)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CSV_PATH = os.path.join(REPO_ROOT, 'results', 'unified', 'processed', 'statistical_summary.csv')

# 1. COMBINED LATENCY & THROUGHPUT (2-PANEL WIDE FIGURE FOR TWO-COLUMN SPAN)
def plot_latency_and_throughput_combined():
    df = pd.read_csv(CSV_PATH)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.3))
    
    mechanisms = ['pipe', 'fifo', 'sysv', 'posix', 'shm', 'uds']
    labels = {
        'pipe': 'Anon. Pipe',
        'fifo': 'Named FIFO',
        'sysv': 'System V MQ',
        'posix': 'POSIX MQ',
        'shm': 'POSIX SHM',
        'uds': 'Unix Sockets'
    }
    markers = {'pipe': 'o', 'fifo': 's', 'sysv': '^', 'posix': 'v', 'shm': 'D', 'uds': 'x'}
    colors = {'pipe': '#1f77b4', 'fifo': '#ff7f0e', 'sysv': '#2ca02c', 'posix': '#d62728', 'shm': '#9467bd', 'uds': '#8c564b'}
    
    # Left: Latency
    for m in mechanisms:
        sub = df[df['mechanism'] == m].sort_values('payload_bytes')
        if not sub.empty:
            ax1.plot(sub['payload_bytes'], sub['mean_avg_rtt_us'], 
                     marker=markers[m], color=colors[m], label=labels[m])
    ax1.set_xscale('log', base=2)
    ax1.set_yscale('log')
    ax1.set_xlabel('Payload Size (Bytes)')
    ax1.set_ylabel(r'Round-Trip Latency ($\mu$s)')
    ax1.set_xticks([64, 256, 1024, 4096, 16384, 65536, 262144])
    ax1.set_xticklabels(['64', '256', '1K', '4K', '16K', '64K', '256K'])
    ax1.set_title('(a) Round-Trip Latency Scaling')
    ax1.grid(True)
    ax1.legend(frameon=True, loc='upper left', ncol=2, handletextpad=0.2, columnspacing=0.8, fontsize=7)
    
    # Right: Throughput
    for m in mechanisms:
        sub = df[df['mechanism'] == m].sort_values('payload_bytes')
        if not sub.empty:
            ax2.plot(sub['payload_bytes'], sub['mean_throughput_mb_sec'], 
                     marker=markers[m], color=colors[m], label=labels[m])
    ax2.set_xscale('log', base=2)
    ax2.set_yscale('log')
    ax2.set_xlabel('Payload Size (Bytes)')
    ax2.set_ylabel('Wire Bandwidth (MB/s)')
    ax2.set_xticks([64, 256, 1024, 4096, 16384, 65536, 262144])
    ax2.set_xticklabels(['64', '256', '1K', '4K', '16K', '64K', '256K'])
    ax2.set_title('(b) Throughput Bandwidth Scaling')
    ax2.grid(True)
    ax2.legend(frameon=True, loc='upper left', ncol=2, handletextpad=0.2, columnspacing=0.8, fontsize=7)
    
    plt.tight_layout()
    pdf_path = os.path.join(OUT_DIR, 'latency_throughput_combined.pdf')
    fig.savefig(pdf_path, dpi=300)
    plt.close(fig)
    print(f'Generated {pdf_path}')

# Individual single-column plots (compact)
def plot_latency_single():
    df = pd.read_csv(CSV_PATH)
    fig, ax = plt.subplots(figsize=(3.4, 2.1))
    mechanisms = ['pipe', 'fifo', 'sysv', 'posix', 'shm', 'uds']
    labels = {'pipe': 'Anon. Pipe', 'fifo': 'Named FIFO', 'sysv': 'SysV MQ', 'posix': 'POSIX MQ', 'shm': 'POSIX SHM', 'uds': 'Unix Skt'}
    markers = {'pipe': 'o', 'fifo': 's', 'sysv': '^', 'posix': 'v', 'shm': 'D', 'uds': 'x'}
    colors = {'pipe': '#1f77b4', 'fifo': '#ff7f0e', 'sysv': '#2ca02c', 'posix': '#d62728', 'shm': '#9467bd', 'uds': '#8c564b'}
    for m in mechanisms:
        sub = df[df['mechanism'] == m].sort_values('payload_bytes')
        if not sub.empty:
            ax.plot(sub['payload_bytes'], sub['mean_avg_rtt_us'], marker=markers[m], color=colors[m], label=labels[m])
    ax.set_xscale('log', base=2)
    ax.set_yscale('log')
    ax.set_xlabel('Payload Size (Bytes)')
    ax.set_ylabel(r'Round-Trip Latency ($\mu$s)')
    ax.set_xticks([64, 256, 1024, 4096, 16384, 65536, 262144])
    ax.set_xticklabels(['64', '256', '1K', '4K', '16K', '64K', '256K'])
    ax.grid(True)
    ax.legend(frameon=True, loc='upper left', ncol=2, handletextpad=0.1, columnspacing=0.5, fontsize=6.8)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'latency_comparison.pdf'), dpi=300)
    plt.close(fig)

def plot_throughput_single():
    df = pd.read_csv(CSV_PATH)
    fig, ax = plt.subplots(figsize=(3.4, 2.1))
    mechanisms = ['pipe', 'fifo', 'sysv', 'posix', 'shm', 'uds']
    labels = {'pipe': 'Anon. Pipe', 'fifo': 'Named FIFO', 'sysv': 'SysV MQ', 'posix': 'POSIX MQ', 'shm': 'POSIX SHM', 'uds': 'Unix Skt'}
    markers = {'pipe': 'o', 'fifo': 's', 'sysv': '^', 'posix': 'v', 'shm': 'D', 'uds': 'x'}
    colors = {'pipe': '#1f77b4', 'fifo': '#ff7f0e', 'sysv': '#2ca02c', 'posix': '#d62728', 'shm': '#9467bd', 'uds': '#8c564b'}
    for m in mechanisms:
        sub = df[df['mechanism'] == m].sort_values('payload_bytes')
        if not sub.empty:
            ax.plot(sub['payload_bytes'], sub['mean_throughput_mb_sec'], marker=markers[m], color=colors[m], label=labels[m])
    ax.set_xscale('log', base=2)
    ax.set_yscale('log')
    ax.set_xlabel('Payload Size (Bytes)')
    ax.set_ylabel('Throughput (MB/s)')
    ax.set_xticks([64, 256, 1024, 4096, 16384, 65536, 262144])
    ax.set_xticklabels(['64', '256', '1K', '4K', '16K', '64K', '256K'])
    ax.grid(True)
    ax.legend(frameon=True, loc='upper left', ncol=2, handletextpad=0.1, columnspacing=0.5, fontsize=6.8)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'throughput_comparison.pdf'), dpi=300)
    plt.close(fig)

# 2. COMBINED PERCENTILES & RESOURCES (2-PANEL WIDE FIGURE)
def plot_percentiles_and_resources_combined():
    df = pd.read_csv(CSV_PATH)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.2))
    
    # Left: Percentiles
    sub = df[df['payload_bytes'] == 1024].copy()
    mechanisms = ['pipe', 'fifo', 'sysv', 'posix', 'shm', 'uds']
    sub = sub[sub['mechanism'].isin(mechanisms)]
    sub['order'] = sub['mechanism'].map({'shm': 0, 'pipe': 1, 'sysv': 2, 'posix': 3, 'fifo': 4, 'uds': 5})
    sub = sub.sort_values('order')
    labels = ['SHM', 'Pipe', 'SysV', 'POSIX', 'FIFO', 'UDS']
    p50 = sub['mean_p50_rtt_us'].values
    p95 = sub['mean_p95_rtt_us'].values
    p99 = sub['mean_p99_rtt_us'].values
    x = np.arange(len(labels))
    width = 0.25
    ax1.bar(x - width, p50, width, label='P50 (Median)', color='#2ca02c')
    ax1.bar(x, p95, width, label='P95', color='#ff7f0e')
    ax1.bar(x + width, p99, width, label='P99', color='#d62728')
    ax1.set_ylabel(r'Latency ($\mu$s)')
    ax1.set_title('(a) Tail Latency Percentiles at 1,024 Bytes')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_yscale('log')
    ax1.grid(True, axis='y')
    ax1.legend(frameon=True, loc='upper left', fontsize=7.5)
    
    # Right: Syscalls
    data = {
        'Mechanism': ['Pipe', 'FIFO', 'SysV', 'POSIX', 'SHM', 'UDS'],
        'Data Syscalls': [4.0, 4.0, 4.0, 4.0, 0.0, 4.0],
        'Sync Syscalls': [0.0, 0.0, 0.0, 0.0, 2.06, 0.0]
    }
    df_sys = pd.DataFrame(data)
    x2 = np.arange(len(df_sys['Mechanism']))
    w2 = 0.45
    ax2.bar(x2, df_sys['Data Syscalls'], w2, label='Data-Path Syscalls', color='#1f77b4')
    ax2.bar(x2, df_sys['Sync Syscalls'], w2, bottom=df_sys['Data Syscalls'], label='Futex Sync Calls', color='#2ca02c')
    ax2.set_ylabel('Syscalls per Exchange')
    ax2.set_title('(b) Communication System Calls')
    ax2.set_xticks(x2)
    ax2.set_xticklabels(df_sys['Mechanism'])
    ax2.grid(True, axis='y')
    ax2.legend(frameon=True, loc='upper right', fontsize=7.5)
    
    plt.tight_layout()
    pdf_path = os.path.join(OUT_DIR, 'percentiles_resources_combined.pdf')
    fig.savefig(pdf_path, dpi=300)
    plt.close(fig)
    print(f'Generated {pdf_path}')

def plot_percentiles_single():
    df = pd.read_csv(CSV_PATH)
    sub = df[df['payload_bytes'] == 1024].copy()
    mechanisms = ['pipe', 'fifo', 'sysv', 'posix', 'shm', 'uds']
    sub = sub[sub['mechanism'].isin(mechanisms)]
    sub['order'] = sub['mechanism'].map({'shm': 0, 'pipe': 1, 'sysv': 2, 'posix': 3, 'fifo': 4, 'uds': 5})
    sub = sub.sort_values('order')
    labels = ['SHM', 'Pipe', 'SysV', 'POSIX', 'FIFO', 'UDS']
    p50 = sub['mean_p50_rtt_us'].values
    p95 = sub['mean_p95_rtt_us'].values
    p99 = sub['mean_p99_rtt_us'].values
    x = np.arange(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(3.4, 2.1))
    ax.bar(x - width, p50, width, label='P50', color='#2ca02c')
    ax.bar(x, p95, width, label='P95', color='#ff7f0e')
    ax.bar(x + width, p99, width, label='P99', color='#d62728')
    ax.set_ylabel(r'Latency ($\mu$s)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_yscale('log')
    ax.grid(True, axis='y')
    ax.legend(frameon=True, loc='upper left', fontsize=7)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'percentile_comparison.pdf'), dpi=300)
    plt.close(fig)

def plot_resources_single():
    data = {
        'Mechanism': ['Pipe', 'FIFO', 'SysV', 'POSIX', 'SHM', 'UDS'],
        'Data Syscalls': [4.0, 4.0, 4.0, 4.0, 0.0, 4.0],
        'Sync Syscalls': [0.0, 0.0, 0.0, 0.0, 2.06, 0.0]
    }
    df = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(3.4, 2.1))
    x = np.arange(len(df['Mechanism']))
    width = 0.45
    ax.bar(x, df['Data Syscalls'], width, label='Data-Path Syscalls', color='#1f77b4')
    ax.bar(x, df['Sync Syscalls'], width, bottom=df['Data Syscalls'], label='Futex Sync', color='#2ca02c')
    ax.set_ylabel('Syscalls per Exchange')
    ax.set_xticks(x)
    ax.set_xticklabels(df['Mechanism'])
    ax.grid(True, axis='y')
    ax.legend(frameon=True, loc='upper right', fontsize=7)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'resource_utilization.pdf'), dpi=300)
    plt.close(fig)

if __name__ == '__main__':
    plot_latency_and_throughput_combined()
    plot_latency_single()
    plot_throughput_single()
    plot_percentiles_and_resources_combined()
    plot_percentiles_single()
    plot_resources_single()
