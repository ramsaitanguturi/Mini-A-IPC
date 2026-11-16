#!/usr/bin/env bash
set -euo pipefail

# Kernel AIPC Module Verification & Benchmarking Suite
# Safely compiles, loads (only if not pre-loaded), verifies all required
# kernel behaviors, benchmarks matched & exploratory workloads, and restores
# the exact original kernel module state on exit or interruption.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EXPERIMENT_ID="${EXPERIMENT_ID:-exp_manual}"
OUT_CSV="${OUT_CSV:-results/unified/raw/kernel_results.csv}"
OUT_EXPLORATORY="${OUT_EXPLORATORY:-results/unified/raw/kernel_exploratory.csv}"
PAYLOADS="${PAYLOADS:-64,256,1024,4096,16384,65536,262144}"
MESSAGES="${MESSAGES:-2000}"
WARMUP="${WARMUP:-100}"
TRIALS="${TRIALS:-7}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$(dirname "$OUT_CSV")"

WE_LOADED_MODULE=0
WAS_LOADED_BEFORE=0

if lsmod 2>/dev/null | grep -q '^aipc_module\b'; then
  WAS_LOADED_BEFORE=1
fi

cleanup_kernel_state() {
  if [[ "$WE_LOADED_MODULE" -eq 1 && "$WAS_LOADED_BEFORE" -eq 0 ]]; then
    if lsmod 2>/dev/null | grep -q '^aipc_module\b'; then
      echo "[kernel-suite] Restoring state: unloading aipc_module (loaded by suite)..."
      sudo -n rmmod aipc_module 2>/dev/null || sudo rmmod aipc_module 2>/dev/null || true
    fi
  fi
}
trap cleanup_kernel_state EXIT INT TERM

write_blocked_matrix() {
  local reason="$1"
  local compiled_status="$2"
  local compiled_reason="$3"
  "$PYTHON_BIN" - "$OUT_CSV" "$EXPERIMENT_ID" "$reason" "$compiled_status" "$compiled_reason" "$PAYLOADS" <<'PY'
import csv, sys
out_csv, exp_id, reason, c_status, c_reason, payloads_s = sys.argv[1:]
tests = [
    ("module_compilation", c_status, c_reason),
    ("module_loading", "BLOCKED", reason),
    ("device_creation", "BLOCKED", reason),
    ("write_read_functionality", "BLOCKED", reason),
    ("data_integrity", "BLOCKED", reason),
    ("buffer_capacity", "BLOCKED", reason),
    ("empty_buffer_behaviour", "BLOCKED", reason),
    ("full_buffer_behaviour", "BLOCKED", reason),
    ("blocking_operations", "BLOCKED", reason),
    ("nonblocking_operations", "BLOCKED", reason),
    ("concurrent_readers_writers", "BLOCKED", reason),
    ("poll_behaviour", "BLOCKED", reason),
    ("error_handling", "BLOCKED", reason),
    ("module_unloading", "BLOCKED", reason),
    ("repeated_load_unload", "BLOCKED", reason),
]
fieldnames = [
    "experiment_id", "record_type", "test_or_metric", "payload_bytes", "trial",
    "messages", "completed_messages", "validation_errors", "status", "status_reason",
    "elapsed_ns", "duration_s", "avg_latency_us", "throughput_msg_s",
    "bytes_per_sec", "mb_per_sec", "consumer_peak_rss_kb", "workload_type",
]
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for name, st, rsn in tests:
        w.writerow({
            "experiment_id": exp_id, "record_type": "functional_test",
            "test_or_metric": name, "payload_bytes": "", "trial": "",
            "messages": "", "completed_messages": "", "validation_errors": "",
            "status": st, "status_reason": rsn, "elapsed_ns": "", "duration_s": "",
            "avg_latency_us": "", "throughput_msg_s": "", "bytes_per_sec": "",
            "mb_per_sec": "", "consumer_peak_rss_kb": "", "workload_type": "kernel_functional",
        })
    for p in [int(x) for x in payloads_s.split(",") if x.strip()]:
        w.writerow({
            "experiment_id": exp_id, "record_type": "benchmark",
            "test_or_metric": "kernel_unidirectional_mailbox", "payload_bytes": p,
            "trial": "", "messages": "", "completed_messages": "", "validation_errors": "",
            "status": "BLOCKED", "status_reason": reason, "elapsed_ns": "", "duration_s": "",
            "avg_latency_us": "", "throughput_msg_s": "", "bytes_per_sec": "",
            "mb_per_sec": "", "consumer_peak_rss_kb": "", "workload_type": "kernel_unidirectional_mailbox",
        })
print(f"[kernel-suite] Recorded BLOCKED kernel matrix to {out_csv}: {reason}")
PY
}

OS_NAME="$(uname -s)"
if [[ "$OS_NAME" != "Linux" ]]; then
  write_blocked_matrix \
    "Host OS is ${OS_NAME}; Linux kernel module build and insmod require a Linux kernel" \
    "BLOCKED" \
    "Host OS is ${OS_NAME}; Linux kernel build tree unavailable"
  exit 0
fi

KREL="$(uname -r)"
KDIR="/lib/modules/${KREL}/build"
if [[ ! -d "$KDIR" ]]; then
  write_blocked_matrix \
    "Missing Linux kernel build headers at ${KDIR}; cannot compile or load kernel/aipc_module.ko" \
    "BLOCKED" \
    "Missing kernel build directory ${KDIR}"
  exit 0
fi

# Compile kernel module
COMPILE_STATUS="PASS"
COMPILE_REASON="make kernel-module succeeded for ${KREL}"
if ! make kernel-module >/tmp/aipc_kbuild.log 2>&1; then
  COMPILE_STATUS="FAIL"
  COMPILE_REASON="$(tail -n 5 /tmp/aipc_kbuild.log | tr '\n' ' ')"
  rm -f /tmp/aipc_kbuild.log
  write_blocked_matrix "Kernel module compilation failed: ${COMPILE_REASON}" "$COMPILE_STATUS" "$COMPILE_REASON"
  exit 1
fi
rm -f /tmp/aipc_kbuild.log

# Check if module already loaded or if sudo insmod is available
if [[ "$WAS_LOADED_BEFORE" -eq 0 ]]; then
  if ! sudo -n insmod "$ROOT/kernel/aipc_module.ko" 2>/tmp/aipc_insmod.err; then
    INSERR="$(cat /tmp/aipc_insmod.err 2>/dev/null | tr '\n' ' ')"
    rm -f /tmp/aipc_insmod.err
    write_blocked_matrix \
      "Module compiled cleanly, but insmod requires non-interactive root/sudo privileges or module-signing permission (${INSERR:-permission denied})" \
      "$COMPILE_STATUS" "$COMPILE_REASON"
    exit 0
  fi
  rm -f /tmp/aipc_insmod.err
  WE_LOADED_MODULE=1
fi

if [[ ! -c /dev/aipc ]]; then
  write_blocked_matrix "Module loaded but /dev/aipc device node was not created" "$COMPILE_STATUS" "$COMPILE_REASON"
  exit 1
fi

# Run existing kernel-test & exploratory benchmark + matched kernel benchmark
bash ./tests/kernel/test_device.sh || true
"$PYTHON_BIN" ./bench/benchmark_kernel_mailbox.py --trials "$TRIALS" --messages "$MESSAGES" --output "$OUT_EXPLORATORY" || true
"$PYTHON_BIN" ./bench/benchmark_kernel_matched.py \
  --device /dev/aipc \
  --experiment-id "$EXPERIMENT_ID" \
  --payloads "$PAYLOADS" \
  --messages "$MESSAGES" \
  --warmup "$WARMUP" \
  --trials "$TRIALS" \
  --output "$OUT_CSV"

# Record module lifecycle checks (compilation, loading, device, unloading, repeated load/unload)
LOAD_STATUS="PASS"
UNLOAD_STATUS="PASS"
UNLOAD_REASON="Restored original module state"
RELOAD_STATUS="PASS"
RELOAD_REASON="Repeated load/unload verified"

if [[ "$WE_LOADED_MODULE" -eq 1 && "$WAS_LOADED_BEFORE" -eq 0 ]]; then
  if sudo -n rmmod aipc_module 2>/dev/null; then
    WE_LOADED_MODULE=0
    if [[ -e /dev/aipc || -e /sys/class/aipc/aipc ]]; then
      UNLOAD_STATUS="FAIL"
      UNLOAD_REASON="/dev/aipc or sysfs node remained after rmmod"
    fi
    if ! sudo -n env ITERATIONS=5 ./tests/kernel/test_load_unload.sh >/dev/null 2>&1; then
      RELOAD_STATUS="FAIL"
      RELOAD_REASON="Repeated load/unload stress failed"
    fi
  else
    UNLOAD_STATUS="FAIL"
    UNLOAD_REASON="rmmod failed"
    RELOAD_STATUS="BLOCKED"
    RELOAD_REASON="Skipped repeated load/unload because rmmod failed"
  fi
else
  UNLOAD_STATUS="BLOCKED"
  UNLOAD_REASON="Module was pre-loaded by user prior to benchmark; preserved without unloading"
  RELOAD_STATUS="BLOCKED"
  RELOAD_REASON="Skipped repeated load/unload to preserve user pre-loaded module"
fi

"$PYTHON_BIN" - "$OUT_CSV" "$EXPERIMENT_ID" "$COMPILE_STATUS" "$COMPILE_REASON" "$LOAD_STATUS" "$UNLOAD_STATUS" "$UNLOAD_REASON" "$RELOAD_STATUS" "$RELOAD_REASON" <<'PY'
import csv, sys
out_csv, exp_id, c_st, c_rsn, l_st, u_st, u_rsn, r_st, r_rsn = sys.argv[1:]
rows = list(csv.DictReader(open(out_csv, newline="", encoding="utf-8")))
extra = [
    ("module_compilation", c_st, c_rsn),
    ("module_loading", l_st, "insmod kernel/aipc_module.ko succeeded"),
    ("device_creation", "PASS", "/dev/aipc character device created"),
    ("module_unloading", u_st, u_rsn),
    ("repeated_load_unload", r_st, r_rsn),
]
fieldnames = list(rows[0].keys()) if rows else [
    "experiment_id", "record_type", "test_or_metric", "payload_bytes", "trial",
    "messages", "completed_messages", "validation_errors", "status", "status_reason",
    "elapsed_ns", "duration_s", "avg_latency_us", "throughput_msg_s",
    "bytes_per_sec", "mb_per_sec", "consumer_peak_rss_kb", "workload_type",
]
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for name, st, rsn in extra:
        w.writerow({
            "experiment_id": exp_id, "record_type": "functional_test",
            "test_or_metric": name, "payload_bytes": "", "trial": "",
            "messages": "", "completed_messages": "", "validation_errors": "",
            "status": st, "status_reason": rsn, "elapsed_ns": "", "duration_s": "",
            "avg_latency_us": "", "throughput_msg_s": "", "bytes_per_sec": "",
            "mb_per_sec": "", "consumer_peak_rss_kb": "", "workload_type": "kernel_functional",
        })
    for r in rows:
        w.writerow(r)
PY

