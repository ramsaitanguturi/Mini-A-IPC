import os
import pandas as pd
import numpy as np

# 1. WSL2 / Ubuntu dataset (comparative_benchmark.csv)
if os.path.exists('results/comparative_benchmark.csv'):
    df_wsl = pd.read_csv('results/comparative_benchmark.csv')
    print('=== WSL2 Dataset (comparative_benchmark.csv) ===')
    for p in sorted(df_wsl['payload_bytes'].unique()):
        sub = df_wsl[df_wsl['payload_bytes'] == p]
        best_idx = sub['avg_rtt_us'].idxmin()
        best_row = sub.loc[best_idx]
        best_mech = best_row['mechanism']
        best_lat = best_row['avg_rtt_us']
        print(f"Payload {p:6d}B: Best={best_mech:6s} ({best_lat:8.2f} us)")
        for _, row in sub.iterrows():
            print(f"   {row['mechanism']:6s}: {row['avg_rtt_us']:8.2f} us")

# 2. Fedora dataset (results/unified/processed/aggregated_results.csv)
if os.path.exists('results/unified/processed/aggregated_results.csv'):
    df_fed = pd.read_csv('results/unified/processed/aggregated_results.csv')
    print('\n=== Fedora Dataset (aggregated_results.csv) ===')
    for p in sorted(df_fed['payload_bytes'].unique()):
        sub = df_fed[(df_fed['payload_bytes'] == p) & (~df_fed['mechanism'].isin(['adaptive', 'kernel']))]
        if not sub.empty:
            best_idx = sub['mean_avg_rtt_us'].idxmin()
            best_row = sub.loc[best_idx]
            best_mech = best_row['mechanism']
            best_lat = best_row['mean_avg_rtt_us']
            print(f"Payload {p:6d}B: Best={best_mech:6s} ({best_lat:8.2f} us)")
            for _, row in sub.iterrows():
                print(f"   {row['mechanism']:6s}: {row['mean_avg_rtt_us']:8.2f} us")

