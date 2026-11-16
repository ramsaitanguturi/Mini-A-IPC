#!/usr/bin/env python3
"""Statistical processing, aggregation, and validation for Mini A-IPC unified benchmarks."""
import argparse
import csv
import datetime
import json
import math
import os
import platform
import sys

import numpy as np
import pandas as pd

try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    scipy_stats = None
    HAS_SCIPY = False


# ---------------------------------------------------------------------------
# Exact pure-Python / math statistical primitives (used when scipy absent)
# ---------------------------------------------------------------------------
def _betacf(a, b, x):
    """Continued fraction for incomplete beta function (Numerical Recipes)."""
    MAXIT = 200
    EPS = 3.0e-12
    FPMIN = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_two_tailed_p(t_abs, df):
    """Exact two-tailed p-value for Student's t distribution."""
    if df <= 0 or math.isnan(t_abs):
        return float("nan")
    if math.isinf(t_abs):
        return 0.0
    x = df / (df + t_abs * t_abs)
    return min(1.0, max(0.0, betainc(0.5 * df, 0.5, x)))


def student_t_crit_95(df):
    """Exact two-sided 95% Student's t critical value (alpha=0.05) via bisection."""
    if HAS_SCIPY:
        return float(scipy_stats.t.ppf(0.975, df))
    if df <= 0:
        return float("nan")
    lo, hi = 0.0, 200.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if student_t_two_tailed_p(mid, df) > 0.05:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def paired_t_test(a, b):
    """Paired two-sided t-test on matched samples a, b."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    n = len(a)
    if n < 2:
        return float("nan"), float("nan"), float("nan"), float("nan")
    diffs = a - b
    mean_d = float(np.mean(diffs))
    sd_d = float(np.std(diffs, ddof=1))
    se_d = sd_d / math.sqrt(n)
    tcrit = student_t_crit_95(n - 1)
    ci_lo = mean_d - tcrit * se_d
    ci_hi = mean_d + tcrit * se_d
    if sd_d == 0.0:
        if mean_d == 0.0:
            return 0.0, 1.0, ci_lo, ci_hi
        return float("inf") if mean_d > 0 else float("-inf"), 0.0, ci_lo, ci_hi
    t_stat = mean_d / se_d
    if HAS_SCIPY:
        res = scipy_stats.ttest_rel(a, b)
        return float(res.statistic), float(res.pvalue), ci_lo, ci_hi
    p_val = student_t_two_tailed_p(abs(t_stat), n - 1)
    return t_stat, p_val, ci_lo, ci_hi


def wilcoxon_signed_rank(a, b):
    """Two-sided Wilcoxon signed-rank test (exact enumeration for n<=20 without ties)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    diffs = (a - b)[mask]
    nz = diffs[diffs != 0.0]
    n = len(nz)
    if n == 0:
        return 0.0, 1.0
    if HAS_SCIPY and n >= 1:
        try:
            res = scipy_stats.wilcoxon(nz, method="auto")
            return float(res.statistic), float(res.pvalue)
        except Exception:
            pass
    abs_d = np.abs(nz)
    order = np.argsort(abs_d)
    ranks = np.empty(n, dtype=float)
    i = 0
    has_ties = False
    while i < n:
        j = i
        while j + 1 < n and abs_d[order[j + 1]] == abs_d[order[i]]:
            j += 1
        if j > i:
            has_ties = True
        avg_rank = 0.5 * ((i + 1) + (j + 1))
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    w_pos = float(np.sum(ranks[nz > 0.0]))
    w_neg = float(np.sum(ranks[nz < 0.0]))
    w_stat = min(w_pos, w_neg)

    if not has_ties and n <= 20:
        # Exact two-sided distribution over all 2^n sign assignments
        max_sum = n * (n + 1) // 2
        dp = [0] * (max_sum + 1)
        dp[0] = 1
        for r in range(1, n + 1):
            for s in range(max_sum, r - 1, -1):
                dp[s] += dp[s - r]
        target = int(round(w_stat))
        tail = sum(dp[0 : target + 1])
        total = 1 << n
        p_val = min(1.0, 2.0 * tail / total)
        return w_stat, p_val

    if n <= 16:
        # Exact enumeration even when ties exist (2^n <= 65536)
        tot_rank_sum = float(np.sum(ranks))
        extreme = 0
        total = 1 << n
        for mask in range(total):
            wp_m = 0.0
            for idx_b in range(n):
                if mask & (1 << idx_b):
                    wp_m += ranks[idx_b]
            w_m = min(wp_m, tot_rank_sum - wp_m)
            if w_m <= w_stat + 1e-12:
                extreme += 1
        return w_stat, min(1.0, extreme / total)

    # Normal approximation with continuity correction for larger n or ties
    mean_w = n * (n + 1) / 4.0
    var_w = n * (n + 1) * (2 * n + 1) / 24.0
    if var_w <= 0:
        return w_stat, 1.0
    z = (abs(w_stat - mean_w) - 0.5) / math.sqrt(var_w)
    z = max(0.0, z)
    p_val = math.erfc(z / math.sqrt(2.0))
    return w_stat, min(1.0, max(0.0, p_val))


def summarize_series(vals):
    """Return summary dict with mean, median, std, 95% t-CI, min, max, iqr."""
    s = pd.to_numeric(vals, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(s)
    if n == 0:
        return {
            "mean": np.nan, "median": np.nan, "std": np.nan,
            "ci95_low": np.nan, "ci95_high": np.nan,
            "min": np.nan, "max": np.nan, "iqr": np.nan,
        }
    mean_v = float(np.mean(s))
    med_v = float(np.median(s))
    min_v = float(np.min(s))
    max_v = float(np.max(s))
    q75, q25 = np.percentile(s, [75, 25])
    iqr_v = float(q75 - q25)
    if n >= 2:
        std_v = float(np.std(s, ddof=1))
        se = std_v / math.sqrt(n)
        tcrit = student_t_crit_95(n - 1)
        ci_lo = mean_v - tcrit * se
        ci_hi = mean_v + tcrit * se
    else:
        std_v = np.nan
        ci_lo = np.nan
        ci_hi = np.nan
    return {
        "mean": mean_v, "median": med_v, "std": std_v,
        "ci95_low": ci_lo, "ci95_high": ci_hi,
        "min": min_v, "max": max_v, "iqr": iqr_v,
    }


def _safe_float(v):
    try:
        if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="Analyze unified IPC benchmark results")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--processed-dir", required=True)
    ap.add_argument("--meta-in", required=True)
    ap.add_argument("--profile-tmp", required=False, default="")
    ap.add_argument("--syscalls-tmp", required=False, default="")
    args = ap.parse_args()

    os.makedirs(args.raw_dir, exist_ok=True)
    os.makedirs(args.processed_dir, exist_ok=True)

    all_path = os.path.join(args.raw_dir, "all_results.csv")
    if not os.path.exists(all_path):
        sys.exit(f"ERROR: missing {all_path}")

    df = pd.read_csv(all_path)
    with open(args.meta_in, "r", encoding="utf-8") as f:
        meta = json.load(f)
    exp_id = meta.get("experiment_id", "unknown")

    # 1. Split raw projection CSVs (never fabricating zeros)
    latency_cols = [
        "experiment_id", "timestamp_utc", "workload_type", "latency_semantics",
        "requested_mode", "selected_transport", "payload_bytes", "trial",
        "completed_messages", "status", "status_reason", "avg_rtt_us",
        "stddev_rtt_us", "min_rtt_us", "p50_rtt_us", "p90_rtt_us",
        "p95_rtt_us", "p99_rtt_us", "p999_rtt_us", "max_rtt_us",
    ]
    df_lat = df[[c for c in latency_cols if c in df.columns]].copy()
    df_lat.rename(columns={"requested_mode": "mechanism"}, inplace=True)
    df_lat.to_csv(os.path.join(args.raw_dir, "latency.csv"), index=False)

    tput_cols = [
        "experiment_id", "timestamp_utc", "workload_type", "requested_mode",
        "selected_transport", "payload_bytes", "producers", "consumers", "trial",
        "completed_messages", "status", "status_reason", "duration_s",
        "throughput_msg_s", "bytes_per_sec", "mb_per_sec", "wire_mb_per_sec",
    ]
    df_tput = df[[c for c in tput_cols if c in df.columns]].copy()
    df_tput.rename(columns={"requested_mode": "mechanism"}, inplace=True)
    df_tput.to_csv(os.path.join(args.raw_dir, "throughput.csv"), index=False)

    cpu_cols = [
        "experiment_id", "timestamp_utc", "workload_type", "requested_mode",
        "selected_transport", "payload_bytes", "producers", "consumers", "trial",
        "completed_messages", "status", "user_cpu_s", "sys_cpu_s",
        "total_cpu_s", "cpu_util_pct", "cpu_us_per_msg",
    ]
    df_cpu = df[[c for c in cpu_cols if c in df.columns]].copy()
    df_cpu.rename(columns={"requested_mode": "mechanism"}, inplace=True)
    df_cpu.to_csv(os.path.join(args.raw_dir, "cpu_metrics.csv"), index=False)

    # 2. Memory & System metrics (combine rusage + separate profiler + syscalls)
    prof_df = pd.read_csv(args.profile_tmp) if (args.profile_tmp and os.path.exists(args.profile_tmp)) else pd.DataFrame()
    sys_df = pd.read_csv(args.syscalls_tmp) if (args.syscalls_tmp and os.path.exists(args.syscalls_tmp)) else pd.DataFrame()

    if not prof_df.empty:
        mem_cols = [
            "experiment_id", "mechanism", "selected_transport", "payload_bytes",
            "profile_messages", "status", "status_reason", "producer_avg_rss_kb",
            "consumer_avg_rss_kb", "total_avg_rss_kb", "producer_peak_rss_kb",
            "consumer_peak_rss_kb", "total_peak_rss_kb", "rss_samples",
            "kernel_mem_total_kb", "kernel_mem_available_kb", "kernel_slab_kb",
            "profiling_method",
        ]
        prof_df[[c for c in mem_cols if c in prof_df.columns]].to_csv(
            os.path.join(args.raw_dir, "memory_metrics.csv"), index=False
        )
    else:
        mem_fb = df[["experiment_id", "requested_mode", "selected_transport", "payload_bytes",
                     "status", "status_reason", "parent_peak_rss_kb", "child_peak_rss_kb",
                     "combined_peak_rss_kb"]].copy()
        mem_fb.rename(columns={"requested_mode": "mechanism"}, inplace=True)
        mem_fb.to_csv(os.path.join(args.raw_dir, "memory_metrics.csv"), index=False)

    # Build unified system_metrics.csv (always with explicit headers)
    sys_cols_out = [
        "experiment_id", "mechanism", "selected_transport", "payload_bytes",
        "status", "status_reason", "total_ctx_switches", "voluntary_ctx_switches",
        "involuntary_ctx_switches", "minor_page_faults", "major_page_faults",
        "ctx_profiling_method", "syscall_status", "syscall_reason",
        "total_syscalls", "total_syscalls_per_exchange", "comm_syscalls",
        "comm_syscalls_per_exchange", "setup_cleanup_syscalls", "other_syscalls",
        "classification", "relevant_syscall_details",
    ]
    sys_rows = []
    if not prof_df.empty:
        for _, r in prof_df.iterrows():
            sc_match = sys_df[sys_df["mechanism"] == r["mechanism"]] if not sys_df.empty else pd.DataFrame()
            sc_row = sc_match.iloc[0] if not sc_match.empty else None
            sys_rows.append({
                "experiment_id": exp_id,
                "mechanism": r["mechanism"],
                "selected_transport": r["selected_transport"],
                "payload_bytes": r["payload_bytes"],
                "status": r["status"],
                "status_reason": r["status_reason"],
                "total_ctx_switches": r.get("total_ctx_switches", ""),
                "voluntary_ctx_switches": r.get("voluntary_ctx_switches", ""),
                "involuntary_ctx_switches": r.get("involuntary_ctx_switches", ""),
                "minor_page_faults": r.get("minor_page_faults", ""),
                "major_page_faults": r.get("major_page_faults", ""),
                "ctx_profiling_method": r.get("profiling_method", ""),
                "syscall_status": sc_row["status"] if sc_row is not None else "UNAVAILABLE",
                "syscall_reason": sc_row["status_reason"] if sc_row is not None else "Syscall profiling did not execute",
                "total_syscalls": sc_row["total_syscalls"] if sc_row is not None else "",
                "total_syscalls_per_exchange": sc_row["total_syscalls_per_exchange"] if sc_row is not None else "",
                "comm_syscalls": sc_row["comm_syscalls"] if sc_row is not None else "",
                "comm_syscalls_per_exchange": sc_row["comm_syscalls_per_exchange"] if sc_row is not None else "",
                "setup_cleanup_syscalls": sc_row["setup_cleanup_syscalls"] if sc_row is not None else "",
                "other_syscalls": sc_row["other_syscalls"] if sc_row is not None else "",
                "classification": sc_row["classification"] if sc_row is not None else "unavailable",
                "relevant_syscall_details": sc_row["relevant_syscall_details"] if sc_row is not None else "",
            })
    else:
        for (m, p), grp in df[df["workload_type"] == "single_pair_rtt"].groupby(["requested_mode", "payload_bytes"]):
            pg = grp[grp["status"] == "PASS"]
            st = "PASS" if not pg.empty else str(grp["status"].iloc[0])
            sys_rows.append({
                "experiment_id": exp_id,
                "mechanism": m,
                "selected_transport": grp["selected_transport"].iloc[0],
                "payload_bytes": int(p),
                "status": st,
                "status_reason": grp["status_reason"].iloc[0],
                "total_ctx_switches": "",
                "voluntary_ctx_switches": round(float(pg["voluntary_ctx_switches"].mean()), 1) if (not pg.empty and pg["voluntary_ctx_switches"].notna().any()) else "",
                "involuntary_ctx_switches": round(float(pg["involuntary_ctx_switches"].mean()), 1) if (not pg.empty and pg["involuntary_ctx_switches"].notna().any()) else "",
                "minor_page_faults": round(float(pg["minor_page_faults"].mean()), 1) if (not pg.empty and pg["minor_page_faults"].notna().any()) else "",
                "major_page_faults": round(float(pg["major_page_faults"].mean()), 1) if (not pg.empty and pg["major_page_faults"].notna().any()) else "",
                "ctx_profiling_method": "rusage_only",
                "syscall_status": "UNAVAILABLE",
                "syscall_reason": "Separate profiling pass skipped",
                "total_syscalls": "",
                "total_syscalls_per_exchange": "",
                "comm_syscalls": "",
                "comm_syscalls_per_exchange": "",
                "setup_cleanup_syscalls": "",
                "other_syscalls": "",
                "classification": "unavailable",
                "relevant_syscall_details": "",
            })
    pd.DataFrame(sys_rows, columns=sys_cols_out).to_csv(os.path.join(args.raw_dir, "system_metrics.csv"), index=False)

    # 3. Aggregated results across all configurations
    metrics_to_agg = [
        "avg_rtt_us", "stddev_rtt_us", "min_rtt_us", "p50_rtt_us", "p90_rtt_us",
        "p95_rtt_us", "p99_rtt_us", "p999_rtt_us", "max_rtt_us",
        "throughput_msg_s", "bytes_per_sec", "mb_per_sec", "wire_mb_per_sec",
        "user_cpu_s", "sys_cpu_s", "total_cpu_s", "cpu_util_pct", "cpu_us_per_msg",
        "combined_peak_rss_kb",
    ]
    group_cols = ["workload_type", "requested_mode", "selected_transport", "payload_bytes", "producers", "consumers"]
    agg_rows = []
    for keys, grp in df.groupby(group_cols, dropna=False, sort=True):
        wtype, rmode, smode, pbytes, prod, cons = keys
        pass_grp = grp[grp["status"] == "PASS"]
        fail_cnt = int((grp["status"] == "FAIL").sum())
        blocked_cnt = int((grp["status"] == "BLOCKED").sum())
        unsup_cnt = int((grp["status"] == "UNSUPPORTED").sum())
        if len(pass_grp) == len(grp):
            agg_status = "PASS"
        elif len(pass_grp) > 0:
            agg_status = "PARTIAL"
        elif blocked_cnt > 0:
            agg_status = "BLOCKED"
        elif unsup_cnt > 0:
            agg_status = "UNSUPPORTED"
        else:
            agg_status = "FAIL"

        reasons = "; ".join(sorted(set(str(x) for x in grp["status_reason"].dropna() if str(x) != "ok"))) or "ok"
        row = {
            "experiment_id": exp_id,
            "workload_type": wtype,
            "mechanism": rmode,
            "selected_transport": smode,
            "payload_bytes": int(pbytes),
            "producers": int(prod),
            "consumers": int(cons),
            "status": agg_status,
            "status_reason": reasons,
            "n_trials_total": int(len(grp)),
            "n_trials_pass": int(len(pass_grp)),
            "n_trials_fail": fail_cnt,
            "total_completed_messages": int(pass_grp["completed_messages"].sum()) if len(pass_grp) else 0,
        }
        src = pass_grp if len(pass_grp) > 0 else grp.iloc[0:0]
        for m in metrics_to_agg:
            st = summarize_series(src[m]) if m in src.columns else summarize_series([])
            for k, v in st.items():
                row[f"{m}_{k}"] = round(v, 6) if (v is not None and not (isinstance(v, float) and math.isnan(v))) else ""
        agg_rows.append(row)

    agg_df = pd.DataFrame(agg_rows)
    agg_df.to_csv(os.path.join(args.processed_dir, "aggregated_results.csv"), index=False)

    # 4. Adaptive Selector Evaluation (raw/adaptive_results.csv)
    rtt_pass = df[(df["workload_type"] == "single_pair_rtt") & (df["status"] == "PASS")].copy()
    sel_over_df = df[(df["workload_type"] == "selector_overhead") & (df["status"] == "PASS")].copy()
    sel_overhead_ns = None
    if not sel_over_df.empty:
        sel_overhead_ns = float(pd.to_numeric(sel_over_df["avg_rtt_us"], errors="coerce").mean() * 1000.0)

    INDIVIDUAL_TRANSPORTS = ["pipe", "fifo", "sysv", "posix", "shm", "uds"]
    adaptive_rows = []
    payload_list = sorted(df[df["workload_type"] == "single_pair_rtt"]["payload_bytes"].unique())

    for pbytes in payload_list:
        sub_ind = rtt_pass[(rtt_pass["payload_bytes"] == pbytes) & (rtt_pass["requested_mode"].isin(INDIVIDUAL_TRANSPORTS))]
        sub_adp = rtt_pass[(rtt_pass["payload_bytes"] == pbytes) & (rtt_pass["requested_mode"] == "adaptive")]

        if sub_ind.empty or sub_adp.empty:
            adaptive_rows.append({
                "experiment_id": exp_id, "workload_type": "single_pair_rtt",
                "payload_bytes": int(pbytes), "threshold_bytes": meta.get("config", {}).get("threshold", 1024),
                "chosen_transport": "", "empirical_best_by_avg_rtt": "",
                "empirical_best_by_p50_rtt": "", "empirical_best_by_throughput": "",
                "status": "BLOCKED", "selection_accurate": "",
            })
            continue

        by_mech = sub_ind.groupby("requested_mode").agg(
            mean_avg=("avg_rtt_us", "mean"),
            med_p50=("p50_rtt_us", "median"),
            mean_p95=("p95_rtt_us", "mean"),
            mean_p99=("p99_rtt_us", "mean"),
            mean_tput=("throughput_msg_s", "mean"),
        )
        best_avg_mech = str(by_mech["mean_avg"].idxmin())
        best_p50_mech = str(by_mech["med_p50"].idxmin())
        best_tput_mech = str(by_mech["mean_tput"].idxmax())

        chosen = str(sub_adp["selected_transport"].iloc[0])
        adp_avg = float(sub_adp["avg_rtt_us"].mean())
        adp_p50 = float(sub_adp["p50_rtt_us"].median())
        adp_p95 = float(sub_adp["p95_rtt_us"].mean())
        adp_p99 = float(sub_adp["p99_rtt_us"].mean())
        adp_tput = float(sub_adp["throughput_msg_s"].mean())

        best_avg_val = float(by_mech.loc[best_avg_mech, "mean_avg"])
        best_p50_val = float(by_mech.loc[best_p50_mech, "med_p50"])
        best_tput_val = float(by_mech.loc[best_tput_mech, "mean_tput"])

        pipe_avg_val = float(by_mech.loc["pipe", "mean_avg"]) if "pipe" in by_mech.index else float("nan")
        pipe_tput_val = float(by_mech.loc["pipe", "mean_tput"]) if "pipe" in by_mech.index else float("nan")

        regret_lat_us = adp_avg - best_avg_val
        regret_lat_pct = (regret_lat_us / best_avg_val) * 100.0 if best_avg_val > 0 else float("nan")
        regret_tput = best_tput_val - adp_tput
        regret_tput_pct = (regret_tput / best_tput_val) * 100.0 if best_tput_val > 0 else float("nan")

        lat_vs_pipe_pct = ((adp_avg - pipe_avg_val) / pipe_avg_val) * 100.0 if not math.isnan(pipe_avg_val) and pipe_avg_val > 0 else float("nan")
        tput_vs_pipe_pct = ((adp_tput - pipe_tput_val) / pipe_tput_val) * 100.0 if not math.isnan(pipe_tput_val) and pipe_tput_val > 0 else float("nan")

        oh_pct = ((sel_overhead_ns / 1000.0) / adp_avg) * 100.0 if (sel_overhead_ns is not None and adp_avg > 0) else float("nan")

        adaptive_rows.append({
            "experiment_id": exp_id,
            "workload_type": "single_pair_rtt",
            "payload_bytes": int(pbytes),
            "threshold_bytes": meta.get("config", {}).get("threshold", 1024),
            "chosen_transport": chosen,
            "empirical_best_by_avg_rtt": best_avg_mech,
            "empirical_best_by_p50_rtt": best_p50_mech,
            "empirical_best_by_throughput": best_tput_mech,
            "selection_accurate_avg_rtt": bool(chosen == best_avg_mech),
            "selection_accurate_p50_rtt": bool(chosen == best_p50_mech),
            "adaptive_avg_rtt_us": round(adp_avg, 4),
            "adaptive_p50_rtt_us": round(adp_p50, 4),
            "adaptive_p95_rtt_us": round(adp_p95, 4),
            "adaptive_p99_rtt_us": round(adp_p99, 4),
            "adaptive_throughput_msg_s": round(adp_tput, 2),
            "best_avg_rtt_us": round(best_avg_val, 4),
            "best_p50_rtt_us": round(best_p50_val, 4),
            "best_throughput_msg_s": round(best_tput_val, 2),
            "pipe_avg_rtt_us": round(pipe_avg_val, 4) if not math.isnan(pipe_avg_val) else "",
            "pipe_throughput_msg_s": round(pipe_tput_val, 2) if not math.isnan(pipe_tput_val) else "",
            "regret_latency_us": round(regret_lat_us, 4),
            "regret_latency_pct": round(regret_lat_pct, 3),
            "regret_throughput_msg_s": round(regret_tput, 2),
            "regret_throughput_pct": round(regret_tput_pct, 3),
            "latency_diff_vs_pipe_pct": round(lat_vs_pipe_pct, 3) if not math.isnan(lat_vs_pipe_pct) else "",
            "throughput_diff_vs_pipe_pct": round(tput_vs_pipe_pct, 3) if not math.isnan(tput_vs_pipe_pct) else "",
            "selection_overhead_ns": round(sel_overhead_ns, 3) if sel_overhead_ns is not None else "",
            "selection_overhead_pct_of_rtt": round(oh_pct, 6) if not math.isnan(oh_pct) else "",
            "status": "PASS",
        })

    adaptive_df = pd.DataFrame(adaptive_rows)
    adaptive_df.to_csv(os.path.join(args.raw_dir, "adaptive_results.csv"), index=False)

    # 5. Paired Statistical Comparisons (processed/statistical_summary.csv)
    stat_rows = []
    for pbytes in payload_list:
        sub = rtt_pass[rtt_pass["payload_bytes"] == pbytes]
        if sub.empty:
            continue
        adp_sub = sub[sub["requested_mode"] == "adaptive"].set_index("trial")
        ind_sub = sub[sub["requested_mode"].isin(INDIVIDUAL_TRANSPORTS)]
        if ind_sub.empty:
            continue
        best_mech = str(ind_sub.groupby("requested_mode")["avg_rtt_us"].mean().idxmin())
        best_sub = ind_sub[ind_sub["requested_mode"] == best_mech].set_index("trial")

        # Paired comparisons: every eligible individual mechanism vs best_mech, plus adaptive vs best_mech and adaptive vs pipe
        targets = [(m, best_mech, "mechanism_vs_best") for m in sorted(ind_sub["requested_mode"].unique()) if m != best_mech]
        if not adp_sub.empty:
            targets.append(("adaptive", best_mech, "adaptive_vs_best"))
            if "pipe" in ind_sub["requested_mode"].unique():
                targets.append(("adaptive", "pipe", "adaptive_vs_pipe"))

        for mech_a, mech_b, cgroup in targets:
            sa = sub[sub["requested_mode"] == mech_a].set_index("trial")
            sb = sub[sub["requested_mode"] == mech_b].set_index("trial")
            common = sorted(set(sa.index) & set(sb.index))
            if not common:
                continue
            for metric in ("avg_rtt_us", "p50_rtt_us", "throughput_msg_s"):
                va = sa.loc[common, metric].to_numpy(dtype=float)
                vb = sb.loc[common, metric].to_numpy(dtype=float)
                t_stat, t_p, ci_lo, ci_hi = paired_t_test(va, vb)
                w_stat, w_p = wilcoxon_signed_rank(va, vb)
                mean_a = float(np.mean(va))
                mean_b = float(np.mean(vb))
                diff = mean_a - mean_b
                diff_pct = (diff / mean_b) * 100.0 if mean_b != 0 else float("nan")
                n_pairs = len(common)
                sig = (
                    "NA (n<2)" if n_pairs < 2 else
                    ("YES (t-test p<0.05)" if (not math.isnan(t_p) and t_p < 0.05) else "NO (p>=0.05)")
                )
                stat_rows.append({
                    "experiment_id": exp_id,
                    "comparison_group": cgroup,
                    "workload_type": "single_pair_rtt",
                    "payload_bytes": int(pbytes),
                    "mechanism_a": mech_a,
                    "mechanism_b": mech_b,
                    "metric": metric,
                    "n_pairs": n_pairs,
                    "mean_a": round(mean_a, 4),
                    "mean_b": round(mean_b, 4),
                    "mean_diff_a_minus_b": round(diff, 4),
                    "diff_pct": round(diff_pct, 3) if not math.isnan(diff_pct) else "",
                    "ci95_diff_low": round(ci_lo, 4) if not math.isnan(ci_lo) else "",
                    "ci95_diff_high": round(ci_hi, 4) if not math.isnan(ci_hi) else "",
                    "paired_t_stat": round(t_stat, 4) if (not math.isnan(t_stat) and not math.isinf(t_stat)) else str(t_stat),
                    "paired_t_pvalue": round(t_p, 6) if not math.isnan(t_p) else "",
                    "wilcoxon_w": round(w_stat, 4) if not math.isnan(w_stat) else "",
                    "wilcoxon_pvalue": round(w_p, 6) if not math.isnan(w_p) else "",
                    "significant_alpha_05": sig,
                    "statistical_method": "Paired Student t-test & exact/normal Wilcoxon signed-rank" + (" (scipy)" if HAS_SCIPY else " (exact built-in)"),
                })

    # Mixed workload paired comparison (pipe vs adaptive) if present
    mixed_pass = df[(df["workload_type"] == "mixed_80_20") & (df["status"] == "PASS")].copy()
    if not mixed_pass.empty:
        sa = mixed_pass[mixed_pass["requested_mode"] == "adaptive"].set_index("trial")
        sb = mixed_pass[mixed_pass["requested_mode"] == "pipe"].set_index("trial")
        common = sorted(set(sa.index) & set(sb.index))
        if common:
            for metric in ("avg_rtt_us", "throughput_msg_s"):
                va = sa.loc[common, metric].to_numpy(dtype=float)
                vb = sb.loc[common, metric].to_numpy(dtype=float)
                t_stat, t_p, ci_lo, ci_hi = paired_t_test(va, vb)
                w_stat, w_p = wilcoxon_signed_rank(va, vb)
                mean_a = float(np.mean(va))
                mean_b = float(np.mean(vb))
                diff = mean_a - mean_b
                diff_pct = (diff / mean_b) * 100.0 if mean_b != 0 else float("nan")
                stat_rows.append({
                    "experiment_id": exp_id,
                    "comparison_group": "mixed_workload_adaptive_vs_pipe",
                    "workload_type": "mixed_80_20",
                    "payload_bytes": "64_and_16384",
                    "mechanism_a": "adaptive",
                    "mechanism_b": "pipe",
                    "metric": metric,
                    "n_pairs": len(common),
                    "mean_a": round(mean_a, 4),
                    "mean_b": round(mean_b, 4),
                    "mean_diff_a_minus_b": round(diff, 4),
                    "diff_pct": round(diff_pct, 3),
                    "ci95_diff_low": round(ci_lo, 4) if not math.isnan(ci_lo) else "",
                    "ci95_diff_high": round(ci_hi, 4) if not math.isnan(ci_hi) else "",
                    "paired_t_stat": round(t_stat, 4) if (not math.isnan(t_stat) and not math.isinf(t_stat)) else str(t_stat),
                    "paired_t_pvalue": round(t_p, 6) if not math.isnan(t_p) else "",
                    "wilcoxon_w": round(w_stat, 4) if not math.isnan(w_stat) else "",
                    "wilcoxon_pvalue": round(w_p, 6) if not math.isnan(w_p) else "",
                    "significant_alpha_05": "YES (t-test p<0.05)" if (len(common) >= 2 and not math.isnan(t_p) and t_p < 0.05) else ("NA (n<2)" if len(common) < 2 else "NO (p>=0.05)"),
                    "statistical_method": "Paired Student t-test & exact/normal Wilcoxon signed-rank" + (" (scipy)" if HAS_SCIPY else " (exact built-in)"),
                })

    pd.DataFrame(stat_rows).to_csv(os.path.join(args.processed_dir, "statistical_summary.csv"), index=False)

    # 6. Component status summary (all 8 components)
    k_path = os.path.join(args.raw_dir, "kernel_results.csv")
    k_df = pd.read_csv(k_path) if os.path.exists(k_path) else pd.DataFrame()

    comp_status = {}
    for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive"]:
        m_df = df[(df["requested_mode"] == m) & (df["workload_type"] == "single_pair_rtt")]
        if m_df.empty:
            comp_status[m] = {"status": "BLOCKED", "reason": "No trials recorded"}
            continue
        statuses = set(m_df["status"].astype(str))
        reasons = "; ".join(sorted(set(str(x) for x in m_df["status_reason"].dropna() if str(x) != "ok")))
        if statuses == {"PASS"}:
            comp_status[m] = {"status": "PASS", "reason": "All payload sizes and trials passed"}
        elif "PASS" in statuses and ("UNSUPPORTED" in statuses or "BLOCKED" in statuses) and "FAIL" not in statuses:
            # Distinguish expected architectural bounds (e.g. SHM <= 1024B) vs OS blocks
            if m == "shm" and all(int(r["payload_bytes"]) <= 1024 for _, r in m_df[m_df["status"] == "PASS"].iterrows()):
                comp_status[m] = {
                    "status": "PASS",
                    "reason": "All supported payloads (<= 1024 B) passed; >1024 B cleanly marked UNSUPPORTED (SHM_MAX_PAYLOAD=1024)",
                }
            else:
                comp_status[m] = {"status": "PARTIAL", "reason": reasons or "Some payload sizes unsupported/blocked"}
        elif statuses == {"BLOCKED"}:
            comp_status[m] = {"status": "BLOCKED", "reason": reasons}
        elif "FAIL" in statuses:
            comp_status[m] = {"status": "FAIL", "reason": reasons}
        else:
            comp_status[m] = {"status": "PARTIAL", "reason": reasons}

    if not k_df.empty:
        k_bench = k_df[k_df["record_type"] == "benchmark"]
        k_func = k_df[k_df["record_type"] == "functional_test"]
        k_statuses = set(k_df["status"].astype(str))
        k_reasons = "; ".join(sorted(set(str(x) for x in k_df["status_reason"].dropna() if str(x) != "ok")))
        if "PASS" in k_statuses and "FAIL" not in k_statuses and "BLOCKED" not in k_statuses:
            comp_status["kernel_aipc"] = {"status": "PASS", "reason": "All kernel tests and matched benchmarks passed"}
        elif "FAIL" in k_statuses:
            comp_status["kernel_aipc"] = {"status": "FAIL", "reason": k_reasons}
        elif k_statuses == {"BLOCKED"} or ("BLOCKED" in k_statuses and "PASS" not in k_bench["status"].astype(str).values):
            comp_status["kernel_aipc"] = {"status": "BLOCKED", "reason": k_reasons}
        else:
            comp_status["kernel_aipc"] = {"status": "PARTIAL", "reason": k_reasons}
    else:
        comp_status["kernel_aipc"] = {"status": "BLOCKED", "reason": "kernel_results.csv missing"}

    # Adaptive summary metrics
    adp_pass_rows = adaptive_df[adaptive_df["status"] == "PASS"] if not adaptive_df.empty else pd.DataFrame()
    adp_summary = {}
    if not adp_pass_rows.empty:
        acc_avg = float(adp_pass_rows["selection_accurate_avg_rtt"].mean() * 100.0)
        acc_p50 = float(adp_pass_rows["selection_accurate_p50_rtt"].mean() * 100.0)
        adp_summary = {
            "payloads_evaluated": int(len(adp_pass_rows)),
            "selection_accuracy_avg_rtt_pct": round(acc_avg, 2),
            "selection_accuracy_p50_rtt_pct": round(acc_p50, 2),
            "mean_regret_latency_pct": round(float(adp_pass_rows["regret_latency_pct"].mean()), 3),
            "max_regret_latency_pct": round(float(adp_pass_rows["regret_latency_pct"].max()), 3),
            "selection_overhead_ns": round(sel_overhead_ns, 3) if sel_overhead_ns is not None else None,
        }

    all_8_statuses = [v["status"] for v in comp_status.values()]
    if all(s == "PASS" for s in all_8_statuses):
        overall_status = "PASS"
    elif any(s == "FAIL" for s in all_8_statuses):
        overall_status = "FAIL"
    elif any(s == "PASS" for s in all_8_statuses):
        overall_status = "PARTIAL"
    else:
        overall_status = "BLOCKED"

    meta["analyzed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta["overall_status"] = overall_status
    meta["component_status"] = comp_status
    meta["adaptive_summary"] = adp_summary
    meta["scipy_available"] = HAS_SCIPY

    # Enrich hardware/compiler/OS metadata from environment.txt if present
    env_txt = os.path.join(os.path.dirname(args.raw_dir), "environment.txt")
    if os.path.exists(env_txt):
        try:
            txt = open(env_txt, "r", encoding="utf-8", errors="replace").read()
            for line in txt.splitlines():
                if line.startswith("Environment ID:"):
                    meta["environment_id"] = line.split(":", 1)[1].strip()
                elif "model name" in line and ":" in line:
                    meta["cpu_model"] = line.split(":", 1)[1].strip()
                elif line.startswith("Model name:") and ":" in line:
                    meta["cpu_model"] = line.split(":", 1)[1].strip()
                elif line.startswith("gcc ") or "GCC" in line:
                    meta["compiler"] = line.strip()
                elif line.startswith("CFLAGS"):
                    meta["build_flags"] = line.strip()
                elif line.startswith("MSYS_NT") or (line.startswith("Linux ") and "strace" not in line and "perf" not in line):
                    meta["kernel_release"] = line.strip()
                elif line.startswith("PRETTY_NAME="):
                    meta["host_os"] = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    meta["row_counts"] = {
        "all_results": int(len(df)),
        "aggregated_results": int(len(agg_df)),
        "statistical_summary": int(len(stat_rows)),
        "adaptive_results": int(len(adaptive_df)),
        "kernel_results": int(len(k_df)),
    }

    with open(os.path.join(args.processed_dir, "benchmark_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Analysis complete: overall_status={overall_status}, rows={len(df)}, comparisons={len(stat_rows)}")


if __name__ == "__main__":
    main()
