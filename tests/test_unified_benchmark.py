#!/usr/bin/env python3
"""Automated test suite for the Mini A-IPC unified benchmarking pipeline."""
import csv
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "bench"))

import analyze_results  # noqa: E402


def _bash_bin():
    for cand in (r"C:\msys64\usr\bin\bash.exe", "/usr/bin/bash", "/bin/bash"):
        if os.path.exists(cand):
            return cand
    found = shutil.which("bash")
    assert found, "bash binary not found"
    return found


def _unified_bin():
    for cand in (
        os.path.join(ROOT, "bin", "aipc_unified_bench.exe"),
        os.path.join(ROOT, "bin", "aipc_unified_bench"),
    ):
        if os.path.exists(cand):
            return cand
    pytest.skip("bin/aipc_unified_bench not built yet")


def test_shell_scripts_syntax():
    bash = _bash_bin()
    for rel in ("bench/run_unified_benchmark.sh", "bench/run_kernel_suite.sh"):
        path = os.path.join(ROOT, rel)
        assert os.path.exists(path)
        res = subprocess.run([bash, "-n", path], capture_output=True, text=True)
        assert res.returncode == 0, f"{rel}: {res.stderr}"


def test_runner_cli_validation():
    bash = _bash_bin()
    runner = "bench/run_unified_benchmark.sh"
    res_help = subprocess.run([bash, runner, "--help"], cwd=ROOT, capture_output=True, text=True)
    assert res_help.returncode == 0
    assert "--trials" in res_help.stdout

    bad_invocations = [
        ["--messages", "0"],
        ["--messages", "-10"],
        ["--warmup", "-1"],
        ["--trials", "0"],
        ["--payloads", "64,abc"],
        ["--concurrency-matrix", "bad"],
        ["--unknown-flag"],
    ]
    for bad in bad_invocations:
        r = subprocess.run([bash, runner] + bad, cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 2, f"Expected exit 2 for {bad}, got {r.returncode}: {r.stdout} {r.stderr}"


def test_c_bench_cli_and_workloads():
    ub = _unified_bin()
    env = os.environ.copy()
    if os.name == "nt" and r"C:\msys64\usr\bin" not in env.get("PATH", ""):
        env["PATH"] = r"C:\msys64\usr\bin;" + env.get("PATH", "")

    # Invalid arguments
    for bad in (["--mode", "nope", "--size", "64", "--count", "10"],
                ["--mode", "pipe", "--size", "0", "--count", "10"],
                ["--mode", "pipe", "--size", "64", "--count", "0"],
                ["--mode", "pipe", "--workload", "bad", "--size", "64", "--count", "10"]):
        r = subprocess.run([ub] + bad, env=env, capture_output=True, text=True)
        assert r.returncode == 2

    # Valid RTT monotonic percentiles invariant
    for mode in ("pipe", "fifo", "posix", "shm", "uds", "adaptive"):
        r = subprocess.run(
            [ub, "--mode", mode, "--workload", "rtt", "--size", "64", "--count", "50", "--warmup", "5"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"{mode} failed: {r.stderr} {r.stdout}"
        d = json.loads(r.stdout.strip().splitlines()[-1])
        assert d["status"] == "PASS"
        assert d["validation_errors"] == 0
        assert d["completed_messages"] == 50
        assert d["min_rtt_us"] <= d["p50_rtt_us"] <= d["p90_rtt_us"] <= d["p95_rtt_us"] <= d["p99_rtt_us"] <= d["p999_rtt_us"] <= d["max_rtt_us"]

    # SHM oversized -> UNSUPPORTED (rc=3)
    r_shm = subprocess.run(
        [ub, "--mode", "shm", "--workload", "rtt", "--size", "4096", "--count", "10"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert r_shm.returncode == 3
    assert json.loads(r_shm.stdout.strip())["status"] == "UNSUPPORTED"

    # Concurrency unsupported topologies -> rc=3
    r_shm_c = subprocess.run(
        [ub, "--mode", "shm", "--workload", "concurrency", "--size", "256", "--count", "20", "--producers", "2", "--consumers", "1"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert r_shm_c.returncode == 3
    assert json.loads(r_shm_c.stdout.strip())["status"] == "UNSUPPORTED"

    r_pipe_2c = subprocess.run(
        [ub, "--mode", "pipe", "--workload", "concurrency", "--size", "256", "--count", "20", "--producers", "1", "--consumers", "2"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert r_pipe_2c.returncode == 3
    assert json.loads(r_pipe_2c.stdout.strip())["status"] == "UNSUPPORTED"

    # Concurrency valid multi-producer/multi-consumer
    for mode, p, c in [("pipe", 2, 1), ("posix", 4, 4), ("uds", 1, 2), ("uds", 4, 4)]:
        rc = subprocess.run(
            [ub, "--mode", mode, "--workload", "concurrency", "--size", "256", "--count", "80",
             "--producers", str(p), "--consumers", str(c)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert rc.returncode == 0, f"{mode} {p}P/{c}C failed: {rc.stdout} {rc.stderr}"
        dc = json.loads(rc.stdout.strip().splitlines()[-1])
        assert dc["status"] == "PASS"
        assert dc["completed_messages"] == 80
        assert dc["validation_errors"] == 0

    # Selector overhead
    rs = subprocess.run(
        [ub, "--mode", "adaptive", "--workload", "selector_overhead", "--size", "1024", "--count", "10000"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert rs.returncode == 0
    ds = json.loads(rs.stdout.strip())
    assert ds["bytes_per_sec"] is None


def test_statistical_primitives():
    # Student's t critical value df=6 -> 2.44691185
    t6 = analyze_results.student_t_crit_95(6)
    assert abs(t6 - 2.44691185) < 1e-4

    # Exact Wilcoxon signed-rank for n=7 all positive diffs -> W=0, p = 2/128 = 0.015625
    a = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0]
    b = [15.0, 18.0, 21.0, 22.0, 25.0, 27.0, 30.0]
    w, wp = analyze_results.wilcoxon_signed_rank(a, b)
    assert w == 0.0
    assert abs(wp - 0.015625) < 1e-6

    # Paired t-test known values
    t_stat, p_val, ci_lo, ci_hi = analyze_results.paired_t_test(a, b)
    assert t_stat < -5.0
    assert p_val < 0.001
    assert ci_lo < ci_hi < 0.0


def test_pipeline_analysis_graphs_and_report():
    """Verify full Python pipeline on realistic synthetic multi-trial fixture."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw")
        proc = os.path.join(tmp, "processed")
        graphs = os.path.join(tmp, "graphs")
        reports = os.path.join(tmp, "reports")
        os.makedirs(raw); os.makedirs(proc); os.makedirs(graphs); os.makedirs(reports)

        # Build synthetic 7-trial dataset covering PASS, UNSUPPORTED, BLOCKED
        rows = []
        for trial in range(1, 8):
            for size in (64, 1024, 16384):
                for mode, base in (("pipe", 25.0), ("fifo", 40.0), ("posix", 30.0), ("shm", 18.0), ("uds", 35.0), ("adaptive", 19.0 if size <= 1024 else 26.0), ("sysv", None)):
                    if mode == "shm" and size > 1024:
                        rows.append({
                            "timestamp_utc": "2026-11-11T00:00:00Z", "experiment_id": "exp_test",
                            "environment_id": "test_env", "trial_order_index": 1,
                            "workload_type": "single_pair_rtt", "latency_semantics": "round_trip_rtt",
                            "requested_mode": mode, "selected_transport": mode,
                            "payload_bytes": size, "producers": 1, "consumers": 1, "trial": trial,
                            "warmup_count": 10, "target_messages": 100, "completed_messages": 0,
                            "validation_errors": 0, "status": "UNSUPPORTED", "status_reason": "EMSGSIZE",
                        })
                        continue
                    if mode == "sysv":
                        rows.append({
                            "timestamp_utc": "2026-11-11T00:00:00Z", "experiment_id": "exp_test",
                            "environment_id": "test_env", "trial_order_index": 1,
                            "workload_type": "single_pair_rtt", "latency_semantics": "round_trip_rtt",
                            "requested_mode": mode, "selected_transport": mode,
                            "payload_bytes": size, "producers": 1, "consumers": 1, "trial": trial,
                            "warmup_count": 10, "target_messages": 100, "completed_messages": 0,
                            "validation_errors": 0, "status": "BLOCKED", "status_reason": "ENOSYS",
                        })
                        continue
                    lat = base + (size / 2000.0) + (trial * 0.2)
                    sel = "shm" if (mode == "adaptive" and size <= 1024) else ("pipe" if mode == "adaptive" else mode)
                    rows.append({
                        "timestamp_utc": "2026-11-11T00:00:00Z", "experiment_id": "exp_test",
                        "environment_id": "test_env", "trial_order_index": 1,
                        "workload_type": "single_pair_rtt", "latency_semantics": "round_trip_rtt",
                        "requested_mode": mode, "selected_transport": sel,
                        "payload_bytes": size, "producers": 1, "consumers": 1, "trial": trial,
                        "warmup_count": 10, "target_messages": 100, "completed_messages": 100,
                        "validation_errors": 0, "status": "PASS", "status_reason": "ok",
                        "elapsed_ns": int(lat * 1000 * 100), "duration_s": lat * 100 / 1e6,
                        "avg_rtt_us": lat, "stddev_rtt_us": 2.5, "min_rtt_us": lat * 0.7,
                        "p50_rtt_us": lat * 0.95, "p90_rtt_us": lat * 1.15, "p95_rtt_us": lat * 1.25,
                        "p99_rtt_us": lat * 1.5, "p999_rtt_us": lat * 1.8, "max_rtt_us": lat * 2.0,
                        "throughput_msg_s": 1e6 / lat, "bytes_per_sec": (1e6 / lat) * size,
                        "mb_per_sec": (1e6 / lat) * size / 1e6, "wire_mb_per_sec": 2 * (1e6 / lat) * size / 1e6,
                        "user_cpu_s": 0.01, "sys_cpu_s": 0.01, "total_cpu_s": 0.02,
                        "cpu_util_pct": 80.0, "cpu_us_per_msg": 200.0,
                        "parent_peak_rss_kb": 6000, "child_peak_rss_kb": 5500, "combined_peak_rss_kb": 11500,
                        "major_page_faults": 100,
                    })

        from orchestrate_unified import FIELDNAMES
        with open(os.path.join(raw, "all_results.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in FIELDNAMES})

        # Minimal kernel BLOCKED csv
        with open(os.path.join(raw, "kernel_results.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["experiment_id", "record_type", "test_or_metric", "payload_bytes", "status", "status_reason", "workload_type"])
            w.writeheader()
            w.writerow({"experiment_id": "exp_test", "record_type": "functional_test", "test_or_metric": "module_compilation", "payload_bytes": "", "status": "BLOCKED", "status_reason": "test host", "workload_type": "kernel_functional"})
            w.writerow({"experiment_id": "exp_test", "record_type": "benchmark", "test_or_metric": "kernel_unidirectional_mailbox", "payload_bytes": 64, "status": "BLOCKED", "status_reason": "test host", "workload_type": "kernel_unidirectional_mailbox"})

        meta_path = os.path.join(proc, "benchmark_metadata.json")
        with open(meta_path, "w") as f:
            json.dump({"experiment_id": "exp_test", "host_os": "test", "config": {"messages": 100, "trials": 7, "threshold": 1024}}, f)
        with open(os.path.join(tmp, "environment.txt"), "w") as f:
            f.write("test env\n")

        subprocess.run([sys.executable, os.path.join(ROOT, "bench", "analyze_results.py"),
                        "--raw-dir", raw, "--processed-dir", proc, "--meta-in", meta_path], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "bench", "generate_graphs.py"),
                        "--raw-dir", raw, "--processed-dir", proc, "--graphs-dir", graphs], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "bench", "generate_report.py"),
                        "--unified-dir", tmp], check=True)

        expected_graphs = [
            "latency_comparison", "p50_latency", "p95_latency", "p99_latency",
            "throughput_comparison", "cpu_comparison", "memory_comparison",
            "context_switches", "syscall_comparison", "payload_scalability",
            "concurrency_scalability", "adaptive_vs_best", "kernel_vs_userspace",
        ]
        for g in expected_graphs:
            assert os.path.getsize(os.path.join(graphs, f"{g}.png")) > 1000
            assert os.path.getsize(os.path.join(graphs, f"{g}.pdf")) > 1000

        rep = open(os.path.join(reports, "FINAL_BENCHMARK_REPORT.md"), encoding="utf-8").read()
        for sec in ("## 1. Executive Summary", "## 10. Latency Comparison", "## 18. Adaptive Selector Evaluation",
                    "## 19. Kernel Mailbox Evaluation", "## 20. Statistical Analysis", "## 24. Conclusions"):
            assert sec in rep

        meta_out = json.load(open(os.path.join(proc, "benchmark_metadata.json")))
        assert meta_out["component_status"]["kernel_aipc"]["status"] == "BLOCKED"
        assert meta_out["component_status"]["sysv"]["status"] == "BLOCKED"
        assert meta_out["component_status"]["shm"]["status"] == "PASS"

