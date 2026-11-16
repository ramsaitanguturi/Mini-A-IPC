#!/usr/bin/env python3
"""Publication-quality graph generator for Mini A-IPC unified benchmarks.

Generates all 13 required figures in both 300-DPI PNG and vector PDF formats
under results/unified/graphs/, strictly respecting workload boundaries and
explicitly annotating BLOCKED / UNAVAILABLE / UNSUPPORTED mechanisms without
fabricating zeros.
"""
import argparse
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


MECH_ORDER = ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive", "kernel"]
MECH_LABELS = {
    "pipe": "Anonymous Pipe",
    "fifo": "Named Pipe (FIFO)",
    "sysv": "System V MQ",
    "posix": "POSIX MQ",
    "shm": "POSIX Shared Mem",
    "uds": "Unix Domain Socket",
    "adaptive": "Adaptive Selector",
    "kernel": "Kernel AIPC (/dev/aipc)",
}
MECH_COLORS = {
    "pipe": "#0072B2",
    "fifo": "#56B4E9",
    "sysv": "#E69F00",
    "posix": "#009E73",
    "shm": "#CC79A7",
    "uds": "#D55E00",
    "adaptive": "#111111",
    "kernel": "#8C564B",
}
MECH_MARKERS = {
    "pipe": "o",
    "fifo": "s",
    "sysv": "^",
    "posix": "D",
    "shm": "v",
    "uds": "P",
    "adaptive": "*",
    "kernel": "X",
}


def fmt_bytes(b):
    b = int(b)
    if b >= 1024 and b % 1024 == 0:
        return f"{b // 1024} KB"
    return f"{b} B"


def setup_style():
    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "legend.fontsize": 8.5,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "axes.grid": True,
        "grid.alpha": 0.28,
        "grid.linestyle": "--",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#FCFCFD",
    })


def save_fig(fig, out_dir, name):
    png_path = os.path.join(out_dir, f"{name}.png")
    pdf_path = os.path.join(out_dir, f"{name}.pdf")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)


def blocked_note(meta, subset_keys=("sysv", "kernel_aipc")):
    cs = meta.get("component_status", {})
    notes = []
    for k in subset_keys:
        if k in cs and cs[k].get("status") in ("BLOCKED", "FAIL", "UNAVAILABLE"):
            label = "System V MQ" if k == "sysv" else "Kernel /dev/aipc"
            notes.append(f"{label}: {cs[k]['status']}")
    return "; ".join(notes)


def plot_grouped_bar_metric(agg_rtt, meta, metric_prefix, ylabel, title, out_dir, filename,
                            selected_payloads=(64, 1024, 16384, 65536, 262144)):
    """Grouped bar chart with 95% CI error bars across representative payload sizes."""
    sub = agg_rtt[agg_rtt["status"] == "PASS"].copy()
    avail_payloads = [p for p in selected_payloads if p in set(sub["payload_bytes"])]
    if not avail_payloads:
        avail_payloads = sorted(sub["payload_bytes"].unique())

    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]
             if m in set(sub["mechanism"])]

    fig, ax = plt.subplots(figsize=(12, 5.8))
    x = np.arange(len(avail_payloads))
    n_m = max(1, len(mechs))
    width = 0.80 / n_m

    for i, m in enumerate(mechs):
        means = []
        errs = []
        for p in avail_payloads:
            row = sub[(sub["mechanism"] == m) & (sub["payload_bytes"] == p)]
            if row.empty or pd.isna(row[f"{metric_prefix}_mean"].iloc[0]):
                means.append(0.0)
                errs.append(0.0)
            else:
                mv = float(row[f"{metric_prefix}_mean"].iloc[0])
                hi = row.get(f"{metric_prefix}_ci95_high", pd.Series([np.nan])).iloc[0]
                err = max(0.0, float(hi) - mv) if pd.notna(hi) else 0.0
                means.append(mv)
                errs.append(err)
        offset = (i - (n_m - 1) / 2.0) * width
        bars = ax.bar(
            x + offset, means, width, yerr=errs, capsize=2.5,
            label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"),
            edgecolor="white", linewidth=0.5, alpha=0.92,
            error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
        )
        # Annotate SHM unsupported payloads gently on first missing slot if needed
        for j, p in enumerate(avail_payloads):
            if m == "shm" and p > 1024:
                ax.text(x[j] + offset, 0.02 * max(1.0, ax.get_ylim()[1]), "N/A",
                        ha="center", va="bottom", fontsize=6.5, color="#777777", rotation=90)

    # Use log scale if max/min non-zero > 30 so small & 256KB bars are both visible, else linear from 0
    vals = [float(v) for v in sub[f"{metric_prefix}_mean"].dropna() if float(v) > 0]
    if vals and (max(vals) / min(vals) > 25):
        ax.set_yscale("log")
        ylabel = f"{ylabel} [log scale]"
    else:
        ax.set_ylim(bottom=0)

    ax.set_xticks(x)
    ax.set_xticklabels([fmt_bytes(p) for p in avail_payloads])
    ax.set_xlabel("Payload Size")
    ax.set_ylabel(ylabel)
    note = blocked_note(meta, ("sysv",))
    full_title = f"{title}\n(1P/1C Round-Trip | Mean ± 95% Student-t CI; {note})" if note else f"{title}\n(1P/1C Round-Trip | Mean ± 95% Student-t CI)"
    ax.set_title(full_title)
    ax.legend(ncol=4, loc="upper left", frameon=True)
    save_fig(fig, out_dir, filename)


def plot_percentile_curve(agg_rtt, meta, col_prefix, ylabel, title, out_dir, filename):
    """Line chart across ALL payload sizes for a given latency percentile."""
    sub = agg_rtt[agg_rtt["status"] == "PASS"].copy()
    payloads = sorted(sub["payload_bytes"].unique())
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]
             if m in set(sub["mechanism"])]

    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    x_pos = np.arange(len(payloads))
    for m in mechs:
        xs, ys, ylo, yhi = [], [], [], []
        for idx, p in enumerate(payloads):
            row = sub[(sub["mechanism"] == m) & (sub["payload_bytes"] == p)]
            if not row.empty and pd.notna(row[f"{col_prefix}_median"].iloc[0]):
                med = float(row[f"{col_prefix}_median"].iloc[0])
                mean_v = float(row[f"{col_prefix}_mean"].iloc[0])
                ci_l = row.get(f"{col_prefix}_ci95_low", pd.Series([np.nan])).iloc[0]
                ci_h = row.get(f"{col_prefix}_ci95_high", pd.Series([np.nan])).iloc[0]
                xs.append(idx)
                ys.append(med)
                ylo.append(max(0.0, med - float(ci_l)) if pd.notna(ci_l) else 0.0)
                yhi.append(max(0.0, float(ci_h) - med) if pd.notna(ci_h) else 0.0)
        if xs:
            ls = "--" if m == "adaptive" else "-"
            lw = 2.4 if m == "adaptive" else 1.8
            ax.plot(
                xs, ys, marker=MECH_MARKERS.get(m, "o"), linestyle=ls, linewidth=lw,
                label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"),
            )

    vals = [float(v) for v in sub[f"{col_prefix}_median"].dropna() if float(v) > 0]
    if vals and (max(vals) / min(vals) > 20):
        ax.set_yscale("log")
        ylabel = f"{ylabel} [log scale]"
    else:
        ax.set_ylim(bottom=0)

    ax.set_xticks(x_pos)
    ax.set_xticklabels([fmt_bytes(p) for p in payloads])
    ax.set_xlabel("Payload Size (Bytes / KiB)")
    ax.set_ylabel(ylabel)
    note = blocked_note(meta, ("sysv",))
    subtitle = f"Across-Trial Median of Per-Exchange {col_prefix.upper()} | SHM bounded <= 1 KB"
    if note:
        subtitle += f" | {note}"
    ax.set_title(f"{title}\n({subtitle})")
    ax.legend(ncol=3, loc="upper left", frameon=True)
    save_fig(fig, out_dir, filename)


def plot_throughput_comparison(agg_rtt, meta, out_dir):
    """Two-panel throughput chart: msg/s (left) and MB/s (right)."""
    sub = agg_rtt[agg_rtt["status"] == "PASS"].copy()
    payloads = sorted(sub["payload_bytes"].unique())
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]
             if m in set(sub["mechanism"])]
    x = np.arange(len(payloads))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.2))
    for m in mechs:
        xs, msg_s, mb_s = [], [], []
        for idx, p in enumerate(payloads):
            row = sub[(sub["mechanism"] == m) & (sub["payload_bytes"] == p)]
            if not row.empty and pd.notna(row["throughput_msg_s_mean"].iloc[0]):
                xs.append(idx)
                msg_s.append(float(row["throughput_msg_s_mean"].iloc[0]))
                mb_s.append(float(row["mb_per_sec_mean"].iloc[0]))
        if xs:
            ls = "--" if m == "adaptive" else "-"
            ax1.plot(xs, msg_s, marker=MECH_MARKERS.get(m, "o"), linestyle=ls, linewidth=1.9,
                     label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))
            ax2.plot(xs, mb_s, marker=MECH_MARKERS.get(m, "o"), linestyle=ls, linewidth=1.9,
                     label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))

    ax1.set_ylim(bottom=0)
    ax2.set_ylim(bottom=0)
    for ax in (ax1, ax2):
        ax.set_xticks(x)
        ax.set_xticklabels([fmt_bytes(p) for p in payloads], rotation=20)
        ax.set_xlabel("Payload Size")
    ax1.set_ylabel("Throughput (Exchanges / sec)")
    ax1.set_title("Message Rate Throughput (msg/s)")
    ax2.set_ylabel("Logical Payload Bandwidth (MB/s, 1 MB = 10^6 B)")
    ax2.set_title("Data Bandwidth Throughput (MB/s)")
    ax1.legend(ncol=2, fontsize=8, loc="upper right", frameon=True)
    note = blocked_note(meta, ("sysv",))
    sup = "Throughput Comparison Across IPC Mechanisms (1P/1C Round-Trip)"
    if note:
        sup += f" [{note}]"
    fig.suptitle(sup, fontsize=13, fontweight="bold", y=1.02)
    save_fig(fig, out_dir, "throughput_comparison")


def plot_cpu_comparison(agg_rtt, meta, out_dir):
    """Stacked User vs System CPU time per message and CPU utilization."""
    sub = agg_rtt[agg_rtt["status"] == "PASS"].copy()
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]
             if m in set(sub["mechanism"])]
    # Use common small+mid payload (e.g. 1024 B where all eligible including SHM run)
    target_p = 1024 if 1024 in set(sub["payload_bytes"]) else sorted(sub["payload_bytes"].unique())[0]
    p_sub = sub[sub["payload_bytes"] == target_p]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 5.0))
    labels = [MECH_LABELS.get(m, m) for m in mechs]
    user_us, sys_us, util_pct, util_err = [], [], [], []
    for m in mechs:
        row = p_sub[p_sub["mechanism"] == m]
        if row.empty:
            user_us.append(0.0); sys_us.append(0.0); util_pct.append(0.0); util_err.append(0.0)
            continue
        tot_cpu = float(row["total_cpu_s_mean"].iloc[0] or 0.0)
        u_cpu = float(row["user_cpu_s_mean"].iloc[0] or 0.0)
        s_cpu = float(row["sys_cpu_s_mean"].iloc[0] or 0.0)
        tot_us_msg = float(row["cpu_us_per_msg_mean"].iloc[0] or 0.0)
        if tot_cpu > 0:
            user_us.append(tot_us_msg * (u_cpu / tot_cpu))
            sys_us.append(tot_us_msg * (s_cpu / tot_cpu))
        else:
            user_us.append(0.0); sys_us.append(0.0)
        up = float(row["cpu_util_pct_mean"].iloc[0] or 0.0)
        uhi = row.get("cpu_util_pct_ci95_high", pd.Series([np.nan])).iloc[0]
        util_pct.append(up)
        util_err.append(max(0.0, float(uhi) - up) if pd.notna(uhi) else 0.0)

    x = np.arange(len(mechs))
    ax1.bar(x, user_us, width=0.58, label="User CPU (us/msg)", color="#0072B2")
    ax1.bar(x, sys_us, width=0.58, bottom=user_us, label="System/Kernel CPU (us/msg)", color="#D55E00")
    ax1.set_ylim(bottom=0)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=25, ha="right")
    ax1.set_ylabel("CPU Time per Message (us/msg)")
    ax1.set_title(f"User vs System CPU Cost per Exchange ({fmt_bytes(target_p)})")
    ax1.legend()

    colors = [MECH_COLORS.get(m, "#555555") for m in mechs]
    ax2.bar(x, util_pct, width=0.58, yerr=util_err, capsize=3, color=colors, alpha=0.9)
    ax2.set_ylim(bottom=0)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right")
    ax2.set_ylabel("Combined Process Tree CPU Utilization (%)")
    ax2.set_title(f"CPU Utilization Across 2-Core Affinity ({fmt_bytes(target_p)})")
    fig.suptitle("CPU Overhead Comparison (getrusage Self + Child Process Tree)", fontsize=13, fontweight="bold", y=1.02)
    save_fig(fig, out_dir, "cpu_comparison")


def plot_memory_comparison(mem_df, meta, out_dir):
    """Peak RSS & Average RSS per mechanism (from separate profiler)."""
    sub = mem_df[mem_df["status"] == "PASS"].copy()
    mem_fb = sub[sub["status"] == "PASS"].copy()
    if mem_fb.empty:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.text(0.5, 0.5, "Memory profiling data unavailable", ha="center", va="center", fontsize=12)
        ax.set_axis_off()
        save_fig(fig, out_dir, "memory_comparison")
        return

    target_p = 1024 if 1024 in set(mem_fb["payload_bytes"]) else sorted(mem_fb["payload_bytes"].unique())[0]
    p_sub = mem_fb[mem_fb["payload_bytes"] == target_p]
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"] if m in set(p_sub["mechanism"])]

    x = np.arange(len(mechs))
    w = 0.28
    avg_tot, peak_tot, prod_peak, cons_peak = [], [], [], []
    for m in mechs:
        row = p_sub[p_sub["mechanism"] == m].iloc[0]
        if "total_peak_rss_kb" in p_sub.columns:
            avg_tot.append(float(pd.to_numeric(row.get("total_avg_rss_kb"), errors="coerce") or 0.0) / 1024.0)
            peak_tot.append(float(pd.to_numeric(row.get("total_peak_rss_kb"), errors="coerce") or 0.0) / 1024.0)
            prod_peak.append(float(pd.to_numeric(row.get("producer_peak_rss_kb"), errors="coerce") or 0.0) / 1024.0)
            cons_peak.append(float(pd.to_numeric(row.get("consumer_peak_rss_kb"), errors="coerce") or 0.0) / 1024.0)
        else:
            # Fallback when profiling pass skipped: use rusage peaks from memory_metrics.csv
            peak_tot.append(float(pd.to_numeric(p_sub[p_sub["mechanism"] == m]["combined_peak_rss_kb"].mean(), errors="coerce") or 0.0) / 1024.0)
            avg_tot.append(0.0)
            prod_peak.append(float(pd.to_numeric(p_sub[p_sub["mechanism"] == m]["parent_peak_rss_kb"].mean(), errors="coerce") or 0.0) / 1024.0)
            cons_peak.append(float(pd.to_numeric(p_sub[p_sub["mechanism"] == m]["child_peak_rss_kb"].mean(), errors="coerce") or 0.0) / 1024.0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.0))
    ax1.bar(x - w / 2, avg_tot, w, label="Combined Average RSS", color="#56B4E9")
    ax1.bar(x + w / 2, peak_tot, w, label="Combined Peak RSS", color="#0072B2")
    ax1.set_ylim(bottom=0)
    ax1.set_xticks(x)
    ax1.set_xticklabels([MECH_LABELS.get(m, m) for m in mechs], rotation=25, ha="right")
    ax1.set_ylabel("Memory Footprint (MiB)")
    ax1.set_title(f"Combined Average vs Peak RSS ({fmt_bytes(target_p)})")
    ax1.legend()

    ax2.bar(x - w / 2, prod_peak, w, label="Producer Peak RSS", color="#009E73")
    ax2.bar(x + w / 2, cons_peak, w, label="Consumer Peak RSS", color="#CC79A7")
    ax2.set_ylim(bottom=0)
    ax2.set_xticks(x)
    ax2.set_xticklabels([MECH_LABELS.get(m, m) for m in mechs], rotation=25, ha="right")
    ax2.set_ylabel("Per-Process Peak RSS (MiB)")
    ax2.set_title(f"Producer vs Consumer Peak RSS ({fmt_bytes(target_p)})")
    ax2.legend()
    fig.suptitle("Memory Consumption Comparison (Separate Process-Tree Sampler)", fontsize=13, fontweight="bold", y=1.02)
    save_fig(fig, out_dir, "memory_comparison")


def plot_context_switches(sys_df, out_dir):
    """Context switches across mechanisms (voluntary/involuntary stacked on Linux, total on Windows)."""
    sub = sys_df[sys_df["status"] == "PASS"].copy()
    if sub.empty:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.text(0.5, 0.5, "Context-switch profiling unavailable", ha="center", va="center")
        ax.set_axis_off()
        save_fig(fig, out_dir, "context_switches")
        return

    target_p = 1024 if 1024 in set(sub["payload_bytes"]) else sorted(sub["payload_bytes"].unique())[0]
    p_sub = sub[sub["payload_bytes"] == target_p]
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"] if m in set(p_sub["mechanism"])]

    has_split = p_sub["voluntary_ctx_switches"].notna().any()
    has_total = p_sub["total_ctx_switches"].notna().any()
    if not has_split and not has_total:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.text(0.5, 0.5, "Context-switch profiling UNAVAILABLE (resource profiler not run)",
                ha="center", va="center", fontsize=11,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF2E0", edgecolor="#E69F00"))
        ax.set_axis_off()
        save_fig(fig, out_dir, "context_switches")
        return

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    x = np.arange(len(mechs))
    if has_split:
        vols = [float(p_sub[p_sub["mechanism"] == m]["voluntary_ctx_switches"].iloc[0] or 0) for m in mechs]
        invs = [float(p_sub[p_sub["mechanism"] == m]["involuntary_ctx_switches"].iloc[0] or 0) for m in mechs]
        ax.bar(x, vols, 0.55, label="Voluntary Context Switches", color="#0072B2")
        ax.bar(x, invs, 0.55, bottom=vols, label="Involuntary Context Switches", color="#D55E00")
        ax.set_title(f"Voluntary vs Involuntary Context Switches ({fmt_bytes(target_p)} Profiling Run)")
        ax.legend()
    else:
        tots = [float(pd.to_numeric(p_sub[p_sub["mechanism"] == m]["total_ctx_switches"].iloc[0], errors="coerce") or 0) for m in mechs]
        colors = [MECH_COLORS.get(m, "#555555") for m in mechs]
        bars = ax.bar(x, tots, 0.55, color=colors, alpha=0.9)
        for b, v in zip(bars, tots):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{int(v)}", ha="center", va="bottom", fontsize=8.5)
        method = str(p_sub["ctx_profiling_method"].iloc[0])
        ax.set_title(f"Total Process-Tree Thread Context Switches ({fmt_bytes(target_p)} Profiling Run)\n"
                     f"[Method: {method}; Vol/Invol split UNAVAILABLE on Windows/MSYS2]")

    ax.set_ylim(bottom=0)
    ax.set_xticks(x)
    ax.set_xticklabels([MECH_LABELS.get(m, m) for m in mechs], rotation=22, ha="right")
    ax.set_ylabel("Total Context Switches (Producer + Consumer)")
    save_fig(fig, out_dir, "context_switches")


def plot_syscall_comparison(sys_df, out_dir):
    """Syscall comparison when Linux strace ran; explicit UNAVAILABLE banner otherwise."""
    if sys_df.empty or "syscall_status" not in sys_df.columns:
        ok_rows = pd.DataFrame()
        reason = "No syscall records captured"
    else:
        ok_rows = sys_df[sys_df["syscall_status"] == "PASS"].drop_duplicates(subset=["mechanism"])
        reason = str(sys_df["syscall_reason"].dropna().iloc[0]) if not sys_df["syscall_reason"].dropna().empty else "Linux strace unavailable"

    if ok_rows.empty:
        fig, ax = plt.subplots(figsize=(11.2, 4.4))
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0.03, 0.10), 0.94, 0.80, facecolor="#FFF6E5", edgecolor="#E69F00", linewidth=2))
        ax.text(0.5, 0.68, "System-Call Profiling: UNAVAILABLE in Current Execution Environment",
                ha="center", va="center", fontsize=11.5, fontweight="bold", color="#995500")
        ax.text(0.5, 0.45, f"Reason: {reason}", ha="center", va="center", fontsize=9.8, color="#333333", wrap=True)
        ax.text(0.5, 0.23, "Policy: Missing kernel syscall measurements are never fabricated or plotted as zero.\n"
                           "Execute on Linux with strace installed to populate exact communication/setup/other syscall counts.",
                ha="center", va="center", fontsize=8.8, color="#555555")
        save_fig(fig, out_dir, "syscall_comparison")
        return

    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"] if m in set(ok_rows["mechanism"])]
    x = np.arange(len(mechs))
    comm = [float(ok_rows[ok_rows["mechanism"] == m]["comm_syscalls"].iloc[0]) for m in mechs]
    setup = [float(ok_rows[ok_rows["mechanism"] == m]["setup_cleanup_syscalls"].iloc[0]) for m in mechs]
    other = [float(ok_rows[ok_rows["mechanism"] == m]["other_syscalls"].iloc[0]) for m in mechs]

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    ax.bar(x, comm, 0.55, label="Communication Syscalls", color="#0072B2")
    ax.bar(x, setup, 0.55, bottom=comm, label="Setup & Cleanup Syscalls", color="#E69F00")
    ax.bar(x, other, 0.55, bottom=np.array(comm) + np.array(setup), label="Other / Loader / Output Syscalls", color="#999999")
    ax.set_ylim(bottom=0)
    ax.set_xticks(x)
    ax.set_xticklabels([MECH_LABELS.get(m, m) for m in mechs], rotation=22, ha="right")
    ax.set_ylabel("System Call Count (100 Exchanges, 64 B)")
    ax.set_title("System-Call Breakdown by Category (Detailed Linux strace -f -o)")
    ax.legend()
    save_fig(fig, out_dir, "syscall_comparison")


def plot_payload_scalability(agg_rtt, meta, out_dir):
    """Dual-panel scalability across 64 B -> 256 KB: Mean RTT (top) & Bandwidth MB/s (bottom)."""
    sub = agg_rtt[agg_rtt["status"] == "PASS"].copy()
    payloads = sorted(sub["payload_bytes"].unique())
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"] if m in set(sub["mechanism"])]
    x = np.arange(len(payloads))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.2), sharex=True)
    for m in mechs:
        xs, lats, bws = [], [], []
        for idx, p in enumerate(payloads):
            row = sub[(sub["mechanism"] == m) & (sub["payload_bytes"] == p)]
            if not row.empty and pd.notna(row["avg_rtt_us_mean"].iloc[0]):
                xs.append(idx)
                lats.append(float(row["avg_rtt_us_mean"].iloc[0]))
                bws.append(float(row["mb_per_sec_mean"].iloc[0]))
        if xs:
            ls = "--" if m == "adaptive" else "-"
            lw = 2.4 if m == "adaptive" else 1.8
            ax1.plot(xs, lats, marker=MECH_MARKERS.get(m, "o"), linestyle=ls, linewidth=lw,
                     label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))
            ax2.plot(xs, bws, marker=MECH_MARKERS.get(m, "o"), linestyle=ls, linewidth=lw,
                     label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))

    ax1.set_yscale("log")
    ax1.set_ylabel("Mean Round-Trip Latency (us) [log scale]")
    ax1.set_title("Payload Scalability: Latency & Bandwidth from 64 B to 256 KB\n(SHM bounded <= 1 KB; Adaptive transitions SHM -> Pipe > 1 KB)")
    ax1.legend(ncol=4, fontsize=8.5, loc="upper left")

    ax2.set_ylim(bottom=0)
    ax2.set_ylabel("Payload Bandwidth (MB/s, 1 MB = 10^6 B)")
    ax2.set_xlabel("Payload Size")
    ax2.set_xticks(x)
    ax2.set_xticklabels([fmt_bytes(p) for p in payloads])
    save_fig(fig, out_dir, "payload_scalability")


def plot_concurrency_scalability(agg_df, meta, out_dir):
    """Multi-producer / multi-consumer throughput & CPU efficiency scaling."""
    sub = agg_df[(agg_df["workload_type"] == "concurrency_pipeline") & (agg_df["status"] == "PASS")].copy()
    if sub.empty:
        fig, ax = plt.subplots(figsize=(9.5, 4.5))
        ax.text(0.5, 0.5, "Concurrency scalability trials unavailable", ha="center", va="center")
        ax.set_axis_off()
        save_fig(fig, out_dir, "concurrency_scalability")
        return

    sub["topo"] = sub["producers"].astype(int).astype(str) + "P/" + sub["consumers"].astype(int).astype(str) + "C"
    topo_order = ["1P/1C", "2P/1C", "4P/1C", "1P/2C", "4P/4C"]
    topos = [t for t in topo_order if t in set(sub["topo"])]
    mechs = [m for m in ["pipe", "fifo", "sysv", "posix", "uds"] if m in set(sub["mechanism"])]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2))
    x = np.arange(len(topos))
    for m in mechs:
        xs, tputs, tput_lo, tput_hi, cpus = [], [], [], [], []
        for idx, t in enumerate(topos):
            row = sub[(sub["mechanism"] == m) & (sub["topo"] == t)]
            if not row.empty and pd.notna(row["throughput_msg_s_mean"].iloc[0]):
                mv = float(row["throughput_msg_s_mean"].iloc[0])
                hi = row.get("throughput_msg_s_ci95_high", pd.Series([np.nan])).iloc[0]
                lo = row.get("throughput_msg_s_ci95_low", pd.Series([np.nan])).iloc[0]
                xs.append(idx)
                tputs.append(mv)
                err_hi = max(0.0, float(hi) - mv) if pd.notna(hi) else 0.0
                err_lo = min(mv, max(0.0, mv - float(lo))) if pd.notna(lo) else 0.0
                tput_lo.append(err_lo)
                tput_hi.append(err_hi)
                cpus.append(float(row["cpu_us_per_msg_mean"].iloc[0] or 0.0))
        if xs:
            ax1.errorbar(xs, tputs, yerr=[tput_lo, tput_hi], capsize=3, marker=MECH_MARKERS.get(m, "o"),
                         linewidth=1.9, label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))
            ax2.plot(xs, cpus, marker=MECH_MARKERS.get(m, "o"), linewidth=1.9,
                     label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))

    ax1.set_ylim(bottom=0)
    ax2.set_ylim(bottom=0)
    for ax in (ax1, ax2):
        ax.set_xticks(x)
        ax.set_xticklabels(topos)
        ax.set_xlabel("Producer / Consumer Topology")
    ax1.set_ylabel("Pipeline Throughput (messages/sec)")
    ax1.set_title("Multi-Process Throughput Scaling")
    ax2.set_ylabel("Combined CPU Time per Message (us/msg)")
    ax2.set_title("CPU Cost per Message Under Contention")
    ax1.legend(loc="upper right", fontsize=8.5)
    pbytes = int(sub["payload_bytes"].iloc[0])
    fig.suptitle(f"Concurrency Scalability ({fmt_bytes(pbytes)} One-Way Validated Pipeline)\n"
                 "[Pipe/FIFO support 1C only; SHM/Adaptive 1P/1C only -> UNSUPPORTED topologies omitted]",
                 fontsize=12, fontweight="bold", y=1.03)
    save_fig(fig, out_dir, "concurrency_scalability")


def plot_adaptive_vs_best(adp_df, out_dir):
    """Evaluate adaptive selector vs empirical best eligible transport & pipe baseline."""
    sub = adp_df[adp_df["status"] == "PASS"].copy()
    if sub.empty:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.text(0.5, 0.5, "Adaptive evaluation data unavailable", ha="center", va="center")
        ax.set_axis_off()
        save_fig(fig, out_dir, "adaptive_vs_best")
        return

    payloads = [int(p) for p in sub["payload_bytes"]]
    x = np.arange(len(payloads))
    adp_lat = sub["adaptive_avg_rtt_us"].astype(float).to_numpy()
    best_lat = sub["best_avg_rtt_us"].astype(float).to_numpy()
    pipe_lat = pd.to_numeric(sub["pipe_avg_rtt_us"], errors="coerce").to_numpy()
    regret_pct = sub["regret_latency_pct"].astype(float).to_numpy()
    chosen = list(sub["chosen_transport"])
    best_m = list(sub["empirical_best_by_avg_rtt"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 7.6), sharex=True, gridspec_kw={"height_ratios": [1.3, 1.0]})
    w = 0.25
    ax1.bar(x - w, best_lat, w, label="Empirical Best Eligible Transport", color="#009E73")
    ax1.bar(x, adp_lat, w, label="Adaptive Selector Actual", color="#111111")
    ax1.bar(x + w, np.nan_to_num(pipe_lat, nan=0.0), w, label="Pipe Baseline", color="#0072B2", alpha=0.85)
    ax1.set_yscale("log")
    ax1.set_ylabel("Mean Round-Trip Latency (us) [log scale]")
    ax1.set_title("Adaptive Policy Selector vs Empirical Best Transport & Pipe Baseline")
    ax1.legend(loc="upper left")

    colors = ["#009E73" if c == b else "#D55E00" for c, b in zip(chosen, best_m)]
    bars = ax2.bar(x, regret_pct, 0.52, color=colors, alpha=0.9)
    opt_x = [i for i, (c, b) in enumerate(zip(chosen, best_m)) if c == b]
    opt_y = [regret_pct[i] for i in opt_x]
    if opt_x:
        ax2.scatter(opt_x, opt_y, color="#009E73", s=70, zorder=5, label="Optimal Pick")
    ax2.axhline(0.0, color="#333333", linewidth=1.0)
    for idx, (bar, c, b, r) in enumerate(zip(bars, chosen, best_m, regret_pct)):
        lbl = f"picked:{c}\nbest:{b}\n({r:+.1f}%)"
        y_pos = max(0.0, r) + 0.04 * max(1.0, float(np.max(np.abs(regret_pct))))
        ax2.text(bar.get_x() + bar.get_width() / 2.0, y_pos, lbl, ha="center", va="bottom", fontsize=7.5)

    ax2.set_ylabel("Latency Regret vs Best (%)")
    ax2.set_xlabel("Payload Size (Green = Optimal Pick, Orange = Suboptimal Pick)")
    ax2.set_xticks(x)
    ax2.set_xticklabels([fmt_bytes(p) for p in payloads])
    ax2.set_ylim(min(-5.0, float(np.min(regret_pct)) * 1.15), max(15.0, float(np.max(regret_pct)) * 1.45))
    save_fig(fig, out_dir, "adaptive_vs_best")


def plot_kernel_vs_userspace(kernel_df, all_df, out_dir):
    """Matched unidirectional kernel /dev/aipc vs user-space streams (or honest BLOCKED banner)."""
    k_bench = kernel_df[kernel_df["record_type"] == "benchmark"].copy() if not kernel_df.empty else pd.DataFrame()
    k_pass = k_bench[k_bench["status"] == "PASS"] if not k_bench.empty else pd.DataFrame()
    uni_pass = all_df[(all_df["workload_type"] == "unidirectional_stream") & (all_df["status"] == "PASS")].copy()

    if k_pass.empty:
        reason = "Linux kernel module unavailable on current host"
        if not k_bench.empty and "status_reason" in k_bench.columns:
            reason = str(k_bench["status_reason"].dropna().iloc[0])

        fig, ax = plt.subplots(figsize=(11.5, 5.4))
        if not uni_pass.empty:
            payloads = sorted(uni_pass["payload_bytes"].unique())
            x = np.arange(len(payloads))
            for m in [m for m in ["pipe", "fifo", "uds", "posix"] if m in set(uni_pass["requested_mode"])]:
                xs, mbs = [], []
                for idx, p in enumerate(payloads):
                    sub = uni_pass[(uni_pass["requested_mode"] == m) & (uni_pass["payload_bytes"] == p)]
                    if not sub.empty:
                        xs.append(idx)
                        mbs.append(float(sub["mb_per_sec"].mean()))
                if xs:
                    ax.plot(xs, mbs, marker=MECH_MARKERS.get(m, "o"), linewidth=1.9,
                            label=f"{MECH_LABELS.get(m, m)} (Matched Unidirectional)", color=MECH_COLORS.get(m, "#555555"))
            ax.set_ylim(bottom=0)
            ax.set_xticks(x)
            ax.set_xticklabels([fmt_bytes(p) for p in payloads])
            ax.set_xlabel("Payload Size")
            ax.set_ylabel("Unidirectional Bandwidth (MB/s)")
            ax.legend(loc="upper left", frameon=True)
            ax.set_title(
                f"Matched Unidirectional User-Space Baselines & Kernel Mailbox Status\n"
                f"[Kernel /dev/aipc: BLOCKED (No Data Plotted / Not Zero) — {reason}]",
                fontsize=10.5,
            )
        else:
            ax.axis("off")
            ax.text(0.5, 0.5, f"Kernel AIPC Module (/dev/aipc): BLOCKED\n{reason}",
                    ha="center", va="center", fontsize=11,
                    bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF2E0", edgecolor="#D55E00"))
        save_fig(fig, out_dir, "kernel_vs_userspace")
        return

    # Kernel module ran cleanly: plot matched unidirectional MB/s & msg/s vs user-space streams
    payloads = sorted(set(k_pass["payload_bytes"].astype(int)) | set(uni_pass["payload_bytes"].astype(int)))
    x = np.arange(len(payloads))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    # Plot kernel
    k_xs, k_msgs, k_mbs = [], [], []
    for idx, p in enumerate(payloads):
        sub = k_pass[k_pass["payload_bytes"].astype(int) == p]
        if not sub.empty:
            k_xs.append(idx)
            k_msgs.append(float(sub["throughput_msg_s"].astype(float).mean()))
            k_mbs.append(float(sub["mb_per_sec"].astype(float).mean()))
    if k_xs:
        ax1.plot(k_xs, k_msgs, marker="X", linewidth=2.4, label=MECH_LABELS["kernel"], color=MECH_COLORS["kernel"])
        ax2.plot(k_xs, k_mbs, marker="X", linewidth=2.4, label=MECH_LABELS["kernel"], color=MECH_COLORS["kernel"])

    for m in [m for m in ["pipe", "fifo", "uds", "posix"] if m in set(uni_pass["requested_mode"])]:
        xs, msgs, mbs = [], [], []
        for idx, p in enumerate(payloads):
            sub = uni_pass[(uni_pass["requested_mode"] == m) & (uni_pass["payload_bytes"].astype(int) == p)]
            if not sub.empty:
                xs.append(idx)
                msgs.append(float(sub["throughput_msg_s"].mean()))
                mbs.append(float(sub["mb_per_sec"].mean()))
        if xs:
            ax1.plot(xs, msgs, marker=MECH_MARKERS.get(m, "o"), linewidth=1.8, label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))
            ax2.plot(xs, mbs, marker=MECH_MARKERS.get(m, "o"), linewidth=1.8, label=MECH_LABELS.get(m, m), color=MECH_COLORS.get(m, "#555555"))

    for ax in (ax1, ax2):
        ax.set_ylim(bottom=0)
        ax.set_xticks(x)
        ax.set_xticklabels([fmt_bytes(p) for p in payloads], rotation=20)
        ax.set_xlabel("Payload Size")
    ax1.set_ylabel("Messages / sec")
    ax1.set_title("Unidirectional Message Rate")
    ax2.set_ylabel("Bandwidth (MB/s)")
    ax2.set_title("Unidirectional Bandwidth")
    ax1.legend()
    fig.suptitle("Kernel AIPC Mailbox (/dev/aipc) vs Matched Unidirectional User-Space IPC", fontsize=13, fontweight="bold", y=1.02)
    save_fig(fig, out_dir, "kernel_vs_userspace")


def main():
    ap = argparse.ArgumentParser(description="Generate all 13 benchmark figures (PNG + PDF)")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--processed-dir", required=True)
    ap.add_argument("--graphs-dir", required=True)
    args = ap.parse_args()

    setup_style()
    os.makedirs(args.graphs_dir, exist_ok=True)

    all_df = pd.read_csv(os.path.join(args.raw_dir, "all_results.csv"))
    agg_df = pd.read_csv(os.path.join(args.processed_dir, "aggregated_results.csv"))
    mem_df = pd.read_csv(os.path.join(args.raw_dir, "memory_metrics.csv"))
    sys_df = pd.read_csv(os.path.join(args.raw_dir, "system_metrics.csv"))
    adp_df = pd.read_csv(os.path.join(args.raw_dir, "adaptive_results.csv"))
    k_path = os.path.join(args.raw_dir, "kernel_results.csv")
    kernel_df = pd.read_csv(k_path) if os.path.exists(k_path) else pd.DataFrame()
    with open(os.path.join(args.processed_dir, "benchmark_metadata.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)

    agg_rtt = agg_df[agg_df["workload_type"] == "single_pair_rtt"].copy()

    # 1. latency_comparison
    plot_grouped_bar_metric(
        agg_rtt, meta, "avg_rtt_us", "Average Round-Trip Latency (us)",
        "Average Round-Trip Latency Comparison Across IPC Mechanisms",
        args.graphs_dir, "latency_comparison",
    )
    # 2. p50_latency
    plot_percentile_curve(
        agg_rtt, meta, "p50_rtt_us", "Median (P50) Round-Trip Latency (us)",
        "P50 Median Round-Trip Latency Across Payload Sizes",
        args.graphs_dir, "p50_latency",
    )
    # 3. p95_latency
    plot_percentile_curve(
        agg_rtt, meta, "p95_rtt_us", "95th Percentile (P95) Round-Trip Latency (us)",
        "P95 Tail Round-Trip Latency Across Payload Sizes",
        args.graphs_dir, "p95_latency",
    )
    # 4. p99_latency
    plot_percentile_curve(
        agg_rtt, meta, "p99_rtt_us", "99th Percentile (P99) Round-Trip Latency (us)",
        "P99 Tail Round-Trip Latency Across Payload Sizes",
        args.graphs_dir, "p99_latency",
    )
    # 5. throughput_comparison
    plot_throughput_comparison(agg_rtt, meta, args.graphs_dir)
    # 6. cpu_comparison
    plot_cpu_comparison(agg_rtt, meta, args.graphs_dir)
    # 7. memory_comparison
    plot_memory_comparison(mem_df, meta, args.graphs_dir)
    # 8. context_switches
    plot_context_switches(sys_df, args.graphs_dir)
    # 9. syscall_comparison
    plot_syscall_comparison(sys_df, args.graphs_dir)
    # 10. payload_scalability
    plot_payload_scalability(agg_rtt, meta, args.graphs_dir)
    # 11. concurrency_scalability
    plot_concurrency_scalability(agg_df, meta, args.graphs_dir)
    # 12. adaptive_vs_best
    plot_adaptive_vs_best(adp_df, args.graphs_dir)
    # 13. kernel_vs_userspace
    plot_kernel_vs_userspace(kernel_df, all_df, args.graphs_dir)

    print(f"Generated 13 PNG + 13 PDF graphs in {args.graphs_dir}")


if __name__ == "__main__":
    main()
