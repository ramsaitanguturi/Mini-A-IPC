#!/usr/bin/env bash
set -euo pipefail

#
# Mini A-IPC: Comparative Benchmarking Suite
# Evaluates all six classical Linux IPC mechanisms:
#   1. Anonymous Pipes (pipe)
#   2. Named Pipes (fifo)
#   3. System V Message Queues (sysv)
#   4. POSIX Message Queues (posix)
#   5. POSIX Shared Memory with Semaphores (shm)
#   6. Unix Domain Stream Sockets (uds)
#
# Workload:
#   - Payload sizes: 64, 128, 256, 512, 1024 bytes
#   - Identical request-response round-trip communication across all mechanisms
#   - Warm-up exchanges prior to measurement
#   - High-resolution CLOCK_MONOTONIC timing
#   - CPU affinity pinning for producer/consumer reproducibility
#

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p results

COUNT="${COUNT:-10000}"
TRIALS="${TRIALS:-5}"
WARMUP="${WARMUP:-500}"
CPU_PRODUCER="${CPU_PRODUCER:-0}"
CPU_CONSUMER="${CPU_CONSUMER:-1}"

OUT_LATENCY="results/comparative_benchmark.csv"
OUT_SYSCALL="results/syscall_benchmark.csv"

echo "============================================================"
echo " Mini A-IPC: Classical IPC Comparative Research Benchmark"
echo "============================================================"
echo "Configuration:"
echo "  Payload sizes   : 64, 128, 256, 512, 1024 bytes"
echo "  Exchanges/trial : ${COUNT}"
echo "  Trials          : ${TRIALS}"
echo "  Warm-up count   : ${WARMUP}"
echo "  Target Cores    : Producer CPU ${CPU_PRODUCER}, Consumer CPU ${CPU_CONSUMER}"
echo "============================================================"

# Step 1: Build the project
echo "[1/5] Building project binaries..."
make all

# Step 2: Run correctness tests
echo "[2/5] Running automated verification test suite..."
make test

# Step 3: Capture hardware and software environment
echo "[3/5] Capturing execution environment..."
bash ./bench/capture_environment.sh

# Check CPU affinity support
AFFINITY_ARGS=""
if taskset -c "$CPU_PRODUCER" true 2>/dev/null && taskset -c "$CPU_CONSUMER" true 2>/dev/null; then
  echo "  CPU affinity enabled: Producer pinned to CPU ${CPU_PRODUCER}, Consumer pinned to CPU ${CPU_CONSUMER}"
  AFFINITY_ARGS="--cpu-producer ${CPU_PRODUCER} --cpu-consumer ${CPU_CONSUMER}"
else
  echo "  WARNING: CPU affinity pinning is unavailable or not supported in this environment; proceeding unpinned."
fi

# Step 4: Execute latency and throughput comparative benchmark
echo "[4/5] Executing comparative latency benchmark across 6 IPC mechanisms..."
printf 'mechanism,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p99_rtt_us,p999_rtt_us,min_rtt_us,max_rtt_us,throughput_msg_sec\n' > "$OUT_LATENCY"

MECHANISMS="pipe fifo sysv posix shm uds"
SIZES="64 128 256 512 1024"

for size in $SIZES; do
  echo "  --> Benchmarking payload size: ${size} bytes..."
  for mode in $MECHANISMS; do
    for ((trial=1; trial<=TRIALS; trial++)); do
      ./mini-aipc --mode "$mode" --size "$size" --count "$COUNT" \
                  --warmup "$WARMUP" $AFFINITY_ARGS --trial "$trial" --csv >> "$OUT_LATENCY"
    done
  done
done
echo "Wrote latency benchmark results to ${OUT_LATENCY}"

# Step 5: System-call measurement experiment
echo "[5/5] Executing system-call measurement experiment..."
printf 'mechanism,payload_bytes,exchanges,total_syscalls,total_syscalls_per_exchange,comm_syscalls,comm_syscalls_per_exchange,setup_cleanup_syscalls,relevant_syscall_details\n' > "$OUT_SYSCALL"

if command -v strace >/dev/null 2>&1; then
  SYSCALL_EXCHANGES=100
  echo "  strace detected: profiling system call behavior over ${SYSCALL_EXCHANGES} exchanges..."
  for mode in $MECHANISMS; do
    STRACE_LOG="/tmp/strace_${mode}.log"
    # Run isolated run with strace
    strace -f -c -o "$STRACE_LOG" ./mini-aipc --mode "$mode" --size 64 --count "$SYSCALL_EXCHANGES" >/dev/null 2>&1
    python3 bench/parse_strace.py "$STRACE_LOG" "$mode" 64 "$SYSCALL_EXCHANGES" >> "$OUT_SYSCALL"
    rm -f "$STRACE_LOG"
  done
  echo "Wrote system-call benchmark results to ${OUT_SYSCALL}"
else
  echo "  strace is not installed; system call profiling skipped. (No fabricated data recorded)."
  echo "skipped,64,0,0,0.0,0,0.0,0,\"strace not installed in environment\"" >> "$OUT_SYSCALL"
fi

echo "============================================================"
echo " Comparative Benchmarking Complete!"
echo " Results available in:"
echo "   - ${OUT_LATENCY}"
echo "   - ${OUT_SYSCALL}"
echo "   - results/environment.txt"
echo "============================================================"

