#!/usr/bin/env python3
import csv
import statistics

rows = list(csv.DictReader(open("results/comparative_benchmark.csv")))
mechs = ["pipe", "fifo", "sysv", "posix", "shm", "uds"]
sizes = [64, 128, 256, 512, 1024]

header = f"{'Mechanism':<8} | {'Size':<5} | {'Avg (us)':<8} | {'P50 (us)':<8} | {'P99 (us)':<8} | {'P99.9':<8} | {'Min (us)':<8} | {'Max (us)':<9} | {'Throughput (msg/s)':<18}"
print(header)
print("-" * len(header))

for s in sizes:
    for m in mechs:
        sub = [r for r in rows if r["mechanism"] == m and int(r["payload_bytes"]) == s]
        if not sub:
            continue
        avg_rtt = statistics.mean(float(r["avg_rtt_us"]) for r in sub)
        p50 = statistics.median(float(r["p50_rtt_us"]) for r in sub)
        p99 = statistics.median(float(r["p99_rtt_us"]) for r in sub)
        p999 = statistics.median(float(r["p999_rtt_us"]) for r in sub)
        min_rtt = min(float(r["min_rtt_us"]) for r in sub)
        max_rtt = max(float(r["max_rtt_us"]) for r in sub)
        tput = statistics.mean(float(r["throughput_msg_sec"]) for r in sub)
        print(f"{m:<8} | {s:<5} | {avg_rtt:<8.2f} | {p50:<8.2f} | {p99:<8.2f} | {p999:<8.2f} | {min_rtt:<8.2f} | {max_rtt:<9.2f} | {tput:<18.2f}")
    print("-" * len(header))

