#!/usr/bin/env python3
"""Separate OS, memory, context-switch, and syscall profiler for Mini A-IPC.

Runs OUTSIDE primary latency measurement trials so sampling, /proc or Win32
polling, strace, and perf never contaminate primary RTT or throughput timings.
"""
import argparse
import csv
import ctypes
import ctypes.wintypes as wt
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time


# ---------------------------------------------------------------------------
# Windows NtQuerySystemInformation(5) sampler (zero external dependencies)
# ---------------------------------------------------------------------------
class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wt.USHORT),
        ("MaximumLength", wt.USHORT),
        ("Buffer", ctypes.c_void_p),
    ]


class _CLIENT_ID(ctypes.Structure):
    _fields_ = [("UniqueProcess", ctypes.c_void_p), ("UniqueThread", ctypes.c_void_p)]


class _SYSTEM_THREAD_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("KernelTime", ctypes.c_int64),
        ("UserTime", ctypes.c_int64),
        ("CreateTime", ctypes.c_int64),
        ("WaitTime", wt.ULONG),
        ("StartAddress", ctypes.c_void_p),
        ("ClientId", _CLIENT_ID),
        ("Priority", ctypes.c_long),
        ("BasePriority", ctypes.c_long),
        ("ContextSwitches", wt.ULONG),
        ("ThreadState", wt.ULONG),
        ("WaitReason", wt.ULONG),
    ]


class _SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", wt.ULONG),
        ("NumberOfThreads", wt.ULONG),
        ("WorkingSetPrivateSize", ctypes.c_int64),
        ("HardFaultCount", wt.ULONG),
        ("NumberOfThreadsHighWatermark", wt.ULONG),
        ("CycleTime", ctypes.c_uint64),
        ("CreateTime", ctypes.c_int64),
        ("UserTime", ctypes.c_int64),
        ("KernelTime", ctypes.c_int64),
        ("ImageName", _UNICODE_STRING),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", wt.ULONG),
        ("SessionId", wt.ULONG),
        ("UniqueProcessKey", ctypes.c_size_t),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", wt.ULONG),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivatePageCount", ctypes.c_size_t),
        ("ReadOperationCount", ctypes.c_int64),
        ("WriteOperationCount", ctypes.c_int64),
        ("OtherOperationCount", ctypes.c_int64),
        ("ReadTransferCount", ctypes.c_int64),
        ("WriteTransferCount", ctypes.c_int64),
        ("OtherTransferCount", ctypes.c_int64),
    ]


def _win32_snapshot_tree(root_pid):
    """Return per-PID metrics for root_pid and its descendants on Windows."""
    ntdll = ctypes.WinDLL("ntdll")
    STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
    sz = 512 * 1024
    while True:
        buf = (ctypes.c_ubyte * sz)()
        ret_len = wt.ULONG()
        st = ntdll.NtQuerySystemInformation(5, buf, sz, ctypes.byref(ret_len))
        if (st & 0xFFFFFFFF) == STATUS_INFO_LENGTH_MISMATCH:
            sz = max(sz * 2, ret_len.value + 65536)
            continue
        if st != 0:
            return {}
        break

    procs = {}
    children_map = {}
    base = ctypes.addressof(buf)
    spi_sz = ctypes.sizeof(_SYSTEM_PROCESS_INFORMATION)
    th_sz = ctypes.sizeof(_SYSTEM_THREAD_INFORMATION)
    off = 0
    while True:
        spi = _SYSTEM_PROCESS_INFORMATION.from_address(base + off)
        pid = int(spi.UniqueProcessId or 0)
        ppid = int(spi.InheritedFromUniqueProcessId or 0)
        ctx = 0
        for t in range(spi.NumberOfThreads):
            th = _SYSTEM_THREAD_INFORMATION.from_address(base + off + spi_sz + t * th_sz)
            ctx += int(th.ContextSwitches)
        procs[pid] = {
            "pid": pid,
            "ppid": ppid,
            "create_time": int(spi.CreateTime),
            "rss_kb": int(spi.WorkingSetSize) / 1024.0,
            "peak_rss_kb": int(spi.PeakWorkingSetSize) / 1024.0,
            "page_faults": int(spi.PageFaultCount),
            "ctx_total": ctx,
        }
        if pid != 0:
            children_map.setdefault(ppid, []).append(pid)
        if spi.NextEntryOffset == 0:
            break
        off += spi.NextEntryOffset

    if root_pid not in procs:
        return {}
    root_ct = procs[root_pid]["create_time"]
    tree = {}
    queue = [root_pid]
    while queue:
        cur = queue.pop(0)
        if cur in procs and cur not in tree:
            tree[cur] = procs[cur]
            cur_ct = procs[cur]["create_time"]
            for ch_pid in children_map.get(cur, []):
                # Guard against Windows PID reuse: a child cannot predate its parent
                if ch_pid in procs and procs[ch_pid]["create_time"] >= max(root_ct, cur_ct):
                    queue.append(ch_pid)
    return tree


# ---------------------------------------------------------------------------
# Linux /proc sampler
# ---------------------------------------------------------------------------
def _read_proc_status(pid):
    path = f"/proc/{pid}/status"
    info = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
    except OSError:
        return None
    def parse_kb(key):
        val = info.get(key, "").split()
        return float(val[0]) if val and val[0].isdigit() else None
    def parse_int(key):
        val = info.get(key, "").strip()
        return int(val) if val.isdigit() else None
    return {
        "pid": pid,
        "ppid": parse_int("PPid") or 0,
        "rss_kb": parse_kb("VmRSS"),
        "peak_rss_kb": parse_kb("VmHWM"),
        "vol_ctx": parse_int("voluntary_ctxt_switches"),
        "invol_ctx": parse_int("nonvoluntary_ctxt_switches"),
    }


def _linux_snapshot_tree(root_pid):
    tree = {}
    queue = [root_pid]
    seen = set()
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        st = _read_proc_status(cur)
        if st is not None:
            tree[cur] = st
            try:
                for tid in os.listdir(f"/proc/{cur}/task"):
                    cfile = f"/proc/{cur}/task/{tid}/children"
                    if os.path.exists(cfile):
                        with open(cfile, "r", encoding="utf-8") as cf:
                            for tok in cf.read().split():
                                if tok.isdigit():
                                    queue.append(int(tok))
            except OSError:
                pass
    return tree


def read_kernel_meminfo():
    """Read /proc/meminfo on Linux or GlobalMemoryStatusEx on Windows."""
    result = {
        "mem_total_kb": None,
        "mem_free_kb": None,
        "mem_available_kb": None,
        "slab_kb": None,
        "sreclaimable_kb": None,
        "sunreclaim_kb": None,
    }
    if os.path.exists("/proc/meminfo"):
        mapping = {
            "MemTotal": "mem_total_kb",
            "MemFree": "mem_free_kb",
            "MemAvailable": "mem_available_kb",
            "Slab": "slab_kb",
            "SReclaimable": "sreclaimable_kb",
            "SUnreclaim": "sunreclaim_kb",
        }
        try:
            with open("/proc/meminfo", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    if k in mapping:
                        toks = v.strip().split()
                        if toks and toks[0].isdigit():
                            result[mapping[k]] = int(toks[0])
        except OSError:
            pass
        return result

    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wt.DWORD),
                ("dwMemoryLoad", wt.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]
        ms = MEMORYSTATUSEX()
        ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            result["mem_total_kb"] = int(ms.ullTotalPhys // 1024)
            result["mem_available_kb"] = int(ms.ullAvailPhys // 1024)
            result["mem_free_kb"] = int(ms.ullAvailPhys // 1024)
    return result


def profile_single_run(bin_path, mode, payload, messages, warmup, cpu_prod, cpu_cons, exp_id):
    cmd = [
        bin_path,
        "--mode", mode,
        "--workload", "rtt",
        "--size", str(payload),
        "--count", str(messages),
        "--warmup", str(warmup),
        "--trial", "1",
        "--experiment-id", exp_id,
    ]
    if cpu_prod >= 0:
        cmd.extend(["--cpu-producer", str(cpu_prod)])
    if cpu_cons >= 0:
        cmd.extend(["--cpu-consumer", str(cpu_cons)])

    is_linux = sys.platform.startswith("linux")
    is_win = os.name == "nt"

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    root_pid = proc.pid

    parent_rss_samples = []
    child_rss_samples = []
    total_rss_samples = []
    peak_by_pid = {}
    ctx_by_pid = {}
    vol_by_pid = {}
    invol_by_pid = {}

    while proc.poll() is None:
        if is_linux:
            snap = _linux_snapshot_tree(root_pid)
            if root_pid in snap:
                prss = snap[root_pid]["rss_kb"] or 0.0
                parent_rss_samples.append(prss)
                crss = sum((v["rss_kb"] or 0.0) for k, v in snap.items() if k != root_pid)
                if len(snap) > 1:
                    child_rss_samples.append(crss)
                total_rss_samples.append(prss + crss)
                for k, v in snap.items():
                    if v["peak_rss_kb"] is not None:
                        peak_by_pid[k] = max(peak_by_pid.get(k, 0.0), v["peak_rss_kb"])
                    if v["vol_ctx"] is not None:
                        vol_by_pid[k] = max(vol_by_pid.get(k, 0), v["vol_ctx"])
                    if v["invol_ctx"] is not None:
                        invol_by_pid[k] = max(invol_by_pid.get(k, 0), v["invol_ctx"])
        elif is_win:
            snap = _win32_snapshot_tree(root_pid)
            if root_pid in snap:
                prss = snap[root_pid]["rss_kb"]
                parent_rss_samples.append(prss)
                crss = sum(v["rss_kb"] for k, v in snap.items() if k != root_pid)
                if len(snap) > 1:
                    child_rss_samples.append(crss)
                total_rss_samples.append(prss + crss)
                for k, v in snap.items():
                    peak_by_pid[k] = max(peak_by_pid.get(k, 0.0), v["peak_rss_kb"])
                    ctx_by_pid[k] = max(ctx_by_pid.get(k, 0), v["ctx_total"])
        time.sleep(0.002)

    out_b, err_b = proc.communicate(timeout=60)
    out_s = out_b.decode("utf-8", errors="replace").strip()
    parsed = {}
    if out_s:
        try:
            parsed = json.loads(out_s.splitlines()[-1])
        except json.JSONDecodeError:
            parsed = {}

    status = parsed.get("status", "PASS" if proc.returncode == 0 else "FAIL")
    reason = parsed.get("status_reason", err_b.decode("utf-8", errors="replace").strip())

    # If the run was so short that polling caught 0 samples, fallback to rusage peaks
    parent_peak = peak_by_pid.get(root_pid)
    child_peaks = [v for k, v in peak_by_pid.items() if k != root_pid]
    child_peak = sum(child_peaks) if child_peaks else None
    if parent_peak is None and parsed.get("parent_peak_rss_kb") is not None:
        parent_peak = float(parsed["parent_peak_rss_kb"])
    if child_peak is None and parsed.get("child_peak_rss_kb") is not None:
        child_peak = float(parsed["child_peak_rss_kb"])

    parent_avg = (sum(parent_rss_samples) / len(parent_rss_samples)) if parent_rss_samples else None
    child_avg = (sum(child_rss_samples) / len(child_rss_samples)) if child_rss_samples else None
    total_avg = (sum(total_rss_samples) / len(total_rss_samples)) if total_rss_samples else None
    total_peak = ((parent_peak or 0.0) + (child_peak or 0.0)) if (parent_peak is not None or child_peak is not None) else parsed.get("combined_peak_rss_kb")

    if is_linux:
        vol_ctx = sum(vol_by_pid.values()) if vol_by_pid else parsed.get("voluntary_ctx_switches")
        invol_ctx = sum(invol_by_pid.values()) if invol_by_pid else parsed.get("involuntary_ctx_switches")
        total_ctx = (vol_ctx + invol_ctx) if (vol_ctx is not None and invol_ctx is not None) else None
        ctx_method = "linux_proc_status_rusage"
    elif is_win:
        vol_ctx = None
        invol_ctx = None
        total_ctx = sum(ctx_by_pid.values()) if ctx_by_pid else None
        ctx_method = "win32_ntdll_thread_context_switches" if total_ctx is not None else "unavailable"
    else:
        vol_ctx = invol_ctx = total_ctx = None
        ctx_method = "unavailable"

    meminfo = read_kernel_meminfo()

    if status != "PASS":
        return {
            "experiment_id": exp_id,
            "mechanism": mode,
            "selected_transport": parsed.get("selected_transport", mode),
            "payload_bytes": payload,
            "profile_messages": messages,
            "status": status,
            "status_reason": reason,
            "producer_avg_rss_kb": "",
            "consumer_avg_rss_kb": "",
            "total_avg_rss_kb": "",
            "producer_peak_rss_kb": "",
            "consumer_peak_rss_kb": "",
            "total_peak_rss_kb": "",
            "rss_samples": 0,
            "total_ctx_switches": "",
            "voluntary_ctx_switches": "",
            "involuntary_ctx_switches": "",
            "minor_page_faults": "",
            "major_page_faults": "",
            "user_cpu_s": "",
            "sys_cpu_s": "",
            "total_cpu_s": "",
            "cpu_util_pct": "",
            "kernel_mem_total_kb": meminfo["mem_total_kb"] if meminfo["mem_total_kb"] is not None else "",
            "kernel_mem_available_kb": meminfo["mem_available_kb"] if meminfo["mem_available_kb"] is not None else "",
            "kernel_slab_kb": meminfo["slab_kb"] if meminfo["slab_kb"] is not None else "",
            "profiling_method": ctx_method,
        }

    return {
        "experiment_id": exp_id,
        "mechanism": mode,
        "selected_transport": parsed.get("selected_transport", mode),
        "payload_bytes": payload,
        "profile_messages": messages,
        "status": status,
        "status_reason": reason,
        "producer_avg_rss_kb": round(parent_avg, 2) if parent_avg is not None else "",
        "consumer_avg_rss_kb": round(child_avg, 2) if child_avg is not None else "",
        "total_avg_rss_kb": round(total_avg, 2) if total_avg is not None else "",
        "producer_peak_rss_kb": round(parent_peak, 2) if parent_peak is not None else "",
        "consumer_peak_rss_kb": round(child_peak, 2) if child_peak is not None else "",
        "total_peak_rss_kb": round(total_peak, 2) if total_peak is not None else "",
        "rss_samples": len(total_rss_samples),
        "total_ctx_switches": total_ctx if total_ctx is not None else "",
        "voluntary_ctx_switches": vol_ctx if vol_ctx is not None else "",
        "involuntary_ctx_switches": invol_ctx if invol_ctx is not None else "",
        "minor_page_faults": parsed.get("minor_page_faults") if parsed.get("minor_page_faults") is not None else "",
        "major_page_faults": parsed.get("major_page_faults") if parsed.get("major_page_faults") is not None else "",
        "user_cpu_s": parsed.get("user_cpu_s") if parsed.get("user_cpu_s") is not None else "",
        "sys_cpu_s": parsed.get("sys_cpu_s") if parsed.get("sys_cpu_s") is not None else "",
        "total_cpu_s": parsed.get("total_cpu_s") if parsed.get("total_cpu_s") is not None else "",
        "cpu_util_pct": parsed.get("cpu_util_pct") if parsed.get("cpu_util_pct") is not None else "",
        "kernel_mem_total_kb": meminfo["mem_total_kb"] if meminfo["mem_total_kb"] is not None else "",
        "kernel_mem_available_kb": meminfo["mem_available_kb"] if meminfo["mem_available_kb"] is not None else "",
        "kernel_slab_kb": meminfo["slab_kb"] if meminfo["slab_kb"] is not None else "",
        "profiling_method": ctx_method,
    }


def is_real_linux_strace():
    if not sys.platform.startswith("linux"):
        return False, f"Host platform is {platform.system()} ({sys.platform}); Linux kernel strace unavailable"
    st_bin = shutil.which("strace")
    if not st_bin:
        return False, "strace is not installed on this Linux host"
    res = subprocess.run([st_bin, "--version"], capture_output=True, text=True)
    if "cygwin" in (res.stdout + res.stderr).lower():
        return False, "Detected Cygwin strace instead of Linux kernel strace"
    return True, st_bin


def run_syscall_profiling(mini_aipc_path, mechanisms, syscall_count, exp_id):
    rows = []
    ok, info = is_real_linux_strace()
    if not ok:
        for m in mechanisms:
            rows.append({
                "experiment_id": exp_id,
                "mechanism": m,
                "payload_bytes": 64,
                "exchanges": syscall_count,
                "status": "UNAVAILABLE",
                "status_reason": info,
                "total_syscalls": "",
                "total_syscalls_per_exchange": "",
                "comm_syscalls": "",
                "comm_syscalls_per_exchange": "",
                "setup_cleanup_syscalls": "",
                "other_syscalls": "",
                "classification": "unavailable",
                "relevant_syscall_details": info,
            })
        return rows

    import importlib.util
    parser_path = os.path.join(os.path.dirname(__file__), "parse_strace.py")
    spec = importlib.util.spec_from_file_location("parse_strace", parser_path)
    parse_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parse_mod)

    strace_bin = info
    for m in mechanisms:
        payload = 64
        trace_mech = "shm" if m == "adaptive" else m
        with tempfile.NamedTemporaryFile(prefix=f"strace_{m}_", suffix=".log", delete=False) as tf:
            tlog = tf.name
        try:
            cmd = [strace_bin, "-f", "-o", tlog, mini_aipc_path,
                   "--mode", m, "--size", str(payload), "--count", str(syscall_count), "--csv"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                status = "BLOCKED" if "Function not implemented" in res.stderr else "FAIL"
                rows.append({
                    "experiment_id": exp_id,
                    "mechanism": m,
                    "payload_bytes": payload,
                    "exchanges": syscall_count,
                    "status": status,
                    "status_reason": res.stderr.strip() or f"exit {res.returncode}",
                    "total_syscalls": "",
                    "total_syscalls_per_exchange": "",
                    "comm_syscalls": "",
                    "comm_syscalls_per_exchange": "",
                    "setup_cleanup_syscalls": "",
                    "other_syscalls": "",
                    "classification": "unavailable",
                    "relevant_syscall_details": res.stderr.strip(),
                })
                continue
            csv_line = parse_mod.parse_strace(tlog, trace_mech, payload, syscall_count)
            parts = list(csv.reader([csv_line]))[0]
            rows.append({
                "experiment_id": exp_id,
                "mechanism": m,
                "payload_bytes": int(parts[1]),
                "exchanges": int(parts[2]),
                "status": "PASS",
                "status_reason": "ok",
                "total_syscalls": int(parts[3]),
                "total_syscalls_per_exchange": float(parts[4]),
                "comm_syscalls": int(parts[5]),
                "comm_syscalls_per_exchange": float(parts[6]),
                "setup_cleanup_syscalls": int(parts[7]),
                "other_syscalls": int(parts[8]),
                "classification": parts[9],
                "relevant_syscall_details": parts[10],
            })
        finally:
            if os.path.exists(tlog):
                os.remove(tlog)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Separate OS/Memory/Syscall profiler")
    ap.add_argument("--bin", required=True, help="Path to aipc_unified_bench")
    ap.add_argument("--mini-aipc", required=True, help="Path to mini-aipc binary")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--payloads", default="64,256,1024,4096,16384,65536,262144")
    ap.add_argument("--mechanisms", default="pipe,fifo,sysv,posix,shm,uds,adaptive")
    ap.add_argument("--messages", type=int, default=1000)
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--syscall-messages", type=int, default=100)
    ap.add_argument("--cpu-producer", type=int, default=0)
    ap.add_argument("--cpu-consumer", type=int, default=1)
    ap.add_argument("--out-profile", required=True)
    ap.add_argument("--out-syscalls", required=True)
    args = ap.parse_args()

    payloads = [int(x) for x in args.payloads.split(",") if x.strip()]
    mechs = [x.strip() for x in args.mechanisms.split(",") if x.strip()]

    profile_rows = []
    for size in payloads:
        # Scale message count for 256KB slightly if huge to keep profiling crisp
        msg_cnt = args.messages if size <= 65536 else min(args.messages, 500)
        for m in mechs:
            row = profile_single_run(
                args.bin, m, size, msg_cnt, args.warmup,
                args.cpu_producer, args.cpu_consumer, args.experiment_id
            )
            profile_rows.append(row)

    os.makedirs(os.path.dirname(args.out_profile) or ".", exist_ok=True)
    if profile_rows:
        with open(args.out_profile, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(profile_rows[0].keys()))
            writer.writeheader()
            writer.writerows(profile_rows)

    sys_rows = run_syscall_profiling(args.mini_aipc, mechs, args.syscall_messages, args.experiment_id)
    os.makedirs(os.path.dirname(args.out_syscalls) or ".", exist_ok=True)
    if sys_rows:
        with open(args.out_syscalls, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(sys_rows[0].keys()))
            writer.writeheader()
            writer.writerows(sys_rows)

    print(f"Profiled {len(profile_rows)} resource configurations and {len(sys_rows)} syscall entries.")


if __name__ == "__main__":
    main()
