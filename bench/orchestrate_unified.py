#!/usr/bin/env python3
"""Controlled sequential trial orchestrator for Mini A-IPC unified benchmarks.

Executes randomized trial blocks for:
  1. Single-pair 1P/1C RTT payload sweep across all eligible IPC transports + adaptive.
  2. Selector decision overhead microbenchmark.
  3. Matched 80%/20% mixed workload (mini-aipc-mixed: pipe vs adaptive).
  4. Concurrency scalability matrix (1P/1C, 2P/1C, 4P/1C, 1P/2C, 4P/4C).
  5. Matched unidirectional 1P/1C baselines (pipe, fifo, uds, posix) for kernel comparison.

Every trial runs sequentially as an isolated subprocess, streams immediately to
raw/all_results.csv (preserving partial results on interruption), and cleans up
temporary IPC artifacts between trials.
"""
import argparse
import csv
import datetime
import glob
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile


FIELDNAMES = [
    "timestamp_utc", "experiment_id", "environment_id", "trial_order_index",
    "workload_type", "latency_semantics", "requested_mode", "selected_transport",
    "payload_bytes", "producers", "consumers", "trial", "warmup_count",
    "target_messages", "completed_messages", "validation_errors", "status",
    "status_reason", "elapsed_ns", "duration_s", "avg_rtt_us", "stddev_rtt_us",
    "min_rtt_us", "p50_rtt_us", "p90_rtt_us", "p95_rtt_us", "p99_rtt_us",
    "p999_rtt_us", "max_rtt_us", "throughput_msg_s", "bytes_per_sec",
    "mb_per_sec", "wire_mb_per_sec", "user_cpu_s", "sys_cpu_s", "total_cpu_s",
    "cpu_util_pct", "cpu_us_per_msg", "parent_peak_rss_kb", "child_peak_rss_kb",
    "combined_peak_rss_kb", "major_page_faults", "minor_page_faults",
    "voluntary_ctx_switches", "involuntary_ctx_switches",
]


def cleanup_temp_ipc():
    """Clean temporary Mini A-IPC FIFO/UDS/POSIX-MQ/SHM artifacts if left over."""
    patterns = [
        "/tmp/mini_aipc_*.fifo",
        "/tmp/mini_aipc_*.sock",
        "/dev/mqueue/mini_aipc_*",
        "/dev/shm/mini_aipc_*",
    ]
    for pat in patterns:
        for p in glob.glob(pat):
            try:
                os.unlink(p)
            except OSError:
                pass


def run_unified_call(bin_path, args_list, timeout_s=45):
    """Run bin/aipc_unified_bench and parse its JSON line output."""
    try:
        res = subprocess.run(
            [bin_path] + args_list,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        cleanup_temp_ipc()
        return None, f"Timed out after {timeout_s}s"

    cleanup_temp_ipc()
    out = res.stdout.strip()
    if out:
        try:
            data = json.loads(out.splitlines()[-1])
            return data, None
        except json.JSONDecodeError as e:
            return None, f"JSON parse error ({e}): {out[-200:]}"
    return None, f"No stdout (rc={res.returncode}): {res.stderr.strip()}"


def run_mixed_call(mixed_bin, policy, count, threshold, trial, exp_id, env_id):
    """Reuse existing ./mini-aipc-mixed binary and normalize into unified CSV schema."""
    cmd = [mixed_bin, "--policy", policy, "--count", str(count), "--threshold", str(threshold)]
    t0_wall = os.times()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        cleanup_temp_ipc()
        return {
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "experiment_id": exp_id, "environment_id": env_id, "trial_order_index": 0,
            "workload_type": "mixed_80_20", "latency_semantics": "round_trip_rtt",
            "requested_mode": policy, "selected_transport": policy, "payload_bytes": 64,
            "producers": 1, "consumers": 1, "trial": trial, "warmup_count": 0,
            "target_messages": count, "completed_messages": 0, "validation_errors": 1,
            "status": "FAIL", "status_reason": "mini-aipc-mixed timeout",
        }
    t1_wall = os.times()
    cleanup_temp_ipc()
    out = res.stdout
    elapsed_m = re.search(r"Elapsed:\s+(\d+)\s+ns", out)
    lat_m = re.search(r"Average latency:\s+([0-9.]+)\s+ns", out)
    tput_m = re.search(r"Throughput:\s+([0-9.]+)\s+exchanges/s", out)
    err_m = re.search(r"Validation errors:\s+(\d+)", out)
    small_m = re.search(r"Small messages:\s+(\d+)", out)
    large_m = re.search(r"Large messages:\s+(\d+)", out)

    elapsed_ns = int(elapsed_m.group(1)) if elapsed_m else 0
    errors = int(err_m.group(1)) if err_m else 1
    small_n = int(small_m.group(1)) if small_m else int(count * 0.8)
    large_n = int(large_m.group(1)) if large_m else (count - small_n)
    total_payload_bytes = small_n * 64 + large_n * 16384
    dur_s = elapsed_ns / 1e9 if elapsed_ns else 0.0
    avg_us = (float(lat_m.group(1)) / 1000.0) if lat_m else ""
    msg_s = float(tput_m.group(1)) if tput_m else 0.0
    bytes_s = (total_payload_bytes / dur_s) if dur_s > 0 else 0.0
    mb_s = bytes_s / 1e6
    cuser = max(0.0, t1_wall.children_user - t0_wall.children_user)
    csys = max(0.0, t1_wall.children_system - t0_wall.children_system)
    ctot = cuser + csys
    status = "PASS" if (res.returncode == 0 and errors == 0) else "FAIL"
    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "experiment_id": exp_id,
        "environment_id": env_id,
        "trial_order_index": 0,
        "workload_type": "mixed_80_20",
        "latency_semantics": "round_trip_rtt",
        "requested_mode": policy,
        "selected_transport": policy,
        "payload_bytes": 3315, # weighted mean payload (0.8*64 + 0.2*16384 = 3328 B)
        "producers": 1,
        "consumers": 1,
        "trial": trial,
        "warmup_count": 0,
        "target_messages": count,
        "completed_messages": count if status == "PASS" else 0,
        "validation_errors": errors,
        "status": status,
        "status_reason": "ok" if status == "PASS" else res.stderr.strip(),
        "elapsed_ns": elapsed_ns,
        "duration_s": f"{dur_s:.9f}",
        "avg_rtt_us": f"{avg_us:.6f}" if avg_us != "" else "",
        "throughput_msg_s": f"{msg_s:.4f}" if status == "PASS" else "",
        "bytes_per_sec": f"{bytes_s:.4f}" if status == "PASS" else "",
        "mb_per_sec": f"{mb_s:.6f}" if status == "PASS" else "",
        "wire_mb_per_sec": f"{2.0 * mb_s:.6f}" if status == "PASS" else "",
        "user_cpu_s": f"{cuser:.6f}",
        "sys_cpu_s": f"{csys:.6f}",
        "total_cpu_s": f"{ctot:.6f}",
        "cpu_util_pct": f"{(ctot / dur_s * 100.0):.3f}" if dur_s > 0 else "",
        "cpu_us_per_msg": f"{(ctot * 1e6 / count):.6f}" if count > 0 else "",
    }


def main():
    ap = argparse.ArgumentParser(description="Orchestrate controlled unified IPC benchmarks")
    ap.add_argument("--bin", required=True)
    ap.add_argument("--mixed-bin", required=True)
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--environment-id", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--meta-out", required=True)
    ap.add_argument("--messages", type=int, default=10000)
    ap.add_argument("--warmup", type=int, default=500)
    ap.add_argument("--trials", type=int, default=7)
    ap.add_argument("--payloads", default="64,256,1024,4096,16384,65536,262144")
    ap.add_argument("--producers", type=int, default=1)
    ap.add_argument("--consumers", type=int, default=1)
    ap.add_argument("--concurrency-matrix", default="1:1,2:1,4:1,1:2,4:4")
    ap.add_argument("--concurrency-payload", type=int, default=256)
    ap.add_argument("--concurrency-messages", type=int, default=5000)
    ap.add_argument("--concurrency-trials", type=int, default=5)
    ap.add_argument("--unidirectional-messages", type=int, default=2000)
    ap.add_argument("--unidirectional-trials", type=int, default=3)
    ap.add_argument("--threshold", type=int, default=1024)
    ap.add_argument("--cpu-producer", type=int, default=0)
    ap.add_argument("--cpu-consumer", type=int, default=1)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--skip-concurrency", action="store_true")
    ap.add_argument("--skip-unidirectional", action="store_true")
    args = ap.parse_args()

    payloads = [int(x) for x in args.payloads.split(",") if x.strip()]
    mechanisms = ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]
    rng = random.Random(args.seed)

    os.makedirs(os.path.dirname(args.out_csv) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.meta_out) or ".", exist_ok=True)

    trial_orders = {}
    # Known blocked/unsupported cache per (workload, mode, payload, P, C) to avoid
    # retrying ENOSYS/EMSGSIZE 7 times needlessly after proving it once per session?
    # Better yet: run trial 1 and still record exact status for every trial (each ENOSYS/EMSGSIZE takes <2ms!).

    with open(args.out_csv, "w", newline="", encoding="utf-8") as csv_f:
        writer = csv.DictWriter(csv_f, fieldnames=FIELDNAMES)
        writer.writeheader()
        csv_f.flush()

        def write_record(row_dict, order_idx=0):
            row_dict["timestamp_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            row_dict["experiment_id"] = args.experiment_id
            row_dict["environment_id"] = args.environment_id
            row_dict["trial_order_index"] = order_idx
            clean = {k: ("" if row_dict.get(k) is None else row_dict.get(k)) for k in FIELDNAMES}
            writer.writerow(clean)
            csv_f.flush()

        # -------------------------------------------------------------------
        # Phase 1: Single-Pair RTT Payload Sweep (Randomized order per trial)
        # -------------------------------------------------------------------
        print(f"[Phase 1] Single-pair RTT sweep: {args.trials} trials x {len(payloads)} payloads x {len(mechanisms)} modes ({args.messages} msgs, warmup {args.warmup})")
        for trial in range(1, args.trials + 1):
            combos = [(m, p) for p in payloads for m in mechanisms]
            rng.shuffle(combos)
            trial_orders[f"rtt_trial_{trial}"] = [f"{m}:{p}" for m, p in combos]
            print(f"  -> RTT Trial {trial}/{args.trials} ({len(combos)} randomized runs)...", flush=True)

            for order_idx, (m, p) in enumerate(combos, start=1):
                cmd_args = [
                    "--mode", m,
                    "--workload", "rtt",
                    "--size", str(p),
                    "--count", str(args.messages),
                    "--warmup", str(args.warmup),
                    "--producers", str(args.producers),
                    "--consumers", str(args.consumers),
                    "--trial", str(trial),
                    "--threshold", str(args.threshold),
                    "--cpu-producer", str(args.cpu_producer),
                    "--cpu-consumer", str(args.cpu_consumer),
                    "--experiment-id", args.experiment_id,
                ]
                data, err = run_unified_call(args.bin, cmd_args, timeout_s=45)
                if data is not None:
                    write_record(data, order_idx)
                    if data["status"] != "PASS" and trial == 1:
                        print(f"     [{data['status']}] {m} @ {p}B: {data['status_reason']}", flush=True)
                else:
                    write_record({
                        "workload_type": "single_pair_rtt",
                        "latency_semantics": "round_trip_rtt",
                        "requested_mode": m,
                        "selected_transport": m,
                        "payload_bytes": p,
                        "producers": args.producers,
                        "consumers": args.consumers,
                        "trial": trial,
                        "warmup_count": args.warmup,
                        "target_messages": args.messages,
                        "completed_messages": 0,
                        "validation_errors": 1,
                        "status": "FAIL",
                        "status_reason": err,
                    }, order_idx)

        # -------------------------------------------------------------------
        # Phase 2: Adaptive Selector Decision Overhead + Mixed Workload
        # -------------------------------------------------------------------
        print("[Phase 2] Evaluating adaptive selector overhead & mixed 80/20 workload...", flush=True)
        for idx, p in enumerate(payloads, start=1):
            data, err = run_unified_call(args.bin, [
                "--mode", "adaptive", "--workload", "selector_overhead",
                "--size", str(p), "--count", "1000000", "--trial", "1",
                "--threshold", str(args.threshold), "--experiment-id", args.experiment_id,
            ])
            if data:
                write_record(data, idx)

        mixed_count = args.messages - (args.messages % 5)
        if mixed_count < 5:
            mixed_count = 5
        if os.path.exists(args.mixed_bin):
            for trial in range(1, args.trials + 1):
                policies = ["pipe", "adaptive"]
                rng.shuffle(policies)
                for idx, pol in enumerate(policies, start=1):
                    mrow = run_mixed_call(
                        args.mixed_bin, pol, mixed_count, args.threshold,
                        trial, args.experiment_id, args.environment_id,
                    )
                    write_record(mrow, idx)

        # -------------------------------------------------------------------
        # Phase 3: Concurrency Scalability Sweep
        # -------------------------------------------------------------------
        if not args.skip_concurrency:
            topos = []
            for tok in args.concurrency_matrix.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                p_str, c_str = tok.split(":")
                topos.append((int(p_str), int(c_str)))

            conc_mechs = ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]
            print(f"[Phase 3] Concurrency scalability: {args.concurrency_trials} trials x {len(topos)} topologies x {len(conc_mechs)} modes @ {args.concurrency_payload}B", flush=True)
            for trial in range(1, args.concurrency_trials + 1):
                combos = [(m, pr, co) for (pr, co) in topos for m in conc_mechs]
                rng.shuffle(combos)
                trial_orders[f"conc_trial_{trial}"] = [f"{m}:{pr}P/{co}C" for m, pr, co in combos]
                print(f"  -> Concurrency Trial {trial}/{args.concurrency_trials}...", flush=True)
                for idx, (m, pr, co) in enumerate(combos, start=1):
                    data, err = run_unified_call(args.bin, [
                        "--mode", m, "--workload", "concurrency",
                        "--size", str(args.concurrency_payload),
                        "--count", str(args.concurrency_messages),
                        "--producers", str(pr), "--consumers", str(co),
                        "--trial", str(trial),
                        "--cpu-producer", str(args.cpu_producer),
                        "--cpu-consumer", str(args.cpu_consumer),
                        "--experiment-id", args.experiment_id,
                    ], timeout_s=300)
                    if data:
                        write_record(data, idx)

        # -------------------------------------------------------------------
        # Phase 4: Matched Unidirectional User-Space Baselines (for Kernel comparison)
        # -------------------------------------------------------------------
        if not args.skip_unidirectional:
            uni_mechs = ["pipe", "fifo", "posix", "uds"]
            print(f"[Phase 4] Matched unidirectional streams ({args.unidirectional_trials} trials x {len(payloads)} payloads)", flush=True)
            for trial in range(1, args.unidirectional_trials + 1):
                combos = [(m, p) for p in payloads for m in uni_mechs]
                rng.shuffle(combos)
                for idx, (m, p) in enumerate(combos, start=1):
                    data, err = run_unified_call(args.bin, [
                        "--mode", m, "--workload", "unidirectional",
                        "--size", str(p), "--count", str(args.unidirectional_messages),
                        "--producers", "1", "--consumers", "1", "--trial", str(trial),
                        "--cpu-producer", str(args.cpu_producer),
                        "--cpu-consumer", str(args.cpu_consumer),
                        "--experiment-id", args.experiment_id,
                    ], timeout_s=300)
                    if data:
                        write_record(data, idx)

    # Save initial metadata JSON
    meta = {
        "experiment_id": args.experiment_id,
        "environment_id": args.environment_id,
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host_os": platform.system(),
        "platform_detail": platform.platform(),
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "config": {
            "messages": args.messages,
            "warmup": args.warmup,
            "trials": args.trials,
            "payloads": args.payloads,
            "producers": args.producers,
            "consumers": args.consumers,
            "concurrency_matrix": args.concurrency_matrix,
            "concurrency_payload": args.concurrency_payload,
            "concurrency_messages": args.concurrency_messages,
            "concurrency_trials": args.concurrency_trials,
            "unidirectional_messages": args.unidirectional_messages,
            "unidirectional_trials": args.unidirectional_trials,
            "threshold": args.threshold,
            "cpu_producer": args.cpu_producer,
            "cpu_consumer": args.cpu_consumer,
            "seed": args.seed,
        },
        "randomized_trial_orders": trial_orders,
    }
    with open(args.meta_out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Orchestration complete -> {args.out_csv}")


if __name__ == "__main__":
    main()

