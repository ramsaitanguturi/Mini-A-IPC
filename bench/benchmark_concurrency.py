#!/usr/bin/env python3
"""
Mini A-IPC Concurrency Scalability Benchmark Runner

Evaluates throughput and scaling behavior across concurrency topologies:
  - 1 Producer  / 1 Consumer (1P/1C) - Supported by all 8 components
  - 2 Producers / 1 Consumer (2P/1C)
  - 4 Producers / 1 Consumer (4P/1C)
  - 1 Producer  / 2 Consumers (1P/2C)
  - 4 Producers / 4 Consumers (4P/4C)

Architectural Classification:
  - Multi-process Shared Queues (System V MQ, POSIX MQ, Kernel /dev/aipc):
    Fully support M:N concurrent producers and consumers.
  - SPSC Point-to-Point Transports (Anonymous Pipes, Named Pipes/FIFO, UDS socketpair, Bounded SHM):
    Classified formally as UNSUPPORTED_BY_DESIGN for M:N topologies (distinguishing
    architectural model constraints from runtime execution failures).
"""

import argparse
import csv
import os
import subprocess
import sys
import time


CONCURRENCY_CONFIGS = [
    (1, 1),
    (2, 1),
    (4, 1),
    (1, 2),
    (4, 4),
]

SPSC_MECHANISMS = {"pipe", "fifo", "shm", "uds", "adaptive"}
MPMC_MECHANISMS = {"sysv", "posix", "kernel"}


def run_concurrency_benchmark(producers, consumers, payload_size, messages_per_p, mechanism, device_path="/dev/aipc"):
    total_messages = producers * messages_per_p

    # For SPSC mechanisms, concurrency > 1:1 is not supported by architectural design
    if (producers > 1 or consumers > 1) and mechanism in SPSC_MECHANISMS:
        return {
            "mechanism": mechanism,
            "producers": producers,
            "consumers": consumers,
            "payload_bytes": payload_size,
            "messages_per_producer": messages_per_p,
            "total_messages": total_messages,
            "elapsed_ms": 0.0,
            "throughput_msg_sec": 0.0,
            "throughput_mb_sec": 0.0,
            "status": "UNSUPPORTED_BY_DESIGN",
            "notes": "SPSC point-to-point transport does not support multi-producer/consumer concurrency without custom framing/multiplexing"
        }

    # 1:1 baseline using standard mini-aipc or kernel runner
    if producers == 1 and consumers == 1:
        if mechanism == "kernel":
            if not os.path.exists(device_path):
                return {
                    "mechanism": mechanism,
                    "producers": 1,
                    "consumers": 1,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": 0.0,
                    "throughput_msg_sec": 0.0,
                    "throughput_mb_sec": 0.0,
                    "status": "BLOCKED",
                    "notes": f"Kernel device {device_path} not found"
                }
            cmd = [sys.executable, "bench/benchmark_kernel_runner.py", "--device", device_path,
                   "--size", str(payload_size), "--count", str(messages_per_p), "--csv-extended"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                parts = res.stdout.strip().split(",")
                # tput_msg is index 14, tput_mb is index 15, elapsed_ns is index 16
                tput_msg = float(parts[14])
                tput_mb = float(parts[15])
                elapsed_ms = float(parts[16]) / 1e6
                return {
                    "mechanism": mechanism,
                    "producers": 1,
                    "consumers": 1,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": elapsed_ms,
                    "throughput_msg_sec": tput_msg,
                    "throughput_mb_sec": tput_mb,
                    "status": "PASS",
                    "notes": "Standard 1P:1C baseline"
                }
            else:
                return {
                    "mechanism": mechanism,
                    "producers": 1,
                    "consumers": 1,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": 0.0,
                    "throughput_msg_sec": 0.0,
                    "throughput_mb_sec": 0.0,
                    "status": "BLOCKED",
                    "notes": res.stderr.strip() or "Kernel execution failed"
                }
        else:
            # Userspace 1P:1C via mini-aipc
            # Check size limits
            if mechanism == "shm" and payload_size > 1024:
                return {
                    "mechanism": mechanism,
                    "producers": 1,
                    "consumers": 1,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": 0.0,
                    "throughput_msg_sec": 0.0,
                    "throughput_mb_sec": 0.0,
                    "status": "EXCEEDS_CAPACITY",
                    "notes": "POSIX SHM bounded mailbox capacity is 1024 bytes"
                }
            cmd = ["./mini-aipc", "--mode", mechanism, "--size", str(payload_size),
                   "--count", str(messages_per_p), "--csv-extended"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                parts = res.stdout.strip().split(",")
                tput_msg = float(parts[14])
                tput_mb = float(parts[15])
                elapsed_ms = float(parts[16]) / 1e6
                return {
                    "mechanism": mechanism,
                    "producers": 1,
                    "consumers": 1,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": elapsed_ms,
                    "throughput_msg_sec": tput_msg,
                    "throughput_mb_sec": tput_mb,
                    "status": "PASS",
                    "notes": "Standard 1P:1C baseline"
                }
            else:
                return {
                    "mechanism": mechanism,
                    "producers": 1,
                    "consumers": 1,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": 0.0,
                    "throughput_msg_sec": 0.0,
                    "throughput_mb_sec": 0.0,
                    "status": "FAIL",
                    "notes": res.stderr.strip() or "Execution failed"
                }

    # For MPMC mechanisms (sysv, posix, kernel), execute real multi-process concurrency
    conc_bin = "./mini-aipc-concurrency"
    if not os.path.exists(conc_bin):
        # Auto-compile if not present
        subprocess.run(["gcc", "-O2", "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-D_GNU_SOURCE",
                        "src/concurrency_benchmark.c", "-o", conc_bin, "-pthread", "-lrt", "-lm"],
                       capture_output=True)

    if os.path.exists(conc_bin):
        cmd = [
            conc_bin,
            "--mode", mechanism,
            "--producers", str(producers),
            "--consumers", str(consumers),
            "--size", str(payload_size),
            "--count", str(messages_per_p),
            "--device", device_path,
            "--csv"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                parts = res.stdout.strip().split(",")
                if len(parts) >= 11:
                    return {
                        "mechanism": mechanism,
                        "producers": producers,
                        "consumers": consumers,
                        "payload_bytes": payload_size,
                        "messages_per_producer": messages_per_p,
                        "total_messages": int(parts[5]),
                        "elapsed_ms": float(parts[6]),
                        "throughput_msg_sec": float(parts[7]),
                        "throughput_mb_sec": float(parts[8]),
                        "status": parts[9],
                        "notes": parts[10]
                    }
            elif res.returncode == 77:
                return {
                    "mechanism": mechanism,
                    "producers": producers,
                    "consumers": consumers,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": 0.0,
                    "throughput_msg_sec": 0.0,
                    "throughput_mb_sec": 0.0,
                    "status": "BLOCKED",
                    "notes": f"Kernel device {device_path} not found or inaccessible"
                }
            else:
                return {
                    "mechanism": mechanism,
                    "producers": producers,
                    "consumers": consumers,
                    "payload_bytes": payload_size,
                    "messages_per_producer": messages_per_p,
                    "total_messages": total_messages,
                    "elapsed_ms": 0.0,
                    "throughput_msg_sec": 0.0,
                    "throughput_mb_sec": 0.0,
                    "status": "FAILED",
                    "notes": res.stderr.strip() or f"Process exited with code {res.returncode}"
                }
        except subprocess.TimeoutExpired:
            return {
                "mechanism": mechanism,
                "producers": producers,
                "consumers": consumers,
                "payload_bytes": payload_size,
                "messages_per_producer": messages_per_p,
                "total_messages": total_messages,
                "elapsed_ms": 0.0,
                "throughput_msg_sec": 0.0,
                "throughput_mb_sec": 0.0,
                "status": "FAILED",
                "notes": "Concurrency benchmark timed out after 30 seconds"
            }

    # Fallback if binary is not yet compiled
    return {
        "mechanism": mechanism,
        "producers": producers,
        "consumers": consumers,
        "payload_bytes": payload_size,
        "messages_per_producer": messages_per_p,
        "total_messages": total_messages,
        "elapsed_ms": 0.0,
        "throughput_msg_sec": 0.0,
        "throughput_mb_sec": 0.0,
        "status": "FAILED",
        "notes": "mini-aipc-concurrency executable not found; build project first"
    }


def main():
    parser = argparse.ArgumentParser(description="Mini A-IPC Concurrency Scalability Benchmark")
    parser.add_argument("--payload", type=int, default=64, help="Payload size in bytes (default: 64)")
    parser.add_argument("--messages", type=int, default=1000, help="Messages per producer (default: 1000)")
    parser.add_argument("--output", default="results/unified/raw/concurrency_results.csv", help="Output CSV path")
    parser.add_argument("--device", default="/dev/aipc", help="Kernel device path")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    all_mechs = ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive", "kernel"]

    fieldnames = [
        "mechanism", "producers", "consumers", "payload_bytes",
        "messages_per_producer", "total_messages", "elapsed_ms",
        "throughput_msg_sec", "throughput_mb_sec", "status", "notes"
    ]

    results = []
    for p, c in CONCURRENCY_CONFIGS:
        for m in all_mechs:
            res = run_concurrency_benchmark(p, c, args.payload, args.messages, m, args.device)
            results.append(res)
            extra = f" ({res['notes']})" if res["status"] in ("FAILED", "BLOCKED") else ""
            print(f"[{res['status']:<21}] Mech: {m:<14} | Topology: {p}P:{c}C | Tput: {res['throughput_msg_sec']:>10.2f} msg/s{extra}")

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote concurrency scalability results to {args.output}")


if __name__ == "__main__":
    main()

