#!/usr/bin/env bash
set -euo pipefail

# Ensure standard POSIX utilities are on PATH even when MSYS2 bash is invoked without -l
if [[ -d /usr/bin ]]; then
  case ":${PATH}:" in
    *:/usr/bin:*) ;;
    *) export PATH="/usr/bin:/bin:${PATH}" ;;
  esac
fi

#
# Mini A-IPC: Unified, Scientifically Controlled IPC Benchmarking Suite
#
# Single-command orchestrator evaluating all eight components:
#   1. Anonymous Pipes          (src/ipc_pipe.c)
#   2. Named Pipes / FIFO       (src/ipc_fifo.c)
#   3. System V Message Queue   (src/ipc_sysv_mq.c)
#   4. POSIX Message Queue      (src/ipc_posix_mq.c)
#   5. POSIX Shared Memory      (src/ipc_shm.c)
#   6. Unix Domain Socket       (src/ipc_uds.c)
#   7. Kernel AIPC Module       (kernel/aipc_module.c)
#   8. Adaptive Policy Selector (src/selector.c)
#
# Default controlled configuration (overridable via CLI flags or env vars):
#   --messages 10000
#   --warmup 500
#   --trials 7
#   --payloads 64,256,1024,4096,16384,65536,262144
#   --producers 1 --consumers 1
#   --cpu-producer 0 --cpu-consumer 1
#

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ---------------------------------------------------------------------------
# Defaults (honoring environment overrides)
# ---------------------------------------------------------------------------
MESSAGES="${MESSAGES:-10000}"
WARMUP="${WARMUP:-500}"
TRIALS="${TRIALS:-7}"
PAYLOADS="${PAYLOADS:-64,256,1024,4096,16384,65536,262144}"
PRODUCERS="${PRODUCERS:-1}"
CONSUMERS="${CONSUMERS:-1}"
CONCURRENCY_MATRIX="${CONCURRENCY_MATRIX:-1:1,2:1,4:1,1:2,4:4}"
CONCURRENCY_PAYLOAD="${CONCURRENCY_PAYLOAD:-256}"
CONCURRENCY_MESSAGES="${CONCURRENCY_MESSAGES:-}"
CONCURRENCY_TRIALS="${CONCURRENCY_TRIALS:-}"
UNIDIRECTIONAL_MESSAGES="${UNIDIRECTIONAL_MESSAGES:-}"
UNIDIRECTIONAL_TRIALS="${UNIDIRECTIONAL_TRIALS:-3}"
PROFILE_MESSAGES="${PROFILE_MESSAGES:-1000}"
PROFILE_WARMUP="${PROFILE_WARMUP:-100}"
THRESHOLD="${THRESHOLD:-1024}"
CPU_PRODUCER="${CPU_PRODUCER:-0}"
CPU_CONSUMER="${CPU_CONSUMER:-1}"
USE_AFFINITY=1
SEED="${SEED:-20261111}"
SKIP_CONCURRENCY=0
SKIP_KERNEL=0
SKIP_PROFILING=0
SKIP_UNIDIRECTIONAL=0
SMOKE_MODE=0
QUICK_MODE=0
OUTPUT_DIR=""

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]
Options:
  --messages N                 Timed messages/exchanges per trial (default: 10000)
  --warmup N                   Untimed warm-up exchanges per trial (default: 500)
  --trials N                   Number of independent randomized trials (default: 7)
  --payloads CSV               Comma-separated payload sizes in bytes
                               (default: 64,256,1024,4096,16384,65536,262144)
  --producers N                Primary RTT producer count (default: 1)
  --consumers N                Primary RTT consumer count (default: 1)
  --concurrency-matrix CSV     P:C pairs (default: 1:1,2:1,4:1,1:2,4:4)
  --concurrency-payload B      Payload size for concurrency matrix (default: 256)
  --concurrency-messages N     Messages per concurrency run (default: min(messages, 5000))
  --concurrency-trials N       Trials for concurrency matrix (default: min(trials, 5))
  --unidirectional-messages N  Messages per unidirectional run (default: min(messages, 2000))
  --unidirectional-trials N    Trials for unidirectional baseline (default: 3)
  --profile-messages N         Messages for separate resource profiler (default: 1000)
  --threshold BYTES            Adaptive selector threshold (default: 1024)
  --cpu-producer CORE          Producer CPU core (default: 0)
  --cpu-consumer CORE          Consumer CPU core (default: 1)
  --no-affinity                Disable CPU affinity pinning
  --seed N                     Deterministic randomization seed (default: 20261111)
  --smoke                      Quick smoke preset (messages=200, warmup=20, trials=3)
  --quick, -q                  Quick benchmark preset (messages=1000, warmup=100, trials=2, payloads=64,1024,16384)
  --output-dir DIR             Output directory (default: results/unified, or results/unified_quick if --quick)
  --skip-concurrency           Skip multi-producer/multi-consumer sweep
  --skip-unidirectional        Skip matched unidirectional baseline
  --skip-profiling             Skip separate RSS/ctx/syscall profiling pass
  --skip-kernel                Skip kernel module verification & benchmark
  -h, --help                   Show this help message
EOF
}

is_pos_int() { [[ "$1" =~ ^[0-9]+$ ]] && [[ "$1" -ge 1 ]]; }
is_nonneg_int() { [[ "$1" =~ ^[0-9]+$ ]]; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --messages) [[ $# -ge 2 ]] || { echo "ERROR: --messages requires a value" >&2; exit 2; }; MESSAGES="$2"; shift 2 ;;
    --warmup) [[ $# -ge 2 ]] || { echo "ERROR: --warmup requires a value" >&2; exit 2; }; WARMUP="$2"; shift 2 ;;
    --trials) [[ $# -ge 2 ]] || { echo "ERROR: --trials requires a value" >&2; exit 2; }; TRIALS="$2"; shift 2 ;;
    --payloads) [[ $# -ge 2 ]] || { echo "ERROR: --payloads requires a value" >&2; exit 2; }; PAYLOADS="$2"; shift 2 ;;
    --producers) [[ $# -ge 2 ]] || { echo "ERROR: --producers requires a value" >&2; exit 2; }; PRODUCERS="$2"; shift 2 ;;
    --consumers) [[ $# -ge 2 ]] || { echo "ERROR: --consumers requires a value" >&2; exit 2; }; CONSUMERS="$2"; shift 2 ;;
    --concurrency-matrix) [[ $# -ge 2 ]] || { echo "ERROR: --concurrency-matrix requires a value" >&2; exit 2; }; CONCURRENCY_MATRIX="$2"; shift 2 ;;
    --concurrency-payload) [[ $# -ge 2 ]] || { echo "ERROR: --concurrency-payload requires a value" >&2; exit 2; }; CONCURRENCY_PAYLOAD="$2"; shift 2 ;;
    --concurrency-messages) [[ $# -ge 2 ]] || { echo "ERROR: --concurrency-messages requires a value" >&2; exit 2; }; CONCURRENCY_MESSAGES="$2"; shift 2 ;;
    --concurrency-trials) [[ $# -ge 2 ]] || { echo "ERROR: --concurrency-trials requires a value" >&2; exit 2; }; CONCURRENCY_TRIALS="$2"; shift 2 ;;
    --unidirectional-messages) [[ $# -ge 2 ]] || { echo "ERROR: --unidirectional-messages requires a value" >&2; exit 2; }; UNIDIRECTIONAL_MESSAGES="$2"; shift 2 ;;
    --unidirectional-trials) [[ $# -ge 2 ]] || { echo "ERROR: --unidirectional-trials requires a value" >&2; exit 2; }; UNIDIRECTIONAL_TRIALS="$2"; shift 2 ;;
    --profile-messages) [[ $# -ge 2 ]] || { echo "ERROR: --profile-messages requires a value" >&2; exit 2; }; PROFILE_MESSAGES="$2"; shift 2 ;;
    --threshold) [[ $# -ge 2 ]] || { echo "ERROR: --threshold requires a value" >&2; exit 2; }; THRESHOLD="$2"; shift 2 ;;
    --cpu-producer) [[ $# -ge 2 ]] || { echo "ERROR: --cpu-producer requires a value" >&2; exit 2; }; CPU_PRODUCER="$2"; shift 2 ;;
    --cpu-consumer) [[ $# -ge 2 ]] || { echo "ERROR: --cpu-consumer requires a value" >&2; exit 2; }; CPU_CONSUMER="$2"; shift 2 ;;
    --no-affinity) USE_AFFINITY=0; shift ;;
    --seed) [[ $# -ge 2 ]] || { echo "ERROR: --seed requires a value" >&2; exit 2; }; SEED="$2"; shift 2 ;;
    --smoke) SMOKE_MODE=1; MESSAGES=200; WARMUP=20; TRIALS=3; CONCURRENCY_MESSAGES=200; CONCURRENCY_TRIALS=2; PROFILE_MESSAGES=200; PROFILE_WARMUP=20; UNIDIRECTIONAL_MESSAGES=200; UNIDIRECTIONAL_TRIALS=2; shift ;;
    --quick|-q) QUICK_MODE=1; MESSAGES=1000; WARMUP=100; TRIALS=2; PAYLOADS="64,1024,16384"; CONCURRENCY_MESSAGES=1000; CONCURRENCY_TRIALS=2; PROFILE_MESSAGES=200; PROFILE_WARMUP=20; UNIDIRECTIONAL_MESSAGES=200; UNIDIRECTIONAL_TRIALS=2; [[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="$ROOT/results/unified_quick"; shift ;;
    --output-dir) [[ $# -ge 2 ]] || { echo "ERROR: --output-dir requires a value" >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
    --skip-concurrency) SKIP_CONCURRENCY=1; shift ;;
    --skip-unidirectional) SKIP_UNIDIRECTIONAL=1; shift ;;
    --skip-profiling) SKIP_PROFILING=1; shift ;;
    --skip-kernel) SKIP_KERNEL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Strict Parameter Validation
# ---------------------------------------------------------------------------
is_pos_int "$MESSAGES" || { echo "ERROR: --messages must be a positive integer (got '$MESSAGES')" >&2; exit 2; }
is_nonneg_int "$WARMUP" || { echo "ERROR: --warmup must be a non-negative integer (got '$WARMUP')" >&2; exit 2; }
is_pos_int "$TRIALS" || { echo "ERROR: --trials must be a positive integer (got '$TRIALS')" >&2; exit 2; }
is_pos_int "$PRODUCERS" || { echo "ERROR: --producers must be a positive integer (got '$PRODUCERS')" >&2; exit 2; }
is_pos_int "$CONSUMERS" || { echo "ERROR: --consumers must be a positive integer (got '$CONSUMERS')" >&2; exit 2; }
is_pos_int "$CONCURRENCY_PAYLOAD" || { echo "ERROR: --concurrency-payload must be a positive integer" >&2; exit 2; }
is_nonneg_int "$THRESHOLD" || { echo "ERROR: --threshold must be a non-negative integer" >&2; exit 2; }
is_nonneg_int "$SEED" || { echo "ERROR: --seed must be a non-negative integer" >&2; exit 2; }
is_nonneg_int "$CPU_PRODUCER" || { echo "ERROR: --cpu-producer must be >= 0" >&2; exit 2; }
is_nonneg_int "$CPU_CONSUMER" || { echo "ERROR: --cpu-consumer must be >= 0" >&2; exit 2; }

if [[ -z "$CONCURRENCY_MESSAGES" ]]; then
  CONCURRENCY_MESSAGES=$(( MESSAGES < 5000 ? MESSAGES : 5000 ))
fi
if [[ -z "$CONCURRENCY_TRIALS" ]]; then
  CONCURRENCY_TRIALS=$(( TRIALS < 5 ? TRIALS : 5 ))
fi
if [[ -z "$UNIDIRECTIONAL_MESSAGES" ]]; then
  UNIDIRECTIONAL_MESSAGES=$(( MESSAGES < 2000 ? MESSAGES : 2000 ))
fi
is_pos_int "$CONCURRENCY_MESSAGES" || { echo "ERROR: --concurrency-messages must be >= 1" >&2; exit 2; }
is_pos_int "$CONCURRENCY_TRIALS" || { echo "ERROR: --concurrency-trials must be >= 1" >&2; exit 2; }
is_pos_int "$UNIDIRECTIONAL_MESSAGES" || { echo "ERROR: --unidirectional-messages must be >= 1" >&2; exit 2; }
is_pos_int "$UNIDIRECTIONAL_TRIALS" || { echo "ERROR: --unidirectional-trials must be >= 1" >&2; exit 2; }
is_pos_int "$PROFILE_MESSAGES" || { echo "ERROR: --profile-messages must be >= 1" >&2; exit 2; }

IFS=',' read -ra _p_arr <<< "$PAYLOADS"
[[ "${#_p_arr[@]}" -gt 0 ]] || { echo "ERROR: --payloads cannot be empty" >&2; exit 2; }
for _p in "${_p_arr[@]}"; do
  is_pos_int "$_p" || { echo "ERROR: Invalid payload size '$_p' in --payloads" >&2; exit 2; }
done

IFS=',' read -ra _m_arr <<< "$CONCURRENCY_MATRIX"
for _pair in "${_m_arr[@]}"; do
  [[ "$_pair" =~ ^[1-9][0-9]*:[1-9][0-9]*$ ]] || { echo "ERROR: Invalid concurrency pair '$_pair' (expected M:N)" >&2; exit 2; }
done

# ---------------------------------------------------------------------------
# Pre-Flight Safety & Dependency Checks
# ---------------------------------------------------------------------------
if [[ "$EUID" -eq 0 ]]; then
  echo "WARNING: Running entire benchmark as root is discouraged; continuing, but non-kernel experiments do not require sudo." >&2
fi

command -v gcc >/dev/null 2>&1 || { echo "ERROR: gcc compiler not found in PATH" >&2; exit 1; }
command -v make >/dev/null 2>&1 || { echo "ERROR: make not found in PATH" >&2; exit 1; }

# Detect Python 3 binary with pandas, numpy, matplotlib
find_python_with_deps() {
  local candidates=()
  [[ -n "${PYTHON_BIN:-}" ]] && candidates+=("$PYTHON_BIN")
  candidates+=(
    "$ROOT/.venv/bin/python"
    "$ROOT/venv/bin/python"
    "$HOME/.venv/bin/python"
    "$HOME/venv/bin/python"
    python3
    python
  )
  for wp in \
    "/c/Users/${USER:-ramsa}/AppData/Local/Programs/Python/Python314/python.exe" \
    "/c/Users/${USER:-ramsa}/AppData/Local/Programs/Python/Python312/python.exe" \
    "/c/Python314/python.exe" \
    "/c/Python312/python.exe"; do
    [[ -x "$wp" ]] && candidates+=("$wp")
  done
  for cand in "${candidates[@]}"; do
    if command -v "$cand" >/dev/null 2>&1 || [[ -x "$cand" ]]; then
      if "$cand" -c "import pandas, numpy, matplotlib" >/dev/null 2>&1; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python_with_deps)" || {
  echo "ERROR: No Python 3 interpreter with pandas, numpy, and matplotlib found." >&2
  echo "" >&2
  echo "To install system dependencies on Fedora Linux, run:" >&2
  echo "  sudo dnf install -y python3-pandas python3-numpy python3-matplotlib" >&2
  echo "" >&2
  echo "Or via pip in a virtual environment:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install pandas numpy matplotlib" >&2
  echo "" >&2
  echo "Or point directly to an existing interpreter: export PYTHON_BIN=/path/to/python3" >&2
  exit 1
}

# Check disk space (>= 50 MB free)
AVAIL_KB=$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')
if [[ -n "$AVAIL_KB" && "$AVAIL_KB" -lt 51200 ]]; then
  echo "ERROR: Insufficient disk space (${AVAIL_KB} KB available; need >= 51200 KB)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Output Directories, Unique Experiment ID, and Non-Overwrite Preservation
# ---------------------------------------------------------------------------
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$ROOT/results/unified"
fi
UNIFIED_DIR="$OUTPUT_DIR"
RAW_DIR="$UNIFIED_DIR/raw"
PROC_DIR="$UNIFIED_DIR/processed"
GRAPHS_DIR="$UNIFIED_DIR/graphs"
REPORTS_DIR="$UNIFIED_DIR/reports"
RUNS_DIR="$UNIFIED_DIR/runs"

mkdir -p "$RAW_DIR" "$PROC_DIR" "$GRAPHS_DIR" "$REPORTS_DIR" "$RUNS_DIR"

# Preserve any previous unified run before starting a new one
if [[ -f "$PROC_DIR/benchmark_metadata.json" ]]; then
  PREV_ID="$("$PYTHON_BIN" -c "import json; print(json.load(open(r'$PROC_DIR/benchmark_metadata.json')).get('experiment_id',''))" 2>/dev/null || true)"
  if [[ -n "$PREV_ID" && ! -d "$RUNS_DIR/$PREV_ID" ]]; then
    echo "[Init] Preserving previous experiment snapshot -> results/unified/runs/${PREV_ID}/"
    mkdir -p "$RUNS_DIR/$PREV_ID"
    cp -r "$RAW_DIR" "$PROC_DIR" "$GRAPHS_DIR" "$REPORTS_DIR" "$RUNS_DIR/$PREV_ID/" 2>/dev/null || true
    [[ -f "$UNIFIED_DIR/environment.txt" ]] && cp "$UNIFIED_DIR/environment.txt" "$RUNS_DIR/$PREV_ID/"
  fi
fi

EXPERIMENT_ID="exp_$(date -u +%Y%m%dT%H%M%SZ)_$$"
ENVIRONMENT_ID="$(uname -s)_$(uname -m)_$(hostname 2>/dev/null || echo host)"

# Safe cleanup trap preserving partial CSVs and cleaning stray IPC nodes
cleanup_on_exit() {
  rm -f /tmp/mini_aipc_*.fifo /tmp/mini_aipc_*.sock /dev/mqueue/mini_aipc_* /dev/shm/mini_aipc_* 2>/dev/null || true
}
trap cleanup_on_exit EXIT INT TERM

echo "========================================================================"
echo " Mini A-IPC: Unified Controlled IPC Benchmarking Suite"
echo "========================================================================"
echo " Experiment ID   : $EXPERIMENT_ID"
echo " Python Runtime  : $PYTHON_BIN"
echo " Messages/Trial  : $MESSAGES (Warm-up: $WARMUP)"
echo " Trials          : $TRIALS (Seed: $SEED)"
echo " Payloads (B)    : $PAYLOADS"
echo " Concurrency     : $CONCURRENCY_MATRIX (@ ${CONCURRENCY_PAYLOAD} B)"
echo " CPU Pinning     : $([[ $USE_AFFINITY -eq 1 ]] && echo "Producer=$CPU_PRODUCER, Consumer=$CPU_CONSUMER" || echo "Disabled")"
echo "========================================================================"

# ---------------------------------------------------------------------------
# Step 1: Clean Host-Native Build
# ---------------------------------------------------------------------------
echo "[1/7] Checking & building project binaries..."
OS_SYS="$(uname -s)"
NEED_CLEAN=0
if [[ "$OS_SYS" == MSYS* || "$OS_SYS" == CYGWIN* ]]; then
  # Ensure we don't accidentally run pre-committed Linux ELF files on MSYS2
  if [[ -f "$ROOT/mini-aipc" ]] && file "$ROOT/mini-aipc" 2>/dev/null | grep -q "ELF"; then
    NEED_CLEAN=1
  fi
fi
if [[ "$NEED_CLEAN" -eq 1 || ! -x "$ROOT/bin/aipc_unified_bench" ]]; then
  make clean
fi
make all

BIN_UNIFIED="$ROOT/bin/aipc_unified_bench"
BIN_MINI="$ROOT/mini-aipc"
BIN_MIXED="$ROOT/mini-aipc-mixed"
if [[ "$OS_SYS" == MSYS* || "$OS_SYS" == CYGWIN* ]]; then
  [[ -x "${BIN_UNIFIED}.exe" ]] && BIN_UNIFIED="${BIN_UNIFIED}.exe"
  [[ -x "${BIN_MINI}.exe" ]] && BIN_MINI="${BIN_MINI}.exe"
  [[ -x "${BIN_MIXED}.exe" ]] && BIN_MIXED="${BIN_MIXED}.exe"
fi

# ---------------------------------------------------------------------------
# Step 2: Check CPU Affinity & Capture Environment
# ---------------------------------------------------------------------------
echo "[2/7] Capturing execution environment -> results/unified/environment.txt"
AFF_PROD="-1"
AFF_CONS="-1"
AFF_STATUS="DISABLED by --no-affinity"
if [[ "$USE_AFFINITY" -eq 1 ]]; then
  if taskset -c "$CPU_PRODUCER" true >/dev/null 2>&1 && taskset -c "$CPU_CONSUMER" true >/dev/null 2>&1; then
    AFF_PROD="$CPU_PRODUCER"
    AFF_CONS="$CPU_CONSUMER"
    AFF_STATUS="SUPPORTED and ACTIVE (sched_setaffinity: producer=$AFF_PROD, consumer=$AFF_CONS)"
  else
    AFF_STATUS="UNAVAILABLE on host (proceeding unpinned)"
  fi
fi

{
  echo "Mini A-IPC Unified Benchmark Environment"
  echo "Experiment ID: ${EXPERIMENT_ID}"
  echo "Environment ID: ${ENVIRONMENT_ID}"
  echo "Captured at (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "[OS / Kernel]"
  uname -a
  cat /etc/os-release 2>/dev/null || true
  echo
  echo "[CPU]"
  lscpu 2>/dev/null || grep -m1 'model name' /proc/cpuinfo 2>/dev/null || echo "nproc=$(nproc 2>/dev/null || echo unknown)"
  echo
  echo "[Memory]"
  head -n 8 /proc/meminfo 2>/dev/null || true
  echo
  echo "[Compiler & Flags]"
  gcc --version 2>&1 | head -n 1
  grep -E '^CFLAGS|^LDFLAGS' Makefile || true
  echo
  echo "[Python & Libraries]"
  "$PYTHON_BIN" -c "import sys, pandas, numpy, matplotlib; print('python:', sys.version.split()[0], 'pandas:', pandas.__version__, 'numpy:', numpy.__version__, 'matplotlib:', matplotlib.__version__)"
  echo
  echo "[Instrumentation & Kernel Availability]"
  echo "CPU affinity status: ${AFF_STATUS}"
  if [[ "$OS_SYS" == "Linux" ]]; then
    echo "Kernel headers (/lib/modules/$(uname -r)/build): $([[ -d "/lib/modules/$(uname -r)/build" ]] && echo PRESENT || echo MISSING)"
    echo "Linux strace: $(command -v strace 2>/dev/null || echo MISSING)"
    echo "Linux perf: $(command -v perf 2>/dev/null || echo MISSING)"
  else
    echo "Kernel headers: UNAVAILABLE (non-Linux host ${OS_SYS})"
    echo "Linux strace: UNAVAILABLE (host strace is Cygwin/MSYS or absent)"
  fi
  echo "GNU time: $(command -v /usr/bin/time 2>/dev/null || echo MISSING)"
  echo "Pre-existing aipc_module loaded: $(lsmod 2>/dev/null | grep -q '^aipc_module\b' && echo YES || echo NO)"
  echo
  echo "[Experiment Parameters]"
  echo "MESSAGES=${MESSAGES} WARMUP=${WARMUP} TRIALS=${TRIALS} SEED=${SEED}"
  echo "PAYLOADS=${PAYLOADS}"
  echo "CONCURRENCY_MATRIX=${CONCURRENCY_MATRIX} CONCURRENCY_PAYLOAD=${CONCURRENCY_PAYLOAD}"
  echo "THRESHOLD=${THRESHOLD}"
} > "$UNIFIED_DIR/environment.txt"

# ---------------------------------------------------------------------------
# Step 3: Run Controlled Sequential Randomized Benchmark Matrix
# ---------------------------------------------------------------------------
echo "[3/7] Executing controlled sequential benchmark trials..."
ORCH_FLAGS=(
  --bin "$BIN_UNIFIED"
  --mixed-bin "$BIN_MIXED"
  --experiment-id "$EXPERIMENT_ID"
  --environment-id "$ENVIRONMENT_ID"
  --out-csv "$RAW_DIR/all_results.csv"
  --meta-out "$PROC_DIR/benchmark_metadata.json"
  --messages "$MESSAGES"
  --warmup "$WARMUP"
  --trials "$TRIALS"
  --payloads "$PAYLOADS"
  --producers "$PRODUCERS"
  --consumers "$CONSUMERS"
  --concurrency-matrix "$CONCURRENCY_MATRIX"
  --concurrency-payload "$CONCURRENCY_PAYLOAD"
  --concurrency-messages "$CONCURRENCY_MESSAGES"
  --concurrency-trials "$CONCURRENCY_TRIALS"
  --unidirectional-messages "$UNIDIRECTIONAL_MESSAGES"
  --unidirectional-trials "$UNIDIRECTIONAL_TRIALS"
  --threshold "$THRESHOLD"
  --cpu-producer "$AFF_PROD"
  --cpu-consumer "$AFF_CONS"
  --seed "$SEED"
)
[[ "$SKIP_CONCURRENCY" -eq 1 ]] && ORCH_FLAGS+=(--skip-concurrency)
[[ "$SKIP_UNIDIRECTIONAL" -eq 1 ]] && ORCH_FLAGS+=(--skip-unidirectional)

"$PYTHON_BIN" "$ROOT/bench/orchestrate_unified.py" "${ORCH_FLAGS[@]}"

# ---------------------------------------------------------------------------
# Step 4: Separate Resource & Syscall Profiling Pass
# ---------------------------------------------------------------------------
PROFILE_TMP="$RAW_DIR/_profile_tmp.csv"
SYSCALLS_TMP="$RAW_DIR/_syscalls_tmp.csv"
rm -f "$PROFILE_TMP" "$SYSCALLS_TMP"

if [[ "$SKIP_PROFILING" -eq 0 ]]; then
  echo "[4/7] Running separate OS/RSS/context-switch/syscall profiling pass..."
  "$PYTHON_BIN" "$ROOT/bench/profile_resources.py" \
    --bin "$BIN_UNIFIED" \
    --mini-aipc "$BIN_MINI" \
    --experiment-id "$EXPERIMENT_ID" \
    --payloads "$PAYLOADS" \
    --mechanisms "pipe,fifo,sysv,posix,shm,uds,adaptive" \
    --messages "$PROFILE_MESSAGES" \
    --warmup "$PROFILE_WARMUP" \
    --cpu-producer "$AFF_PROD" \
    --cpu-consumer "$AFF_CONS" \
    --out-profile "$PROFILE_TMP" \
    --out-syscalls "$SYSCALLS_TMP"
else
  echo "[4/7] Separate profiling skipped (--skip-profiling)."
fi

# ---------------------------------------------------------------------------
# Step 5: Kernel Module Verification & Benchmarking
# ---------------------------------------------------------------------------
if [[ "$SKIP_KERNEL" -eq 0 ]]; then
  echo "[5/7] Executing Kernel AIPC Module verification & benchmark suite..."
  EXPERIMENT_ID="$EXPERIMENT_ID" \
  OUT_CSV="$RAW_DIR/kernel_results.csv" \
  OUT_EXPLORATORY="$RAW_DIR/kernel_exploratory.csv" \
  PAYLOADS="$PAYLOADS" \
  MESSAGES="$UNIDIRECTIONAL_MESSAGES" \
  WARMUP="$PROFILE_WARMUP" \
  TRIALS="$TRIALS" \
  PYTHON_BIN="$PYTHON_BIN" \
    bash "$ROOT/bench/run_kernel_suite.sh" || true
else
  echo "[5/7] Kernel suite skipped (--skip-kernel); recording BLOCKED notice..."
  EXPERIMENT_ID="$EXPERIMENT_ID" \
  OUT_CSV="$RAW_DIR/kernel_results.csv" \
  PAYLOADS="$PAYLOADS" \
  PYTHON_BIN="$PYTHON_BIN" \
    bash -c '
      "$PYTHON_BIN" - "$OUT_CSV" "$EXPERIMENT_ID" "$PAYLOADS" <<PY
import csv, sys
out_csv, exp_id, payloads_s = sys.argv[1:]
fieldnames = ["experiment_id","record_type","test_or_metric","payload_bytes","trial","messages","completed_messages","validation_errors","status","status_reason","elapsed_ns","duration_s","avg_latency_us","throughput_msg_s","bytes_per_sec","mb_per_sec","consumer_peak_rss_kb","workload_type"]
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerow({"experiment_id": exp_id, "record_type": "functional_test", "test_or_metric": "kernel_suite", "status": "BLOCKED", "status_reason": "Skipped by --skip-kernel flag", "workload_type": "kernel_functional"})
PY
    '
fi

# ---------------------------------------------------------------------------
# Step 6: Statistical Analysis, Graphs, & Final Report
# ---------------------------------------------------------------------------
echo "[6/7] Computing statistical summaries, 95% CIs, paired tests, and adaptive regret..."
"$PYTHON_BIN" "$ROOT/bench/analyze_results.py" \
  --raw-dir "$RAW_DIR" \
  --processed-dir "$PROC_DIR" \
  --meta-in "$PROC_DIR/benchmark_metadata.json" \
  --profile-tmp "$PROFILE_TMP" \
  --syscalls-tmp "$SYSCALLS_TMP"

rm -f "$PROFILE_TMP" "$SYSCALLS_TMP"

echo "[7/7] Generating 13 publication-quality PNG/PDF graphs and FINAL_BENCHMARK_REPORT.md..."
"$PYTHON_BIN" "$ROOT/bench/generate_graphs.py" \
  --raw-dir "$RAW_DIR" \
  --processed-dir "$PROC_DIR" \
  --graphs-dir "$GRAPHS_DIR"

"$PYTHON_BIN" "$ROOT/bench/generate_report.py" --unified-dir "$UNIFIED_DIR"

# Archive immutable snapshot of this completed experiment
SNAP_DIR="$RUNS_DIR/$EXPERIMENT_ID"
mkdir -p "$SNAP_DIR"
cp -r "$RAW_DIR" "$PROC_DIR" "$GRAPHS_DIR" "$REPORTS_DIR" "$UNIFIED_DIR/environment.txt" "$SNAP_DIR/"

"$PYTHON_BIN" - "$PROC_DIR/benchmark_metadata.json" "$RUNS_DIR/experiments_index.csv" <<'PY'
import csv, json, os, sys
meta_path, idx_path = sys.argv[1:]
m = json.load(open(meta_path, encoding="utf-8"))
exists = os.path.exists(idx_path)
with open(idx_path, "a", newline="", encoding="utf-8") as f:
    cols = ["experiment_id", "started_at_utc", "overall_status", "host_os", "messages", "trials", "payloads"]
    w = csv.DictWriter(f, fieldnames=cols)
    if not exists:
        w.writeheader()
    w.writerow({
        "experiment_id": m.get("experiment_id"),
        "started_at_utc": m.get("started_at_utc"),
        "overall_status": m.get("overall_status"),
        "host_os": m.get("host_os"),
        "messages": m.get("config", {}).get("messages"),
        "trials": m.get("config", {}).get("trials"),
        "payloads": m.get("config", {}).get("payloads"),
    })
PY

echo "========================================================================"
echo " Unified Benchmark Complete! Summary:"
"$PYTHON_BIN" - "$PROC_DIR/benchmark_metadata.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"   Experiment ID  : {m['experiment_id']}")
print(f"   Overall Status : {m['overall_status']}")
for k, v in m.get("component_status", {}).items():
    print(f"   - {k:<14}: {v['status']:<11} ({v['reason']})")
PY
echo " Report : results/unified/reports/FINAL_BENCHMARK_REPORT.md"
echo " Graphs : results/unified/graphs/*.png (+ .pdf)"
echo " Archive: results/unified/runs/${EXPERIMENT_ID}/"
echo "========================================================================"
