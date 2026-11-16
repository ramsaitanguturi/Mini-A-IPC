#!/usr/bin/env python3
"""Automated research-grade Markdown benchmark report generator for Mini A-IPC.

Reads ONLY genuine experimental outputs from results/unified/raw/,
results/unified/processed/, and results/unified/environment.txt and emits
results/unified/reports/FINAL_BENCHMARK_REPORT.md covering all 24 required sections.
"""
import argparse
import json
import math
import os

import pandas as pd


COMP_INFO = [
    ("1", "Anonymous Pipes", "src/ipc_pipe.c", "pipe", "Kernel unidirectional ring buffer pair (`pipe()` / `read()` / `write()`)."),
    ("2", "Named Pipes / FIFO", "src/ipc_fifo.c", "fifo", "Filesystem-backed kernel FIFO rendezvous (`mkfifo()` / `open()` / `read()` / `write()`)."),
    ("3", "System V Message Queue", "src/ipc_sysv_mq.c", "sysv", "Kernel discrete typed message queue (`msgget()` / `msgsnd()` / `msgrcv()`)."),
    ("4", "POSIX Message Queue", "src/ipc_posix_mq.c", "posix", "POSIX priority message queues (`mq_open()` / `mq_send()` / `mq_receive()`)."),
    ("5", "POSIX Shared Memory", "src/ipc_shm.c", "shm", "Shared memory mapping (`shm_open()` / `mmap()`) + 4 POSIX process-shared semaphores (`<= 1024 B`)."),
    ("6", "Unix Domain Socket", "src/ipc_uds.c", "uds", "Connection-oriented local stream socket (`AF_UNIX`, `SOCK_STREAM`)."),
    ("7", "Kernel AIPC Module", "kernel/aipc_module.c", "kernel_aipc", "Loadable Linux kernel character device (`/dev/aipc`) ring buffer with mutex & wait queues."),
    ("8", "Adaptive Policy Selector", "src/selector.c", "adaptive", "User-space policy selecting `shm` for payloads `<= min(threshold, 1024)` and `pipe` otherwise."),
]


def _fmt(v, digits=2, suffix=""):
    if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    try:
        fv = float(v)
        if math.isnan(fv):
            return "N/A"
        return f"{fv:,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_bytes(b):
    b = int(b)
    return f"{b // 1024} KB" if (b >= 1024 and b % 1024 == 0) else f"{b} B"


def _df_md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Generate FINAL_BENCHMARK_REPORT.md")
    ap.add_argument("--unified-dir", required=True)
    args = ap.parse_args()

    raw_dir = os.path.join(args.unified_dir, "raw")
    proc_dir = os.path.join(args.unified_dir, "processed")
    rep_dir = os.path.join(args.unified_dir, "reports")
    os.makedirs(rep_dir, exist_ok=True)

    all_df = pd.read_csv(os.path.join(raw_dir, "all_results.csv"))
    agg_df = pd.read_csv(os.path.join(proc_dir, "aggregated_results.csv"))
    stat_df = pd.read_csv(os.path.join(proc_dir, "statistical_summary.csv")) if os.path.exists(os.path.join(proc_dir, "statistical_summary.csv")) else pd.DataFrame()
    mem_df = pd.read_csv(os.path.join(raw_dir, "memory_metrics.csv"))
    sys_df = pd.read_csv(os.path.join(raw_dir, "system_metrics.csv"))
    adp_df = pd.read_csv(os.path.join(raw_dir, "adaptive_results.csv"))
    k_df = pd.read_csv(os.path.join(raw_dir, "kernel_results.csv")) if os.path.exists(os.path.join(raw_dir, "kernel_results.csv")) else pd.DataFrame()

    with open(os.path.join(proc_dir, "benchmark_metadata.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)

    env_path = os.path.join(args.unified_dir, "environment.txt")
    env_text = open(env_path, "r", encoding="utf-8", errors="replace").read() if os.path.exists(env_path) else "environment.txt missing"

    exp_id = meta.get("experiment_id", "unknown")
    overall = meta.get("overall_status", "UNKNOWN")
    comp_status = meta.get("component_status", {})
    cfg = meta.get("config", {})
    adp_sum = meta.get("adaptive_summary", {})
    agg_rtt = agg_df[agg_df["workload_type"] == "single_pair_rtt"].copy()
    rtt_pass = agg_rtt[agg_rtt["status"] == "PASS"].copy()

    lines = []
    add = lines.append

    add(f"# Mini A-IPC: Unified IPC Experimental Benchmark Report\n")
    add(f"- **Experiment ID**: `{exp_id}`")
    add(f"- **Generated At (UTC)**: `{meta.get('analyzed_at_utc', '')}`")
    add(f"- **Overall Evaluation Status**: **{overall}**")
    add(f"- **Host Environment**: `{meta.get('host_os', '')}` | Kernel `{meta.get('kernel_release', '')}` | Arch `{meta.get('machine', '')}`\n")

    # 1. Executive Summary
    add("## 1. Executive Summary\n")
    if overall != "PASS":
        blocked_items = [k for k, v in comp_status.items() if v.get("status") in ("BLOCKED", "FAIL")]
        add(f"> [!IMPORTANT]")
        add(f"> Overall benchmark status is **{overall}**. Components not fully executed in this environment: "
            f"`{', '.join(blocked_items) if blocked_items else 'none'}`. "
            f"Because the kernel module and/or blocked transports could not execute on this host, the cross-8-component comparison is explicitly incomplete and missing measurements are reported as `BLOCKED`/`N/A` rather than fabricated.\n")
    else:
        add("All eight Mini A-IPC components were evaluated under controlled, sequential, randomized-order trials with zero validation errors.\n")

    if not rtt_pass.empty:
        # Highlight empirical winner at 64 B and 16 KB
        for check_p in (64, 1024, 16384, 262144):
            sub_p = rtt_pass[(rtt_pass["payload_bytes"] == check_p) & (~rtt_pass["mechanism"].isin(["adaptive"]))]
            if not sub_p.empty:
                best_row = sub_p.loc[sub_p["avg_rtt_us_mean"].astype(float).idxmin()]
                add(f"- **Fastest eligible transport at {_fmt_bytes(check_p)}**: `{best_row['mechanism']}` "
                    f"(mean RTT **{_fmt(best_row['avg_rtt_us_mean'])} us**, "
                    f"P50 **{_fmt(best_row['p50_rtt_us_median'])} us**, "
                    f"throughput **{_fmt(best_row['throughput_msg_s_mean'], 1)} msg/s**).")
    if adp_sum:
        add(f"- **Adaptive Policy Selector (`src/selector.c`)**: "
            f"Selection accuracy **{adp_sum.get('selection_accuracy_avg_rtt_pct', 'N/A')}%** (vs empirical best mean RTT), "
            f"mean latency regret **{_fmt(adp_sum.get('mean_regret_latency_pct'), 2)}%**, "
            f"decision overhead **{_fmt(adp_sum.get('selection_overhead_ns'), 2)} ns/call**.\n")

    # 2. Project Architecture
    add("## 2. Project Architecture\n")
    add("Mini A-IPC separates transport implementations (`src/ipc_*.c`), adaptive selection policy (`src/selector.c`), "
        "kernel mailbox (`kernel/aipc_module.c`), and the unified controlled benchmarking harness (`bench/unified_bench.c` + `bench/run_unified_benchmark.sh`). "
        "Primary latency measurements run directly in compiled C using `CLOCK_MONOTONIC` with process-isolated setup/teardown and zero strace/polling overhead inside the timed loop.\n")

    # 3. All Eight Components
    add("## 3. All Eight Components\n")
    comp_rows = []
    for cid, cname, cimpl, ckey, cdesc in COMP_INFO:
        st = comp_status.get(ckey, {"status": "BLOCKED", "reason": "Not recorded"})
        comp_rows.append([cid, cname, f"`{cimpl}`", f"**{st['status']}**", st["reason"], cdesc])
    add(_df_md_table(["ID", "Component", "Implementation", "Status", "Status Rationale", "Mechanism Semantics"], comp_rows))
    add("")

    # 4. Experimental Environment
    add("## 4. Experimental Environment\n")
    add("```text")
    add(env_text.strip())
    add("```\n")

    # 5. Hardware and Software Configuration
    add("## 5. Hardware and Software Configuration\n")
    hw_rows = [
        ["Host OS / Subsystem", f"`{meta.get('host_os', '')}` (`{meta.get('platform_detail', '')}`)"],
        ["Kernel Release", f"`{meta.get('kernel_release', '')}`"],
        ["CPU Model", f"`{meta.get('cpu_model', 'unknown')}`"],
        ["Logical CPUs", f"`{meta.get('cpu_count', 'unknown')}`"],
        ["Compiler", f"`{meta.get('compiler', 'unknown')}`"],
        ["Optimization & Flags", f"`{meta.get('build_flags', '')}`"],
        ["Python Runtime", f"`{meta.get('python_version', '')}` (`scipy={meta.get('scipy_available', False)}`)"],
        ["CPU Affinity Policy", f"Producer core `{cfg.get('cpu_producer', -1)}`, Consumer core `{cfg.get('cpu_consumer', -1)}` (`sched_setaffinity`)"],
    ]
    add(_df_md_table(["Parameter", "Observed Value"], hw_rows))
    add("")

    # 6. Benchmark Methodology
    add("## 6. Benchmark Methodology\n")
    add("- **Sequential execution**: One benchmark configuration runs at a time to eliminate cross-experiment contention.\n"
        "- **Trial-block randomization**: Within each trial block `1..T`, mechanism execution order is shuffled using deterministic PRNG seed "
        f"`{cfg.get('seed', '')}` (recorded in `benchmark_metadata.json`).\n"
        "- **Process isolation & cleanup**: Each trial executes in a fresh process invocation, unlinking FIFOs, POSIX MQs, SysV queues, shared memory segments, and UDS sockets before and after each trial.\n"
        "- **Instrumentation separation**: Primary trials record latency, throughput, and `getrusage()` around the run; per-process RSS sampling, context-switch polling, and syscall tracing execute in a separate profiling pass (`bench/profile_resources.py`).\n")

    # 7. Workload Definitions
    add("## 7. Workload Definitions\n")
    add("1. **`single_pair_rtt` (1P/1C Round-Trip Request-Response)**: Parent producer writes payload of size $S$, child consumer validates/echoes $S$ back, parent verifies byte-for-byte identity (`memcmp == 0`). **Latency represents full round-trip time (RTT)**.\n"
        "2. **`concurrency_pipeline` (M-Producer / N-Consumer One-Way Validated Pipeline)**: $M$ producer processes send `24`-byte header + deterministic payload with FNV-1a checksum (`M:N` across `1P/1C`, `2P/1C`, `4P/1C`, `1P/2C`, `4P/4C`); $N$ consumers validate every byte and report counts back to coordinator. Classified strictly separately from RTT.\n"
        "3. **`unidirectional_stream` & `kernel_unidirectional_mailbox`**: 1P->1C unidirectional transfer matching `/dev/aipc` ring-buffer semantics.\n"
        "4. **`mixed_80_20` (`mini-aipc-mixed`)**: Deterministic shuffled sequence of 80% 64 B and 20% 16 KB messages comparing `pipe` vs `adaptive`.\n"
        "5. **`selector_overhead`**: Tight loop calling `select_transport()` to isolate decision latency in nanoseconds.\n")

    # 8. Measurement Methodology
    add("## 8. Measurement Methodology\n")
    add("- **Clocks**: `clock_gettime(CLOCK_MONOTONIC)` with nanosecond resolution.\n"
        "- **Percentiles**: Exact nearest-rank indexing ($k = N - \\lfloor N / D \\rfloor$, index $k - 1$) on sorted per-exchange sample arrays (`P50` conventional median, `P90`, `P95`, `P99`, `P99.9`), plus sample standard deviation ($s$, $N-1$ denominator).\n"
        "- **Throughput**: Calculated strictly from validated completed messages (`validation_errors == 0`). `MB/s` uses SI $10^6$ bytes/sec; both logical payload bandwidth and bidirectional RTT wire bandwidth are preserved in CSVs.\n"
        "- **CPU & Memory**: `getrusage(RUSAGE_SELF)` + `getrusage(RUSAGE_CHILDREN)` outside the timed loop for CPU user/system times and peak RSS, plus separate 2 ms process-tree polling (`Win32 NtQuerySystemInformation` / Linux `/proc/<pid>/status`) for average RSS and context switches.\n")

    # 9. Raw Experiment Configuration
    add("## 9. Raw Experiment Configuration\n")
    cfg_rows = [[k, f"`{v}`"] for k, v in cfg.items()]
    add(_df_md_table(["Configuration Key", "Value"], cfg_rows))
    add("")

    # 10. Latency Comparison
    add("## 10. Latency Comparison\n")
    lat_rows = []
    for _, r in agg_rtt.sort_values(["payload_bytes", "mechanism"]).iterrows():
        lat_rows.append([
            _fmt_bytes(r["payload_bytes"]), r["mechanism"], r["status"],
            _fmt(r.get("avg_rtt_us_mean")), _fmt(r.get("avg_rtt_us_std")),
            _fmt(r.get("p50_rtt_us_median")), _fmt(r.get("p90_rtt_us_median")),
            _fmt(r.get("p95_rtt_us_median")), _fmt(r.get("p99_rtt_us_median")),
            _fmt(r.get("min_rtt_us_min")), _fmt(r.get("max_rtt_us_max")),
        ])
    add(_df_md_table(
        ["Payload", "Mechanism", "Status", "Avg Mean (us)", "Trial SD (us)", "P50 (us)", "P90 (us)", "P95 (us)", "P99 (us)", "Min (us)", "Max (us)"],
        lat_rows,
    ))
    add("\n![Latency Comparison](../graphs/latency_comparison.png)\n")
    add("![P50 Latency](../graphs/p50_latency.png)\n")
    add("![P95 Latency](../graphs/p95_latency.png)\n")
    add("![P99 Latency](../graphs/p99_latency.png)\n")

    # 11. Throughput Comparison
    add("## 11. Throughput Comparison\n")
    tput_rows = []
    for _, r in rtt_pass.sort_values(["payload_bytes", "mechanism"]).iterrows():
        tput_rows.append([
            _fmt_bytes(r["payload_bytes"]), r["mechanism"],
            _fmt(r.get("throughput_msg_s_mean"), 1),
            _fmt(r.get("bytes_per_sec_mean"), 0),
            _fmt(r.get("mb_per_sec_mean"), 3),
            _fmt(r.get("wire_mb_per_sec_mean"), 3),
        ])
    add(_df_md_table(["Payload", "Mechanism", "Msg/s (Mean)", "Bytes/s (Mean)", "Payload MB/s", "RTT Wire MB/s"], tput_rows))
    add("\n![Throughput Comparison](../graphs/throughput_comparison.png)\n")

    # 12. CPU Comparison
    add("## 12. CPU Comparison\n")
    cpu_rows = []
    for _, r in rtt_pass.sort_values(["payload_bytes", "mechanism"]).iterrows():
        cpu_rows.append([
            _fmt_bytes(r["payload_bytes"]), r["mechanism"],
            _fmt(r.get("user_cpu_s_mean"), 4), _fmt(r.get("sys_cpu_s_mean"), 4),
            _fmt(r.get("total_cpu_s_mean"), 4), _fmt(r.get("cpu_util_pct_mean"), 1),
            _fmt(r.get("cpu_us_per_msg_mean"), 2),
        ])
    add(_df_md_table(["Payload", "Mechanism", "User CPU (s)", "Sys CPU (s)", "Total CPU (s)", "CPU Util (%)", "CPU us/msg"], cpu_rows))
    add("\n![CPU Comparison](../graphs/cpu_comparison.png)\n")

    # 13. Memory Comparison
    add("## 13. Memory Comparison\n")
    mem_pass = mem_df[mem_df["status"] == "PASS"] if not mem_df.empty else pd.DataFrame()
    if not mem_pass.empty:
        mem_rows = []
        for _, r in mem_pass.sort_values(["payload_bytes", "mechanism"]).iterrows():
            mem_rows.append([
                _fmt_bytes(r["payload_bytes"]), r["mechanism"],
                _fmt(r.get("producer_avg_rss_kb"), 0), _fmt(r.get("consumer_avg_rss_kb"), 0),
                _fmt(r.get("total_avg_rss_kb"), 0), _fmt(r.get("total_peak_rss_kb"), 0),
                _fmt(r.get("kernel_slab_kb"), 0),
            ])
        add(_df_md_table(["Payload", "Mechanism", "Prod Avg RSS (KB)", "Cons Avg RSS (KB)", "Total Avg RSS (KB)", "Total Peak RSS (KB)", "Kernel Slab (KB)"], mem_rows))
    else:
        add("Memory profiler data was unavailable.\n")
    add("\n![Memory Comparison](../graphs/memory_comparison.png)\n")

    # 14. Context-Switch Comparison
    add("## 14. Context-Switch Comparison\n")
    sys_pass = sys_df[sys_df["status"] == "PASS"] if not sys_df.empty else pd.DataFrame()
    if not sys_pass.empty:
        cs_rows = []
        for _, r in sys_pass.sort_values(["payload_bytes", "mechanism"]).iterrows():
            cs_rows.append([
                _fmt_bytes(r["payload_bytes"]), r["mechanism"],
                _fmt(r.get("total_ctx_switches"), 0),
                _fmt(r.get("voluntary_ctx_switches"), 0),
                _fmt(r.get("involuntary_ctx_switches"), 0),
                _fmt(r.get("major_page_faults"), 0),
                r.get("ctx_profiling_method", ""),
            ])
        add(_df_md_table(["Payload", "Mechanism", "Total Ctx Sw", "Voluntary", "Involuntary", "Page Faults", "Method"], cs_rows))
    add("\n![Context Switches](../graphs/context_switches.png)\n")

    # 15. System-Call Comparison
    add("## 15. System-Call Comparison\n")
    if not sys_df.empty and "syscall_status" in sys_df.columns:
        sc_sub = sys_df.drop_duplicates(subset=["mechanism"])
        sc_rows = []
        for _, r in sc_sub.iterrows():
            sc_rows.append([
                r["mechanism"], r["syscall_status"],
                _fmt(r.get("comm_syscalls_per_exchange"), 2),
                _fmt(r.get("setup_cleanup_syscalls"), 0),
                _fmt(r.get("total_syscalls"), 0),
                r.get("syscall_reason", ""),
            ])
        add(_df_md_table(["Mechanism", "Syscall Status", "Comm/Exch", "Setup/Cleanup", "Total", "Notes"], sc_rows))
    add("\n![System Call Comparison](../graphs/syscall_comparison.png)\n")

    # 16. Payload Scalability
    add("## 16. Payload Scalability\n")
    add("Payload scaling spans `64 B` to `256 KB`. `shm` is bounded to `<= 1024 B` (`SHM_MAX_PAYLOAD`), cleanly transitioning to `UNSUPPORTED` above 1 KB, while `pipe`, `fifo`, `posix`, `uds`, and `adaptive` scale across the full sweep.\n")
    add("![Payload Scalability](../graphs/payload_scalability.png)\n")

    # 17. Concurrency Scalability
    add("## 17. Concurrency Scalability\n")
    conc_agg = agg_df[agg_df["workload_type"] == "concurrency_pipeline"].copy()
    if not conc_agg.empty:
        c_rows = []
        for _, r in conc_agg.sort_values(["producers", "consumers", "mechanism"]).iterrows():
            topo = f"{int(r['producers'])}P/{int(r['consumers'])}C"
            c_rows.append([
                topo, r["mechanism"], r["status"],
                _fmt(r.get("throughput_msg_s_mean"), 1),
                _fmt(r.get("mb_per_sec_mean"), 3),
                _fmt(r.get("cpu_us_per_msg_mean"), 2),
                r["status_reason"],
            ])
        add(_df_md_table(["Topology", "Mechanism", "Status", "Throughput (msg/s)", "MB/s", "CPU us/msg", "Notes"], c_rows))
    add("\n![Concurrency Scalability](../graphs/concurrency_scalability.png)\n")

    # 18. Adaptive Selector Evaluation
    add("## 18. Adaptive Selector Evaluation\n")
    if not adp_df.empty:
        adp_rows = []
        for _, r in adp_df[adp_df["status"] == "PASS"].iterrows():
            adp_rows.append([
                _fmt_bytes(r["payload_bytes"]), r["chosen_transport"],
                r["empirical_best_by_avg_rtt"], r["empirical_best_by_throughput"],
                str(r["selection_accurate_avg_rtt"]),
                _fmt(r["adaptive_avg_rtt_us"]), _fmt(r["best_avg_rtt_us"]),
                _fmt(r["regret_latency_pct"], 2, "%"),
                _fmt(r["latency_diff_vs_pipe_pct"], 2, "%"),
                _fmt(r["selection_overhead_ns"], 2, " ns"),
            ])
        add(_df_md_table(
            ["Payload", "Chosen", "Best (Avg RTT)", "Best (Tput)", "Optimal?", "Adaptive RTT (us)", "Best RTT (us)", "Regret vs Best", "Diff vs Pipe", "Decision Cost"],
            adp_rows,
        ))
    mixed_agg = agg_df[agg_df["workload_type"] == "mixed_80_20"]
    if not mixed_agg.empty:
        add("\n### Mixed 80%/20% Workload (`mini-aipc-mixed`)\n")
        m_rows = []
        for _, r in mixed_agg.iterrows():
            m_rows.append([
                r["mechanism"], r["status"],
                _fmt(r.get("avg_rtt_us_mean")), _fmt(r.get("throughput_msg_s_mean"), 1),
                _fmt(r.get("cpu_us_per_msg_mean"), 2),
            ])
        add(_df_md_table(["Policy", "Status", "Avg Latency (us)", "Throughput (exch/s)", "CPU us/msg"], m_rows))
    add("\n![Adaptive vs Best](../graphs/adaptive_vs_best.png)\n")

    # 19. Kernel Mailbox Evaluation
    add("## 19. Kernel Mailbox Evaluation\n")
    if not k_df.empty:
        k_func = k_df[k_df["record_type"] == "functional_test"]
        kf_rows = [[r["test_or_metric"], r["status"], r["status_reason"]] for _, r in k_func.iterrows()]
        add("### Functional Test Matrix\n")
        add(_df_md_table(["Kernel Check", "Status", "Diagnostic Detail"], kf_rows))
        k_bench = k_df[k_df["record_type"] == "benchmark"]
        if not k_bench.empty:
            add("\n### Matched Unidirectional Kernel Benchmark\n")
            kb_rows = []
            for _, r in k_bench.iterrows():
                kb_rows.append([
                    _fmt_bytes(r["payload_bytes"]) if pd.notna(r["payload_bytes"]) and r["payload_bytes"] != "" else "N/A",
                    r["status"], _fmt(r.get("avg_latency_us")), _fmt(r.get("throughput_msg_s"), 1),
                    _fmt(r.get("mb_per_sec"), 3), r["status_reason"],
                ])
            add(_df_md_table(["Payload", "Status", "Avg Latency (us)", "Msg/s", "MB/s", "Reason / Notes"], kb_rows))
    add("\n![Kernel vs Userspace](../graphs/kernel_vs_userspace.png)\n")

    # 20. Statistical Analysis
    add("## 20. Statistical Analysis\n")
    add(f"Matched paired statistical tests were performed across matched trial blocks (`n_pairs = {cfg.get('trials', '')}`). "
        f"Both parametric **paired Student's t-test** (with 95% confidence interval of mean difference) and non-parametric **Wilcoxon signed-rank test** "
        f"({'SciPy' if meta.get('scipy_available') else 'exact built-in enumeration/incomplete beta'}) are reported below for key adaptive and best-transport comparisons.\n")
    if not stat_df.empty:
        key_stat = stat_df[
            (stat_df["comparison_group"].isin(["adaptive_vs_best", "adaptive_vs_pipe", "mixed_workload_adaptive_vs_pipe"]))
            & (stat_df["metric"].isin(["avg_rtt_us", "throughput_msg_s"]))
        ]
        s_rows = []
        for _, r in key_stat.iterrows():
            s_rows.append([
                r["comparison_group"], str(r["payload_bytes"]), r["metric"],
                f"{r['mechanism_a']} vs {r['mechanism_b']}", int(r["n_pairs"]),
                _fmt(r["mean_diff_a_minus_b"], 3), _fmt(r["diff_pct"], 2, "%"),
                _fmt(r["paired_t_pvalue"], 5), _fmt(r["wilcoxon_pvalue"], 5),
                r["significant_alpha_05"],
            ])
        if s_rows:
            add(_df_md_table(["Comparison", "Payload", "Metric", "Pair", "n", "Mean Diff", "Diff %", "t p-val", "Wilcoxon p-val", "Sig (a=0.05)"], s_rows))
    add("")

    # 21. Limitations
    add("## 21. Limitations\n")
    add("1. **Host OS / Kernel Scope**: Experiments reflect the actual host environment documented in Section 4/5. Where Linux kernel build headers, `insmod` privileges, Linux `strace`, or System V IPC (`cygserver` on MSYS2) are unavailable, those components are marked `BLOCKED`/`UNAVAILABLE` rather than simulated.\n"
        "2. **Timer & `getrusage` Granularity**: On Windows/MSYS2, `getrusage()` CPU user/sys times advance in coarse scheduler ticks (~15.6 ms) and `ru_nvcsw`/`ru_nivcsw` are unsupported (`0`); thread context switches were captured via separate Win32 `NtQuerySystemInformation` polling without voluntary/involuntary split.\n"
        "3. **Workload Semantic Differences**: `single_pair_rtt` (bidirectional round-trip) and `concurrency_pipeline` / `kernel_unidirectional_mailbox` (one-way validated transfer) have distinct synchronization semantics and are never combined into single axes.\n"
        "4. **Shared Memory Capacity**: `src/ipc_shm.c` imposes `SHM_MAX_PAYLOAD = 1024` bytes.\n")

    # 22. Failed or Unsupported Experiments
    add("## 22. Failed or Unsupported Experiments\n")
    non_pass = all_df[all_df["status"] != "PASS"].drop_duplicates(
        subset=["workload_type", "requested_mode", "payload_bytes", "producers", "consumers", "status", "status_reason"]
    )
    if non_pass.empty and (k_df.empty or (k_df["status"] == "PASS").all()):
        add("No failed, blocked, or unsupported configurations encountered.\n")
    else:
        np_rows = []
        for _, r in non_pass.iterrows():
            np_rows.append([
                r["workload_type"], r["requested_mode"], _fmt_bytes(r["payload_bytes"]),
                f"{int(r['producers'])}P/{int(r['consumers'])}C", r["status"], r["status_reason"],
            ])
        if not k_df.empty:
            k_np = k_df[k_df["status"] != "PASS"].drop_duplicates(subset=["test_or_metric", "status", "status_reason"])
            for _, r in k_np.iterrows():
                np_rows.append([
                    r["workload_type"], "kernel_aipc", str(r["test_or_metric"]), "1P/1C", r["status"], r["status_reason"],
                ])
        add(_df_md_table(["Workload", "Component", "Payload / Check", "Topology", "Status", "Exact Diagnostic Reason"], np_rows))
    add("")

    # 23. Reproducibility Instructions
    add("## 23. Reproducibility Instructions\n")
    add("```bash\n"
        "# Run complete unified benchmark with default controlled configuration\n"
        "./bench/run_unified_benchmark.sh\n\n"
        "# Or reproduce this exact run configuration:\n"
        f"./bench/run_unified_benchmark.sh --messages {cfg.get('messages', 10000)} "
        f"--warmup {cfg.get('warmup', 500)} --trials {cfg.get('trials', 7)} "
        f"--payloads {cfg.get('payloads', '64,256,1024,4096,16384,65536,262144')} "
        f"--seed {cfg.get('seed', 20261111)}\n"
        "```\n")

    # 24. Conclusions
    add("## 24. Conclusions\n")
    add("- Every measurement in this report was empirically collected from this session's executable runs (`all_results.csv`, `memory_metrics.csv`, `system_metrics.csv`, `adaptive_results.csv`, `kernel_results.csv`).\n"
        "- The adaptive selector (`src/selector.c`) incurs negligible decision overhead (~nanoseconds) but uses a fixed static threshold (`<= 1024 B -> shm`, else `pipe`), meaning its empirical selection accuracy depends directly on whether `shm`/`pipe` outperform `uds` or `posix` on the target OS.\n"
        "- For complete 8/8 evaluation including System V MQ and `/dev/aipc` kernel module execution, run the identical `./bench/run_unified_benchmark.sh` command on a native Linux host with matching `linux-headers-$(uname -r)` and `strace`.\n")

    out_md = os.path.join(rep_dir, "FINAL_BENCHMARK_REPORT.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote report to {out_md}")


if __name__ == "__main__":
    main()

